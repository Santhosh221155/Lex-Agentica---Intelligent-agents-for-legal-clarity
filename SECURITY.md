# Security Architecture

## Current Implementation
- **Authentication**: Username + password, bcrypt hashing, JWT access tokens, refresh tokens.
- **Authorization**: Protected query, ingestion, memory, and admin endpoints.
- **Rate limiting**: Per-user and per-IP with Redis-backed counters.
- **Enhanced Prompt injection detection**: Multi-layer pattern matching with:
  - Unicode normalization
  - Homoglyph resolution (Cyrillic, Greek, etc.)
  - Critical pattern immediate blocking
  - Suspicious pattern score accumulation
  - Obfuscation detection
- **Sensitive Request Blocking**: Blocks requests for passwords, secrets, tokens, API keys, and credentials upfront.
- **Response Sanitization**: Removes citations, references, filenames, page numbers, and retrieval metadata from LLM outputs.
- **Tool governance**: Role-based allowlisting per tool with timeouts and retries.
- **File upload validation**: Extension, content-type, size limit, safe filenames.

## End-User Assistant Mode Security
The system has been updated from a document analyst tool to a natural end-user assistant with these security enhancements:
1. No more document/excerpt/citation references in responses
2. Sensitive information requests blocked immediately
3. Clean, sanitized responses with no internal metadata
4. Improved prompt injection defenses

## Architecture Reasoning
The design prioritizes least privilege, evidence-only answers, and a minimal trusted surface:
- JWT auth avoids session state on the API edge.
- Refresh tokens are persisted and revocable to reduce long-lived access risk.
- Role-based tool allowlisting prevents unapproved external calls.
- Prompt injection detection acts as early request filtering.
- Response sanitization prevents internal metadata leakage to end users.

## Dependencies
- PyJWT
- passlib[bcrypt]
- redis (optional but recommended)
- FastAPI security utilities

## Authorization Model
- User endpoints require a valid access token.
- Admin endpoints require `is_admin` on the user record.
- Ownership enforced on ingestion jobs.

## Rate Limiting
- Default: 100 requests/hour per user and per IP.
- Uploads: 20 uploads/hour per user and per IP.

## Input Validation
- Query sanitization strips control characters and enforces max length.
- Upload validation enforces PDF only, valid content-type, and max size.

## Output Validation
- Output sanitization strips control characters from streamed tokens.
- LLM response sanitization removes citations, filenames, page numbers, and metadata.

## Hardening Recommendations
- Rotate `SECRET_KEY` regularly and store via a secrets manager.
- Enforce TLS in production.
- Add CSRF protection for browser-based sessions (if added later).
- Add full audit logging for auth events and admin actions.
- Add dependency allowlists for tool endpoints.
