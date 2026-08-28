import os
from urllib import response
from openai import AsyncOpenAI, OpenAI, OpenAIError, RateLimitError, APIError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

def log_retry(retry_state):
    exception = retry_state.outcome.exception()
    sleep_time = retry_state.next_action.sleep
    attempt = retry_state.attempt_number
    if os.environ["VERBOSE_MODE"] == "1": print(f"    [~] API Issue (Attempt {attempt}): {exception}")
    if os.environ["VERBOSE_MODE"] == "1": print(f"    [~] Retrying in {sleep_time:.1f} seconds...")
    
@retry(stop=stop_after_attempt(6), wait=wait_exponential(multiplier=2, min=2, max=65), before_sleep=log_retry)
async def _call_api_with_retry(client, model_id, messages, temp):
    response =  await client.chat.completions.create(
        model=model_id,
        messages=messages,
        temperature=temp,
        max_tokens=3000,
    )

    if not response or getattr(response, 'choices', None) is None or len(response.choices) == 0:
        error_info = getattr(response, 'error', 'Empty choices returned by API')
        raise ValueError(f"Invalid OpenRouter response: {error_info}")

    content = response.choices[0].message.content
    if content is None or str(content).strip() == "":
        raise ValueError("Model returned an empty or NoneType content string.")
    
    return response

async def run_review(model_id, system_instructions, user_prompt, temp):
    """OpenRouter specialist for review (Free Large Context)."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key: raise ValueError("OPENROUTER_API_KEY missing")

    # Standard connector pointing to OpenRouter
    client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    messages = [{"role": "system", "content": system_instructions}, {"role": "user", "content": user_prompt}]
    
    try:
        response = await _call_api_with_retry(client, model_id, messages, temp)
        
        content = response.choices[0].message.content
        content = content.replace("```json\n", "").replace("```json", "").replace("```", "").strip()
        tokens = response.usage.total_tokens if hasattr(response, 'usage') and response.usage else 0

        return content, tokens

    except OpenAIError as e:
        if os.environ["VERBOSE_MODE"] == "1": print(f"[!] OpenAI/OpenRouter Network Error: {e}")
        return '{"status": "FAIL", "concerns": [{"quote": "", "issue": "API Network/Rate Limit Failed", "source": "System"}]}', 0
    except Exception as e:
        if os.environ["VERBOSE_MODE"] == "1": print(f"[!] Critical Error in OpenRouter Agent: {e}")
        return '{"status": "FAIL", "concerns": [{"quote": "", "issue": "Unexpected System Error", "source": "System"}]}', 0
