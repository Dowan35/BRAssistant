import os
import json
from ai_models.router import get_ai_review 
from toolbox.tool_execution_functions import execute_tool_async

async def process_toolchain_arch_review(state):
    """
    Full pipeline for the Toolchain & arch theme (get the diff, rag infos, result of the tools and prompt).
    """

    sandbox = state["sandbox_path"]
    subject = state["patch_info"].get("subject", "")
    package_name = state["patch_info"].get("name", "")
    diff = state["patch_info"].get("diff", "")
    description = state["patch_info"].get("full_discussion", "")
    rag_context = state["rag_result"].get("toolchain_arch", [])
    if rag_context:
        rag_context_formatted = "\n\n".join([f"CASE {i+1}:\n{case}" for i, case in enumerate(rag_context)])
    else:
        rag_context_formatted = "No precedent rejected patches found."

    # 1. Execute the local tool (non-blocking)
    tool_data = await execute_tool_async("br_package_analyzer.py", ["toolchain", sandbox, package_name])

    # 2. Prepare the prompts
    system_instruction_path = os.path.join("prompts", "toolchain_and_arch_review.md")
    with open(system_instruction_path, "r") as f:
        system_instruction = f.read()

    prompt = f"""
    # SUBJECT :
    {subject}
    # DESCRIPTION : 
    {description}
    
    # DIFF :
    {diff}
    
    # TOOL OUTPUT :
    {json.dumps(tool_data, indent=2)}
    
    # CONTEXT RAG (precedent rejected patches):
    {rag_context_formatted}
    """

    provider = os.getenv("AGENT_PROVIDER", "").lower()
    model_id = os.getenv("AGENT_MODEL", "")

    raw_response_text, token_usage = await get_ai_review(
            system_instruction, 
            prompt, 
            temp=0.1, 
            provider_override=provider, 
            model_override=model_id
    )
    
    return {
        "theme": "Toolchain and Architecture",
        "result": raw_response_text,
        "tokens": token_usage
    }

