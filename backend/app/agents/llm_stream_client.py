import os
import httpx
import asyncio
from typing import AsyncGenerator


async def stream_chat_completion(prompt: str, system_prompt: str = None, model: str = None) -> AsyncGenerator[str, None]:
    """Stream chat completion tokens from a Groq-compatible endpoint.

    Yields raw text chunks. Falls back to a simple local generator if streaming fails.
    """
    # Read env at call-time so updates to `.env` (or late dotenv loading) take effect
    groq_compat_url = os.getenv("GROQ_API_URL") or "https://api.groq.com/openai/v1/chat/completions"
    groq_api_key = os.getenv("GROQ_API_KEY")

    model = model or os.getenv("SYNTH_MODEL", "llama-3.3-70b-versatile")
    headers = {"Content-Type": "application/json"}
    if groq_api_key:
        headers["Authorization"] = f"Bearer {groq_api_key}"

    # Use provided system prompt or default
    default_system_prompt = """You are a helpful assistant answering questions based on available information.

Answer the user's question directly.

Rules:

1. Never mention:
   * documents
   * excerpts
   * citations
   * sources
   * filenames
   * page numbers
   * retrieval
   * chunks
   * context

2. Never say:
   * "According to the document"
   * "The provided document states"
   * "The excerpt mentions"
   * "Based on the retrieved information"

3. Never expose reasoning.
4. Never expose analysis.
5. Return only the final answer.
6. Use natural human language.
7. Keep answers concise.
8. Do not repeat information.

9. If information is unavailable:
   respond naturally.

Examples:
BAD: "The provided excerpts do not contain password information."
GOOD: "I cannot provide passwords or other sensitive account information."

BAD: "The topic of the case study is Green Loop according to Case_study.pdf."
GOOD: "The case study focuses on Green Loop, an AI-driven waste management and recycling platform."

BAD: "The punishment is not explicitly stated in the excerpts."
GOOD: "Writing a student's name on the answer sheet is listed as a malpractice offense. The available information does not specify the corresponding punishment."""

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt or default_system_prompt},
            {"role": "user", "content": prompt},
        ],
        "stream": True,
        "max_tokens": 1024,
        "temperature": 0.2,
    }

    try:
        refusal_markers = [
            "i can't answer",
            "i cannot answer",
            "i'm not able to provide",
            "i am not able to provide",
            "cannot help with that",
            "can't help with that",
            "i can't provide",
            "i cannot provide",
        ]
        prefix_buffer = ""
        emitted_any = False
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", groq_compat_url, json=payload, headers=headers) as resp:
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    # Groq-compatible streaming often sends lines like: data: {...}\n\n
                    if line.startswith("data:"):
                        data = line[len("data:"):].strip()
                        if data == "[DONE]":
                            break
                        try:
                            # parse JSON and extract token text
                            import json as _json
                            parsed = _json.loads(data)
                        except Exception:
                            # if parsing fails, yield raw data
                            yield data
                            continue

                        if isinstance(parsed, dict) and parsed.get("error"):
                            raise RuntimeError(parsed["error"].get("message") or parsed["error"])

                        # Choice delta content path
                        choices = parsed.get("choices", []) if isinstance(parsed, dict) else []
                        if not choices:
                            raise RuntimeError("empty model response")
                        delta = choices[0].get("delta", {})
                        token_text = delta.get("content") or delta.get("text")
                        if token_text:
                            if not emitted_any:
                                prefix_buffer += token_text
                                lowered = prefix_buffer.lower()
                                if any(marker in lowered for marker in refusal_markers):
                                    raise RuntimeError("model refusal detected")
                                if len(prefix_buffer) < 160 and not any(ch in prefix_buffer for ch in [".", "!", "?", "\n"]):
                                    continue
                                emitted_any = True
                                yield prefix_buffer
                                continue
                            yield token_text
                    else:
                        # Some endpoints stream raw text lines
                        if not emitted_any:
                            prefix_buffer += line
                            lowered = prefix_buffer.lower()
                            if any(marker in lowered for marker in refusal_markers):
                                raise RuntimeError("model refusal detected")
                            if len(prefix_buffer) < 160 and not any(ch in prefix_buffer for ch in [".", "!", "?", "\n"]):
                                continue
                            emitted_any = True
                            yield prefix_buffer
                            continue
                        yield line
        return
    except Exception:
        # Fallback: produce a short deterministic answer derived from the prompt
        # instead of returning unrelated placeholder text.
        query = ""
        sources = []
        in_sources = False
        for line in prompt.splitlines():
            if line.startswith("User query:"):
                query = line.split(":", 1)[1].strip()
            elif line.startswith("Relevant sources:"):
                in_sources = True
            elif in_sources and line.startswith("-"):
                sources.append(line.lstrip("- ").strip())
            elif in_sources and line.strip() and not line.startswith("-"):
                in_sources = False

        intro = f"I could not reach the model provider, so this is a local fallback answer for: {query or 'your question'}."
        if sources:
            body = " Retrieved evidence: " + "; ".join(sources[:3]) + "."
        else:
            body = " No retrieved evidence was available, so please upload relevant files and try again."

        closing = " This response is based on the current local pipeline and will improve once an LLM API is configured."
        for chunk in [intro, body, closing]:
            await asyncio.sleep(0.15)
            yield chunk
        return
