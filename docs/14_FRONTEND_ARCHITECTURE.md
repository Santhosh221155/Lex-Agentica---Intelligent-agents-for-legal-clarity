**Frontend Architecture**

Pages (under `frontend/pages`):
- `index.tsx` : main query UI.
- `collections.tsx`, `evaluations.tsx`, `settings.tsx`, `workspace.tsx` — workspace and admin pages.

Key components (under `frontend/components`):
- `AppShell.tsx`: top-level layout.
- `StreamOutput.tsx`, `TracePanel.tsx`, `ReviewPanel.tsx` — streaming output, trace inspection, and review UI.

State Management & API Integration:
- Frontend communicates with backend via REST and SSE for streaming answers.
- Auth: frontend uses JWT stored in browser to call protected endpoints (pattern implied by backend routes); API keys supported via headers.

User Workflows:
- Query -> receive streamed answer with provenance -> mark for review if requested -> reviewers approve/reject.
