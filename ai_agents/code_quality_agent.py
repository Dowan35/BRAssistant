import os
import json
from ai_models.router import get_ai_review 
from toolbox.tool_execution_functions import execute_tool

async def process_code_review(state):
    """
    Full pipeline for the Code Quality theme (get the diff, rag infos, result of the tools and prompt).
    """

    sandbox = state["sandbox_path"]
    subject = state["patch_info"].get("subject", "")
    diff = state["patch_info"].get("diff", "")
    description = state["patch_info"].get("full_discussion", "")
    #Retrieve the list of precedent patches
    rag_context = state["rag_result"].get("code_review", [])
    if rag_context:
        rag_context_formatted = "\n\n".join([f"CASE {i+1}:\n{case}" for i, case in enumerate(rag_context)])
    else:
        rag_context_formatted = "No precedent rejected patches found."
    # Retrieve the list of manual rules about formatting from the database
    manual_data = state.get("manual_rules", [])
    
    # Launch the check-package script to check for some formatting and coding issues 
    tool_data = execute_tool("br_check_package.py", [sandbox])


    # 2. Prepare the prompts
    system_instruction_path = os.path.join("prompts", "code_quality_review.md")
    with open(system_instruction_path, "r") as f:
        system_instruction = f.read()

    prompt = f"""
    # SUBJECT :
    {subject}
    # DESCRIPTION : 
    {description}
    
    # DIFF :
    {diff}
    
    # TOOLS OUTPUT (check-package command results):
    {json.dumps(tool_data, indent=2)}

    # CONTEXT RAG :
    ## 1. Manual rules:
    {json.dumps(manual_data, indent=2)}

    ## 2. Precedent rejected patches:
    {json.dumps(rag_context_formatted, indent=2)}
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
        "theme": "Code review",
        "result": raw_response_text,
        "tokens": token_usage
    }
