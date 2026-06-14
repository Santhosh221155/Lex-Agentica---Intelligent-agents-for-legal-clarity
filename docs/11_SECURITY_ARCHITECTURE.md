**Security Architecture**

Authentication & Authorization: JWT + refresh tokens and API keys (see [backend/app/api/auth.py](backend/app/api/auth.py#L1-L200) and `APIKeyAuthMiddleware`).

Encryption & Secrets Management:
- Secrets expected via environment variables and `.env`. No secrets manager integration found in codebase (Not Found in Codebase: secrets manager integration like Vault).

API Security:
- Rate limiting middleware implemented as `RateLimitMiddleware` in [backend/app/main.py](backend/app/main.py#L1-L80).
- **Enhanced Prompt Injection Protection**: Multi-layer pattern matching with Unicode normalization, homoglyph resolution, critical pattern immediate blocking, and obfuscation detection.
- **Sensitive Request Blocking**: Blocks requests for passwords, secrets, tokens, API keys, and credentials upfront.
- **Response Sanitization**: Removes citations, references, filenames, page numbers, and retrieval metadata from LLM outputs.

Prompt Injection & Data Leakage Protections:
- `synthesizer` explicitly instructs LLMs to answer only from provided excerpts; `validator` checks for evidence overlap and sets `review_required` when confidence low.
- `sanitize_retrieved_text` removes instruction patterns from retrieved chunk text to defend against indirect prompt injection.
- `clean_llm_response` cleans outputs to remove internal metadata and document references.
- See [21_ANSWER_GENERATION_QUALITY.md](21_ANSWER_GENERATION_QUALITY.md) for detailed prompt injection handling guidelines and response quality requirements.

Audit & Trails:
- `document_audits`, `tools_history`, `traces`, and `audit_logs` capture actions for review and compliance.

Threat Model: (high-level)
- Insider data exfiltration: mitigated by tenancy scope and API key scopes, but enforcement requires operational controls.
- Model hallucination: mitigated by validator and review gating.
- Prompt injection: mitigated by multi-layer detection and sanitization.
- Sensitive data leakage: mitigated by sensitive request blocking and response sanitization.
