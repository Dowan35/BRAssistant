import os
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), 
       wait=wait_exponential(multiplier=2, min=2, max=10),
        before_sleep=lambda retry_state: print(f"  [~] API overloaded, retry {retry_state.attempt_number} in {retry_state.next_action.sleep} seconds.")
       )
async def _call_api_with_retry(client, model_id, messages, temp):
    return await client.chat.completions.create(
        model=model_id,
        messages=messages,
        temperature=temp,
        stream=False
    )

async def run_review(model_id, system_instructions, user_prompt, temp):
    """B.AI specialist for code review (Asynchronous with robust retries)."""
    api_key = os.getenv("B_AI_API_KEY")
    if not api_key: 
        raise ValueError("B_AI_API_KEY missing from environment")

    client = AsyncOpenAI(base_url="https://api.b.ai/v1", api_key=api_key)
    
    messages = [
        {"role": "system", "content": system_instructions}, 
        {"role": "user", "content": user_prompt}
    ]
    
    try:
        response = await _call_api_with_retry(client, model_id, messages, temp)
        
        if not response or getattr(response, 'choices', None) is None or len(response.choices) == 0:
            raise ValueError("Empty or invalid response from B.AI")
            
        content = response.choices[0].message.content
        content = content.replace("```json\n", "").replace("```json", "").replace("```", "").strip()
        tokens = response.usage.total_tokens if hasattr(response, 'usage') and response.usage else 0
        
        return content, tokens

    except Exception as e:
        print(f"[!] Error B.AI API: {e}")
        fallback_json = '{"status": "FAIL", "concerns": [{"quote": "", "issue": "API Request Failed (B.AI)", "source": "System"}]}'
        return fallback_json, 0
