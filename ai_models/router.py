import os

from ai_models import agent_b_ai

from . import agent_openrouter
from . import agent_cohere
from . import agent_gemini
import ai_models.agent_claude as agent_claude

async def get_ai_review(system_instructions, user_prompt, temp=0.1, provider_override=None, model_override=None):
    """
    Read .env, choose the right agent and execute the review.
    """
    # print the prompts if VERBOSE_MODE is set
    if os.getenv("VERBOSE_MODE") == "1":
        print(f"\n\033[96m{'='*20} PROMPT SYSTEM {'='*20}\033[0m")
        print(system_instructions)
        print(f"\033[93m{'='*20} PROMPT USER {'='*20}\033[0m")
        print(user_prompt)
        print(f"\033[96m{'='*55}\033[0m\n")

    provider = provider_override or os.getenv("DEFAULT_AI_PROVIDER", "gemini").lower()
    
    if provider == "gemini":
        model_id = model_override or "gemini-3.5-flash"
        return await agent_gemini.run_review(model_id, system_instructions, user_prompt, temp)
    
    elif provider == "cohere":
        model_id = model_override or "command-a-plus-05-2026"
        return await agent_cohere.run_review(model_id, system_instructions, user_prompt, temp)
    
    elif provider == "openrouter":
        model_id = model_override or "nousresearch/hermes-3-llama-3.1-405b:free" 
        return await agent_openrouter.run_review(model_id, system_instructions, user_prompt, temp)

    elif provider == "claude":
        model_id = model_override or "claude-3-5-sonnet-20240620"
        return await agent_claude.run_review(model_id, system_instructions, user_prompt, temp)

    elif provider == "b.ai":
        model_id = model_override or "deepseek-v4-flash"
        return await agent_b_ai.run_review(model_id, system_instructions, user_prompt, temp)
    
    else:
        raise ValueError(f"Unknown REVIEW_AI_PROVIDER: {provider}. \nAvailable models: 'gemini', 'cohere', 'openrouter', 'claude', 'b.ai'.")
