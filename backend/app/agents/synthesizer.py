import asyncio
import re
from app.agents.llm_stream_client import stream_chat_completion
from app.services.security import sanitize_output_text, clean_llm_response, sanitize_retrieved_text
from app.services.reflection import reflect_answer


SYSTEM_PROMPT = """You are a helpful assistant. Answer the user's question directly and naturally. 

Rules you must follow without exception: 
- Never mention file names, page numbers, source names, or document metadata in your answer. 
- Never use phrases like "according to the document", "the excerpt states", "the provided document excerpts", or "Source:". 
- Never list citations or references at the end of your answer. 
- Answer in plain, confident English as if you already know the answer. 
- Do not explain your reasoning. Output only the final answer. 
- If the information is not in the provided context, say exactly: "I don't have information on that." 
- If the question asks for passwords, credentials, or system internals, say exactly: "I'm not able to help with that." 
"""


async def stream_synthesize(query: str, plan: dict, retrieval_res: dict, tools_res: dict, memory_res: dict, validation_res: dict):
    """Streaming synthesizer that calls an LLM streaming endpoint.

    Yields chunks with provenance metadata and initial plan trace.
    """
    # First yield the plan for the frontend trace panel
    yield {"role": "plan", "plan": plan}

    retrieved_chunks = retrieval_res.get("chunks") if retrieval_res else []
    if not retrieved_chunks:
        yield {
            "role": "synthesizer",
            "text": "I don't have information on that.",
            "provenance": [],
            "citations": [],
            "confidence": 0.0,
            "grounded": False,
        }
        return

    if validation_res and validation_res.get("hallucination_risk") == "HIGH":
        yield {
            "role": "synthesizer",
            "text": "I don't have information on that.",
            "provenance": [],
            "citations": [],
            "confidence": 0.0,
            "grounded": False,
        }
        return

    # Build prompt with system and user parts
    formatted_context = "\n\n".join([
        sanitize_retrieved_text(c.get("content", c.get("text", ""))) 
        for c in retrieved_chunks
    ])
    
    user_message = f"""Use the following context to answer the question. Do not reference the context directly. 

Context: 
{formatted_context} 

Question: {query} 

Answer:"""

    # Stream tokens from model
    from app.observability import record_token_usage
    full_text_so_far = ""
    in_citation_block = False
    answer_chunks = []
    async for token in stream_chat_completion(user_message, system_prompt=SYSTEM_PROMPT):
        # Attach light provenance: e.g., which retrieval source has highest score
        top_sources = [c.get("source") for c in retrieved_chunks[:3]]
        # approximate token count by whitespace-separated chunks
        token_text = sanitize_output_text(token)
        
        # Keep track of full text so far
        full_text_so_far += token_text
        
        # Check if we've started a citation block
        lowered_text = full_text_so_far.lower()
        if any(marker in lowered_text for marker in ["citations:", "references:", "sources:"]):
            in_citation_block = True
            continue  # Stop yielding once we hit a citation block
        
        if in_citation_block:
            continue  # Skip all tokens in citation block
        
        # Collect tokens, don't clean individual tokens - we'll clean the full response
        answer_chunks.append(token_text)
        token_count = max(1, len(str(token_text).split()))
        record_token_usage(token_count)
        yield {"role": "synthesizer", "text": token_text, "provenance": top_sources}

    # Build and clean final answer
    final_answer_raw = "".join(answer_chunks).strip()
    final_answer = clean_llm_response(final_answer_raw)
    if validation_res and validation_res.get("review_required"):
        yield {
            "role": "review",
            "text": "Human review required before final approval.",
            "review_required": True,
            "confidence": validation_res.get("confidence", 0.0),
            "threshold": validation_res.get("confidence_threshold", 0.72),
        }
    reflection = await reflect_answer(query, plan, retrieval_res, final_answer, validation_res)
    yield {
        "role": "reflection",
        "text": "Reflection: " + "; ".join(reflection.get("critique") or []),
        "reflection": reflection,
        "confidence": reflection.get("confidence", 0.0),
        "review_required": bool(validation_res and validation_res.get("review_required")),
    }

    if reflection.get("revised_answer") and reflection.get("revised_answer") != final_answer:
        cleaned_revised = clean_llm_response(reflection.get("revised_answer"))
        yield {
            "role": "revision",
            "text": cleaned_revised,
            "provenance": reflection.get("citations", []),
            "confidence": reflection.get("confidence", 0.0),
        }

