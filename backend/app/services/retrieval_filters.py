import re
from typing import Any, Dict, Iterable, List, Optional
from app.observability import log_event


DOCUMENT_TYPE_ALIASES = {
    "contract": ["contract", "contracts", "legal contract", "legal contracts"],
    "report": ["report", "reports", "finance report", "finance reports", "financial report", "financial reports"],
    "memo": ["memo", "memos", "note", "notes"],
    "policy": ["policy", "policies", "policy document", "policy documents"],
    "invoice": ["invoice", "invoices"],
}

DEPARTMENT_ALIASES = {
    "finance": ["finance", "financial", "fiscal"],
    "legal": ["legal", "law", "compliance"],
    "hr": ["hr", "human resources", "people ops"],
    "sales": ["sales", "revenue operations", "revops"],
    "engineering": ["engineering", "product engineering", "platform"],
    "operations": ["operations", "ops", "supply chain"],
}


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _first_year(query: str) -> Optional[str]:
    match = re.search(r"\b(19|20)\d{2}\b", query)
    if match:
        return match.group(0)
    return None


def infer_retrieval_filters(query: str, plan: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    text = _normalize_text(query)
    inferred: Dict[str, Any] = {}

    if isinstance(plan, dict) and isinstance(plan.get("retrieval_filters"), dict):
        inferred.update({k: v for k, v in plan["retrieval_filters"].items() if v is not None})

    if year := _first_year(text):
        inferred.setdefault("date", year)

    for normalized, aliases in DOCUMENT_TYPE_ALIASES.items():
        if any(alias in text for alias in aliases):
            inferred.setdefault("document_type", normalized)
            break

    # Department filtering is intentionally disabled.
    #
    # Current ingestion metadata does not include a `department` field on
    # Chroma chunk documents, so applying a department filter would
    # incorrectly reduce retrieval results to 0.

    source_aliases = {
        "upload": ["uploaded file", "uploaded documents", "upload"],
        "email": ["email", "mail"],
        "web": ["web", "website", "internet"],
        "drive": ["drive", "google drive"],
    }
    for normalized, aliases in source_aliases.items():
        if any(alias in text for alias in aliases):
            inferred.setdefault("source", normalized)
            break

    owner_match = re.search(r"owner:\s*([\w\-@.]+)", text)
    if owner_match:
        inferred.setdefault("owner", owner_match.group(1))

    return {k: v for k, v in inferred.items() if v not in (None, "")}


def build_metadata_filter(owner_id: Optional[int], filters: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    clauses: List[Dict[str, Any]] = []
    if owner_id is not None:
        clauses.append({"owner_id": {"$eq": owner_id}})

    normalized = {k: v for k, v in (filters or {}).items() if v not in (None, "")}
    for field in ("document_type", "date", "owner", "document_id", "workspace_id", "department", "source"):
        value = normalized.get(field)
        if value is not None:
            clauses.append({field: {"$eq": value}})

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def _metadata_matches(metadata: Dict[str, Any], filters: Dict[str, Any]) -> bool:
    if not filters:
        return True

    for field, expected in filters.items():
        if expected in (None, ""):
            continue
        actual = metadata.get(field)
        if actual is None:
            if field == "owner":
                actual = metadata.get("owner_id") or metadata.get("document_owner")
            elif field == "source":
                actual = metadata.get("document_source") or metadata.get("filename")
            elif field == "document_type":
                actual = metadata.get("document_type")
            elif field == "department":
                actual = metadata.get("department")
            elif field == "date":
                actual = metadata.get("date") or metadata.get("year")
        # Do not drop chunks when the indexed metadata simply omits a field.
        if actual is None:
            continue
        if str(actual).lower() != str(expected).lower():
            return False
    return True


def filter_items(items: Iterable[Dict[str, Any]], filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    filters = filters or {}
    filtered: List[Dict[str, Any]] = []
    try:
        total_in = len(items) if hasattr(items, '__len__') else None
    except Exception:
        total_in = None
    log_event("retrieval.filter.enter", filter_summary=summarize_filters(filters), total_in=total_in)
    for item in items:
        metadata = dict(item.get("metadata") or {})
        if item.get("owner_id") is not None:
            metadata.setdefault("owner_id", item.get("owner_id"))
        if item.get("document_id") is not None:
            metadata.setdefault("document_id", item.get("document_id"))
        if item.get("workspace_id") is not None:
            metadata.setdefault("workspace_id", item.get("workspace_id"))
        if item.get("tenant_id") is not None:
            metadata.setdefault("tenant_id", item.get("tenant_id"))
        if item.get("document_source") is not None:
            metadata.setdefault("document_source", item.get("document_source"))
        if item.get("document_type") is not None:
            metadata.setdefault("document_type", item.get("document_type"))
        if item.get("department") is not None:
            metadata.setdefault("department", item.get("department"))
        if item.get("date") is not None:
            metadata.setdefault("date", item.get("date"))
        if item.get("year") is not None:
            metadata.setdefault("year", item.get("year"))
        metadata.setdefault("filename", item.get("source") or item.get("filename"))
        if _metadata_matches(metadata, filters):
            filtered.append(item)
    try:
        total_out = len(filtered)
    except Exception:
        total_out = None
    log_event("retrieval.filter.exit", filter_summary=summarize_filters(filters), total_out=total_out)
    return filtered
    


def summarize_filters(filters: Optional[Dict[str, Any]]) -> str:
    if not filters:
        return "no metadata filter"
    parts = [f"{key}={value}" for key, value in filters.items() if value not in (None, "")]
    return ", ".join(parts) if parts else "no metadata filter"


def is_document_scoped_query(query: str) -> bool:
    text = _normalize_text(query)
    doc_keywords = [
        "uploaded",
        "upload",
        "document",
        "file",
        "pdf",
        "card",
        "invoice",
        "contract",
        "receipt",
        "in the document",
        "in the file",
        "from the file",
        "from the document",
        "what is the name",
        "who is",
        "what does",
    ]
    return any(keyword in text for keyword in doc_keywords) or bool(infer_retrieval_filters(query, {}))


def is_general_knowledge_query(query: str) -> bool:
    text = _normalize_text(query)
    if is_document_scoped_query(query):
        return False
    general_keywords = ["latest", "news", "current", "today", "web", "internet", "external", "search"]
    return any(keyword in text for keyword in general_keywords)