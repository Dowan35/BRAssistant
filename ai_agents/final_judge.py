# ai_agents/final_judge.py
import os
import json
from ai_models.router import get_ai_review
from datetime import datetime

async def process_final_judge(state):
    """
    Consolidates all agents reports and generates the final email.
    """
    
    # 1. Extract patch metadata
    patch_info = state.get("patch_info", {})
    submitter_name = patch_info.get("submitter", {}).get("name", "")
    patch_subject = patch_info.get("subject", "")
    ai_model_used = os.getenv("AGENT_MODEL", "Unknown") # The model used for the agents has the biggest impact on the final review.
    
    # 2. Aggregate JSON reports from all agents that ran
    reports_list = []
    for report in state.get("agents_reports", []):
        if "result" in report:
            reports_list.append({
                "agent_theme": report.get("theme", "Unknown"),
                "report": report["result"]
            })

    system_instruction_path = os.path.join("prompts", "final_judge_review.md")
    with open(system_instruction_path, "r") as f:
        system_instruction = f.read()

    prompt = f"""
    Today's date : {datetime.now().strftime("%Y-%m-%d")}

    # CONTRIBUTOR_NAME : {submitter_name}

    # PATCH_SUBJECT : {patch_subject}
    # PATCH DESCRIPTION : {patch_info.get("full_discussion", "")}
    
    # MODEL USED : {ai_model_used}

    # JSON REPORTS FROM ALL AGENTS :
    {json.dumps(reports_list, indent=2)}
    """

    provider = os.getenv("JUDGE_PROVIDER", "").lower()
    model_id = os.getenv("JUDGE_MODEL", "")

    raw_response_text, token_usage = await get_ai_review(
            system_instruction, 
            prompt, 
            temp=0.3, # more freedom for the consolidation
            provider_override=provider, 
            model_override=model_id
    )
    
    return raw_response_text, token_usage
