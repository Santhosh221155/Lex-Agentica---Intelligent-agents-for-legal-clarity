**Governance & Human Review**

Human review workflow:
- `validator` sets `review_required` when confidence < threshold. The orchestrator persists a `review_request` (see `review_requests` table in models).
- Frontend surfaces review queue (UI components under `frontend/components/ReviewPanel.tsx`).

Escalation & Approval:
- Review records contain `reviewer_id`, `reviewer_notes`, and `status` that can be updated by admin reviewers.

Compliance checks:
- Audit trails exist via `document_audits`, `traces`, and `audit_logs` to allow retrospective compliance review.

Agent Oversight:
- Operators can re-run traces and inspect `trace` JSON persisted to `traces` table.
