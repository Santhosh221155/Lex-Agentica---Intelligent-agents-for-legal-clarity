import asyncio
import json
import logging
from typing import Dict, Any, Optional

from app.agents.llm_client import call_planning_model
from app.services.document_store import list_chunks
from app.services.security import sanitize_chunk, clean_llm_response
from app.observability import log_event

LOGGER = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a helpful assistant that compares two documents. Answer the user's question directly and naturally.

Rules you must follow without exception:
- Never mention file names, page numbers, source names, or document metadata in your answer.
- Never use phrases like "according to the document", "the excerpt states", or "Source:".
- Never list citations or references at the end of your answer.
- Answer in plain, confident English as if you already know the answer.
- Do not explain your reasoning. Output only the final JSON.
- Always return a JSON object with exactly three keys: similarities, differences, summary.
- Each value should be a natural language string, no more than 300 words each.
"""


async def compare_documents(
    query: str,
    user_id: int,
    document_id_1: int,
    document_id_2: int
) -> Dict[str, Any]:
    """Compare two documents and return similarities, differences, and summary."""
    log_event(
        "comparison.start",
        user_id=user_id,
        query=query[:240],
        document_id_1=document_id_1,
        document_id_2=document_id_2
    )

    # 1. Validate that documents are different
    if document_id_1 == document_id_2:
        log_event("comparison.same_documents", user_id=user_id)
        raise ValueError("Please select two different documents to compare.")

    # 2. Retrieve chunks for both documents
    doc1_chunks = await list_chunks(document_id_1, user_id)
    doc2_chunks = await list_chunks(document_id_2, user_id)

    # 3. Check if either document has no chunks
    if not doc1_chunks:
        log_event("comparison.no_chunks", user_id=user_id, document_id=document_id_1)
        raise ValueError("Document A has no content.")
    if not doc2_chunks:
        log_event("comparison.no_chunks", user_id=user_id, document_id=document_id_2)
        raise ValueError("Document B has no content.")

    # 4. Check chunk quality (minimum 2 chunks each)
    if len(doc1_chunks) < 2 or len(doc2_chunks) < 2:
        log_event("comparison.insufficient_chunks", user_id=user_id, doc1_count=len(doc1_chunks), doc2_count=len(doc2_chunks))
        raise ValueError("Both documents must have at least 2 chunks to compare.")

    # 5. Sanitize chunks and build context strings
    doc1_context = "\n\n".join([
        sanitize_chunk(chunk.get("content", chunk.get("text", "")))
        for chunk in doc1_chunks
    ])
    doc2_context = "\n\n".join([
        sanitize_chunk(chunk.get("content", chunk.get("text", "")))
        for chunk in doc2_chunks
    ])

    # 6. Build prompt for LLM
    user_prompt = f"""Use the following contexts from two documents to answer the user's question.

Document 1 context:
{doc1_context}

Document 2 context:
{doc2_context}

User question: {query}

Return a JSON object with exactly three keys: similarities, differences, summary."""

    # 7. Call LLM
    try:
        llm_response = await call_planning_model(user_prompt, system_prompt=SYSTEM_PROMPT, timeout=30.0, max_tokens=1000)
    except Exception as e:
        log_event("comparison.llm_error", user_id=user_id, error=str(e))
        raise RuntimeError("Failed to generate comparison.") from e

    # 8. Parse JSON response
    parsed_response: Optional[Dict[str, Any]] = None
    for attempt in range(2):
        try:
            parsed_response = json.loads(llm_response)
            break
        except json.JSONDecodeError:
            if attempt == 0:
                # Retry with stricter prompt
                retry_prompt = f"""Previous response was not valid JSON. Please return ONLY valid JSON with keys: similarities, differences, summary.

{user_prompt}"""
                llm_response = await call_planning_model(retry_prompt, system_prompt=SYSTEM_PROMPT)
            else:
                log_event("comparison.parse_failed", user_id=user_id, response=llm_response[:240])
                raise RuntimeError("Failed to parse comparison response.")

    # 9. Validate response structure
    required_keys = ["similarities", "differences", "summary"]
    if not all(key in parsed_response for key in required_keys):
        log_event("comparison.missing_keys", user_id=user_id, keys=list(parsed_response.keys()))
        raise RuntimeError("Comparison response missing required keys.")

    # 10. Clean each field
    cleaned_response = {
        key: clean_llm_response(str(parsed_response[key]))
        for key in required_keys
    }

    log_event("comparison.complete", user_id=user_id)
    return cleaned_response
