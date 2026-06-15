import os
import httpx
import asyncio
from typing import Optional


async def call_planning_model(prompt: str, system_prompt: str = None, model: str = None, timeout: float = 0.9, max_tokens: int = 300) -> Optional[str]:
    """Call a Groq-compatible chat completion endpoint to get a planner response.
    Uses a short timeout to keep planning latency under ~1s. Returns None on failure.
    """
    # Read env at call-time so updates to `.env` (or late dotenv loading) take effect
    groq_compat_url = os.getenv("GROQ_API_URL") or "https://api.groq.com/openai/v1/chat/completions"
    groq_api_key = os.getenv("GROQ_API_KEY")

    model = model or os.getenv("PLANNER_MODEL", "llama-3.1-8b-instant")
    headers = {"Content-Type": "application/json"}
    if groq_api_key:
        headers["Authorization"] = f"Bearer {groq_api_key}"

    system_msg = system_prompt or "You are a fast deterministic planner. Output JSON only."
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.0,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(groq_compat_url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
            # Groq-compatible response parsing
            choice = data["choices"][0]
            if "message" in choice:
                return choice["message"].get("content")
            return choice.get("text")
    except Exception:
        await asyncio.sleep(0)
        return None
