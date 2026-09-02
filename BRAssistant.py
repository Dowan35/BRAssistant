import asyncio
from email.message import EmailMessage
import re
import sys
import os
from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from sentence_transformers import SentenceTransformer

from ai_agents.code_quality_agent import process_code_review
from ai_agents.dependency_agent import process_dependency_review
from ai_agents.final_judge import process_final_judge
from ai_agents.license_agent import process_license_review
from ai_agents.toolchain_arch_agent import process_toolchain_arch_review
from ai_agents.upstream_agent import process_upstream_review
from toolbox.feedback_functions import get_feedback
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_agents.infra_agent import process_infra_review
from elastic_functions.search_database import search_history, search_manual
from sandbox.sandbox_git_tool import run_command
from ai_agents.contextualizing_agent import get_relevant_chapters
from toolbox.routing_functions import *
from toolbox.tool_execution_functions import execute_tool
from ai_agents import *

load_dotenv()

MAIL_ADRESS = os.getenv("MAIL_ADRESS", "")
EML_OUTPUT_DIR = os.getenv("EML_OUTPUT_DIR", "./reviews_eml")

es = Elasticsearch("http://localhost:9200", meta_header=False)
es = es.options(headers={"Accept": "application/vnd.elasticsearch+json; compatible-with=8"})
embedder = SentenceTransformer(os.getenv("HF_MODEL_ID", ""))

def clean_review_text(review_text):
    if not review_text:
        return ""
    return re.sub(r'<think>.*?</think>', '', review_text, flags=re.DOTALL).strip()

def save_as_eml(review_text, patch_data):
    msg = EmailMessage()
    msg.set_content(review_text)
    
    patch_subject = patch_data.get('subject', 'Unknown Patch')
    msg["Subject"] = f"Re: {patch_subject}"
    msg["From"] = MAIL_ADRESS
    
    submitter_email = patch_data.get("submitter", {}).get("email", "unknown@buildroot.org")
    msg["To"] = f"{submitter_email}, buildroot@buildroot.org"

    msg_id = patch_data.get('msgid')
    if msg_id:
        if not msg_id.startswith('<'):
            msg_id = f"<{msg_id}>"
        msg['In-Reply-To'] = msg_id
        msg['References'] = msg_id

    os.makedirs(EML_OUTPUT_DIR, exist_ok=True)
    patch_id = patch_data.get('id', 'unknown')
    file_path = os.path.join(EML_OUTPUT_DIR, f"review_patch_{patch_id}.eml")
    
    with open(file_path, "wb") as f:
        f.write(msg.as_bytes())
    
    print(f"\n[+] Review ready in {file_path}\n")

def stage_0_initialize_and_fetch_data(patch_target):
    """
    Execute Stage 0: prepare the environment and gather context.
    """
    print(f"[*] Starting Stage 0 for target: {patch_target}")
    state = {}

    # 1. Retrieve patch information (subject, diff, etc.)
    print("  [*] Extracting patch information...")
    patch_info = execute_tool("br_patch_info.py", [patch_target])
    if "error" in patch_info:
        print("Fatal error while fetching patch info.")
        sys.exit(1)
    
    state["patch_info"] = patch_info

    # 2. Ingestion and sandbox creation
    print("  [*] Ingesting patch and creating sandbox...")
    # Pass the URL or path to the ingestor. It should return {"sandbox_path": "/tmp/br_sandbox_xyz" , "status":...}
    ingest_result = execute_tool("br_ingestor.py", [patch_target])
    if "error" in ingest_result:
        print("Fatal error while applying the patch and creating sandbox.")
        sys.exit(1)
    state["sandbox_path"] = ingest_result.get("sandbox_path", ".")

    print("[+] Stage 0 completed successfully.\n")
    return state

