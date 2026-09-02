import os
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=15))
async def _call_api_with_retry(client, model_id, system_instructions, user_prompt, temp):
    # The Anthropic API requires max_tokens.
    # 4096 is a good limit to ensure the model has enough room to respond.
    response = await client.messages.create(
        model=model_id,
        system=system_instructions, # The system prompt is a separate argument in Anthropic
        messages=[
            {"role": "user", "content": user_prompt}
        ],
        temperature=temp,
        max_tokens=4096 
    )
    
    # Basic response validation
    if not response or not hasattr(response, 'content') or len(response.content) == 0:
        raise ValueError("Invalid or empty response from Anthropic")
        
    return response

async def run_review(model_id, system_instructions, user_prompt, temp):
    """Anthropic (Claude) specialist for code review (Asynchronous with robust retries)."""
    from anthropic import AsyncAnthropic
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key: 
        raise ValueError("ANTHROPIC_API_KEY missing from environment")

    # Initialize the async client
    client = AsyncAnthropic(api_key=api_key)
    
    try:
        response = await _call_api_with_retry(client, model_id, system_instructions, user_prompt, temp)
        
        # Extract the text (Anthropic returns a list of content blocks)
        content = response.content[0].text
        
        # Count tokens (Anthropic separates input and output)
        input_tokens = response.usage.input_tokens if hasattr(response, 'usage') else 0
        output_tokens = response.usage.output_tokens if hasattr(response, 'usage') else 0
        tokens = input_tokens + output_tokens
        
        return content, tokens

    except Exception as e:
        print(f"[!] Error Anthropic API: {e}")
        # JSON fallback in case of a final failure so the pipeline does not crash
        fallback_json = '{"status": "FAIL", "concerns": [{"quote": "", "issue": "API Request Failed (Anthropic Network/Limit)", "source": "System"}]}'
        return fallback_json, 0
