import os
import pathlib
import sys
import json
import re
from ai_models.router import get_ai_review

parent_dir = pathlib.Path(__file__).parent.resolve()
MAPPING_FILE = parent_dir.parent / 'ressources' / 'sections_buildroot_manual.json'

try:
    with open(MAPPING_FILE, "r", encoding="utf-8") as f:
        SECTIONS_MAPPING = json.load(f)
except FileNotFoundError:
    print(f"Error: {MAPPING_FILE} not found.")
    sys.exit(1)

def extract_json_array(text):
    """
    Extract a JSON array from any raw text.
    Useful to remove <think> tags or markdown ```json blocks.
    """
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    
    match = re.search(r'\[\s*".*?\s*\]', text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    
    return json.loads(text)

async def get_relevant_chapters(git_diff: str) -> list:
    """
    Analyzes a git diff with an LLM and returns the list 
    of chapter numbers from the Buildroot manual to consult.
    """
    
    formatted_chapters = []
    for chapter_num, info in SECTIONS_MAPPING.items():
        titre = info["title"]
        formatted_chapters.append(f"{chapter_num}: {titre}")

    available_chapters_string = "\n".join(formatted_chapters)

    system_instruction_path = os.path.join("prompts", "relevant_chapters.md")
    with open(system_instruction_path, "r") as f:
        system_instruction = f.read()

    prompt = f"Here is the patch to analyze:\n{git_diff} \n\nAnd here are the available manual chapters:\n{available_chapters_string}"

    try:
        provider = os.getenv("ROUTING_PROVIDER", "").lower()
        model_id = os.getenv("ROUTING_MODEL", "")

        raw_response_text, token_usage = await get_ai_review(
            system_instruction, 
            prompt, 
            temp=0.1, 
            provider_override=provider, 
            model_override=model_id
        )
        chapters_list = extract_json_array(raw_response_text)
        return chapters_list, token_usage
    except Exception as e:
        print(f"Routing agent failed after retries or JSON parsing error: {e}")
        return ["22.5.1", "23"]