async def stage_1_routing_async_tasks(state):
    """
    Execute Stage 1: route tasks to the appropriate agents based on the patch context and select agents that will be invoked.
    """
    print("[*] Starting Stage 1: Routing tasks to agents...")

    # Analyze the patch scope and determine which agents to invoke
    files_changed_raw = run_command(
        state["sandbox_path"], 
        ["git", "show", "--name-only", "--format=", "HEAD"]
    )
    files_changed_text = files_changed_raw["output"]
    files_changed = [line.strip() for line in files_changed_text.strip().split('\n') if line.strip()]

    state["is_package"] = False
    state["license_agent"] = False
    state["dependency_agent"] = False
    state["upstream_agent"] = False

    if is_package(files_changed):
        state["is_package"] = True
        print("  [*] Package-related changes detected.")
        # Determine if license agent should run
        if should_run_license_agent(files_changed, state["patch_info"].get("subject", "")):
            print("  [*] License agent will be invoked.")
            state["license_agent"] = True

        if should_run_dependency_agent(files_changed):
            print("  [*] Dependency agent will be invoked.")
            state["dependency_agent"] = True

        if should_run_toolchain_arch_agent(files_changed, state["patch_info"].get("subject", "")):
            print("  [*] Toolchain & Architecture agent will be invoked.")
            state["toolchain_arch_agent"] = True

        if should_run_upstream_agent(files_changed):
            print("[*] Upstream agent will be invoked.")
            state["upstream_agent"] = True

    # The AI contextualizing agent selects chapters
    print("  [*] Determining required manual chapters...")

    diff_content = state["patch_info"].get("diff", "")
    chapters_list, token_usage = await get_relevant_chapters(diff_content)
    print(f"    -> Selected chapters: {chapters_list}")
    # We then retrieve the relevant manual content for those chapters and store it in the state
    manual_rules = search_manual(es,chapters_list)
    state["manual_rules"] = manual_rules

    # Search and dispatch similar RAG patches
    similar_rag_patches = search_history(embedder, es, state["patch_info"])
    rag_result = dispatch_rag_patches(similar_rag_patches)
    state["rag_result"] = rag_result
    state['tokens'] = token_usage

    print("[+] Stage 1 completed successfully.\n")
    return state

async def stage_2_start_async_tasks(state):
    """
    Execute Stage 2: Start the asynchronous tasks for the selected agents.
    """
    print("[*] Starting Stage 2: Executing agent tasks...")

    tasks = []
    # For each agent that is flagged to run, execute its corresponding script
    if state.get("is_package"):
        tasks.append(process_infra_review(state))

        if state.get("license_agent"):
            tasks.append(process_license_review(state))

        if state.get("dependency_agent"):
            tasks.append(process_dependency_review(state))

        if state.get("upstream_agent"):
            tasks.append(process_upstream_review(state))
        
        if state.get("toolchain_arch_agent"):
            tasks.append(process_toolchain_arch_review(state))

    tasks.append(process_code_review(state))

    # wait for all agents to finish and gather their reports
    results = await asyncio.gather(*tasks)
    
    state["agents_reports"] = []
    for res in results:
        state["agents_reports"].append(res)
        state["tokens"] += res.get("tokens", 0)

    print("[+] Stage 2 completed successfully.\n")
    return state

async def stage_3_gather_results(state):
    """
    Execute Stage 3: Gather results from all agents and generate the final report."""
    print("[*] Starting Stage 3: Gathering results and generating final report...")

    if not state.get("agents_reports"):
        print("[!] No reports from agents were found. Exiting.")
        return state

    final_email, tokens = await process_final_judge(state)
    state["final_email"] = final_email
    state['tokens'] += tokens

    print("[+] Stage 3 completed successfully.\n")
    return state    

async def run_core_pipeline(target):
    """Launch the different stages of the pipeline in order."""
    state = stage_0_initialize_and_fetch_data(target)
    state = await stage_1_routing_async_tasks(state)
    state = await stage_2_start_async_tasks(state)
    state = await stage_3_gather_results(state)
    return state

def run_agent(patch_url):
    print(f"\n{'='*50}\nProcessing: {patch_url}\n{'='*50}")
    
    state = asyncio.run(run_core_pipeline(patch_url))
    
    if not state or not state.get("final_email"):
        print("[!] Analysis failed or no review generated.")
        return

    review_text = clean_review_text(state["final_email"])
    patch_data = state.get("patch_info", {})

    if review_text and patch_data:
        save_as_eml(review_text, patch_data)
        
        print("--- REVIEW PREVIEW ---\n")
        print(review_text[:500] + "\n[...]\n") 
        print(f"Total tokens used: {state['tokens']}")
        
        try:
            get_feedback(patch_url, "review_text") 
        except Exception as e:
            print(f"Error during feedback: {e}")

if __name__ == "__main__":

    #verbose mode handling
    if "-v" in sys.argv or "--verbose" in sys.argv:
        os.environ["VERBOSE_MODE"] = "1"
        # On nettoie sys.argv pour ne pas perturber la suite du script
        sys.argv = [arg for arg in sys.argv if arg not in ("-v", "--verbose")]
    else:
        os.environ["VERBOSE_MODE"] = "0"

    if not MAIL_ADRESS:
        sys.exit("Error: Please provide a valid MAIL_ADRESS in your .env file.")

    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            run_agent(arg)
            
    print("\n--- Welcome to the BRAssistant tool ---")
    print("(Type 'exit' or 'q' to stop the script)")

    while True:
        try:
            url = input("\nPaste Patchwork URL, file path or quit (q): ").strip()
            
            if url.lower() in ['exit', 'q', 'quit']:
                print("Goodbye!")
                break
                
            if not url:
                continue
                
            run_agent(url)
            
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break

