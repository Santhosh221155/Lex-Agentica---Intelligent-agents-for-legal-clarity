import { useEffect, useMemo, useRef, useState } from 'react'
import { BACKEND_URL } from '../lib/auth'
import { useAuth } from '../lib/auth-client'
import ThemeToggle from './ThemeToggle'

/* ─── Types ─── */

type StreamItem = {
  role?: string
  text?: string
  provenance?: string[]
  error?: string
  plan?: any
  reflection?: any
  review_required?: boolean
}

type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  text: string
  streaming?: boolean
}

type ActiveDocument = {
  fileName: string
  jobId?: string
  documentId?: number | null
  status: 'queued' | 'processing' | 'completed' | 'failed'
  stage: string
  progress: number
  detail?: string
}

type PipelineStep = {
  label: string
  data: Record<string, any>
}

/* ─── Helpers ─── */

const INGRESS_ORDER = ['queued', 'processing', 'chunking', 'embedding', 'indexing', 'completed']

function stageLabel(stage: string) {
  switch (String(stage || '').toLowerCase()) {
    case 'queued': return 'Queued'
    case 'processing': return 'Processing'
    case 'chunking': return 'Chunking'
    case 'embedding': return 'Embedding'
    case 'indexing': return 'Indexing'
    case 'completed':
    case 'complete': return 'Ready'
    case 'failed': return 'Failed'
    default: return 'Uploading'
  }
}

function stageProgress(stage: string) {
  const normalized = String(stage || '').toLowerCase()
  if (normalized === 'completed' || normalized === 'complete') return 100
  const index = Math.max(0, INGRESS_ORDER.indexOf(normalized))
  return Math.round((index / (INGRESS_ORDER.length - 1)) * 100)
}

function friendlyError(kind: 'upload' | 'indexing' | 'retrieval' | 'auth' | 'general') {
  switch (kind) {
    case 'upload': return 'Upload failed. Please try again.'
    case 'indexing': return 'Indexing failed. Please try again.'
    case 'retrieval': return 'Something went wrong. Please try again.'
    case 'auth': return 'Sign-in failed. Please try again.'
    default: return 'Something went wrong. Please try again.'
  }
}

function isSecurityEvent(item: StreamItem): boolean {
  const text = JSON.stringify(item).toLowerCase()
  return text.includes('injection') || text.includes('guard') || text.includes('security')
}

/* ─── Component ─── */

export default function WorkspaceStudio() {
  const { status, logout, user, authFetch } = useAuth()

  // Chat state
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [queryValue, setQueryValue] = useState('')
  const [isRunning, setIsRunning] = useState(false)
  const [workspaceError, setWorkspaceError] = useState<string | null>(null)

  // Document state
  const [activeDocument, setActiveDocument] = useState<ActiveDocument | null>(null)
  const [confirmReplace, setConfirmReplace] = useState<File | null>(null)

  // Sources panel state
  const [currentSources, setCurrentSources] = useState<string[]>([])
  const [pipelineSteps, setPipelineSteps] = useState<PipelineStep[]>([])
  const [securityAlert, setSecurityAlert] = useState(false)
  const [sourcesOpen, setSourcesOpen] = useState(true)
  const [uploadOpen, setUploadOpen] = useState(true)

  // Refs
  const streamAbortRef = useRef<AbortController | null>(null)
  const transcriptEndRef = useRef<HTMLDivElement | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const uploadStatusRef = useRef<Record<string, string>>({})

  // Auto-scroll
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, isRunning])

  /* ─── Ingestion Polling ─── */

  async function pollIngest(jobId: string, fileName: string) {
    const pollingInterval = 1500
    while (true) {
      const response = await authFetch(`${BACKEND_URL}/api/ingest/status/${jobId}`)
      if (!response.ok) {
        const detail = friendlyError('indexing')
        setActiveDocument((current) =>
          current && current.jobId === jobId
            ? { ...current, status: 'failed', stage: 'failed', progress: 0, detail }
            : current,
        )
        setWorkspaceError(detail)
        return
      }

      const payload = await response.json()
      const rawStatus = String(payload?.status || payload?.meta?.status || 'processing').toLowerCase()
      const statusValue = rawStatus === 'complete' ? 'completed' : rawStatus
      const nextStatus = statusValue === 'completed' ? 'completed' : statusValue === 'failed' ? 'failed' : 'processing'

      const detail = nextStatus === 'failed'
        ? friendlyError('indexing')
        : payload?.meta?.error
          ? friendlyError('indexing')
          : nextStatus === 'completed'
            ? 'Indexed and ready.'
            : undefined

      const progress = stageProgress(statusValue)

      setActiveDocument((current) =>
        current && current.jobId === jobId
          ? { ...current, fileName, status: nextStatus, stage: statusValue, progress, detail }
          : current,
      )

      if (nextStatus === 'completed' || nextStatus === 'failed') return
      await new Promise((resolve) => setTimeout(resolve, pollingInterval))
    }
  }

  /* ─── Upload ─── */

  async function uploadFiles(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return

    const file = fileList[0] // Only one file at a time

    // If there's an active document, ask for confirmation
    if (activeDocument && activeDocument.status === 'completed') {
      setConfirmReplace(file)
      return
    }

    await performUpload(file)
  }

  async function performUpload(file: File) {
    setConfirmReplace(null)
    setWorkspaceError(null)

    const jobId = `upload-${crypto.randomUUID()}`
    uploadStatusRef.current[jobId] = 'queued'
    setActiveDocument({
      fileName: file.name,
      jobId,
      status: 'queued',
      stage: 'queued',
      progress: 8,
      detail: 'Uploading...',
    })

    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await authFetch(`${BACKEND_URL}/api/ingest/file`, {
        method: 'POST',
        body: formData,
      })

      const text = await response.text()
      let payload: any = null
      try { payload = text ? JSON.parse(text) : null } catch { payload = null }

      if (!response.ok) {
        const detail = friendlyError('upload')
        setActiveDocument((current) =>
          current && current.jobId === jobId
            ? { ...current, status: 'failed', stage: 'failed', progress: 0, detail }
            : current,
        )
        setWorkspaceError(detail)
        return
      }

      const backendJobId = String(payload?.job_id || payload?.db_job_id || '')
      const documentId = payload?.document_id ?? null

      if (!backendJobId) {
        const detail = friendlyError('upload')
        setActiveDocument((current) =>
          current && current.jobId === jobId
            ? { ...current, status: 'failed', stage: 'failed', progress: 0, detail }
            : current,
        )
        setWorkspaceError(detail)
        return
      }

      setActiveDocument((current) =>
        current && current.jobId === jobId
          ? {
              ...current,
              documentId,
              jobId: backendJobId,
              status: 'processing',
              stage: 'processing',
              progress: stageProgress('processing'),
              detail: 'Indexing in progress...',
            }
          : current,
      )

      uploadStatusRef.current[backendJobId] = 'processing'
      await pollIngest(backendJobId, file.name)
    } catch (error: any) {
      const detail = friendlyError('upload')
      setActiveDocument((current) =>
        current && current.jobId === jobId
          ? { ...current, status: 'failed', stage: 'failed', progress: 0, detail }
          : current,
      )
      setWorkspaceError(detail)
    }

    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  /* ─── Query / Chat ─── */

  async function runQuery(nextQuery = queryValue) {
    const question = nextQuery.trim()
    if (!question) return

    setWorkspaceError(null)
    setIsRunning(true)
    setCurrentSources([])
    setPipelineSteps([])
    setSecurityAlert(false)

    const userMessage: ChatMessage = {
      id: `user-${crypto.randomUUID()}`,
      role: 'user',
      text: question,
    }

    const assistantId = `assistant-${crypto.randomUUID()}`
    setMessages((current) => [...current, userMessage, { id: assistantId, role: 'assistant', text: '', streaming: true }])
    setQueryValue('')

    if (streamAbortRef.current) {
      streamAbortRef.current.abort()
    }
    const controller = new AbortController()
    streamAbortRef.current = controller

    try {
      const searchParams = new URLSearchParams({ q: question })
      if (activeDocument?.documentId) {
        searchParams.set('doc_id', String(activeDocument.documentId))
      }
      const response = await authFetch(`${BACKEND_URL}/api/stream-query?${searchParams.toString()}`, {
        method: 'GET',
        signal: controller.signal,
      })

      if (!response.ok || !response.body) {
        throw new Error('Request failed')
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let assistantText = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const segments = buffer.split('\n\n')
        buffer = segments.pop() || ''

        for (const segment of segments) {
          const line = segment
            .split('\n')
            .map((entry) => entry.trim())
            .find((entry) => entry.startsWith('data:'))

          if (!line) continue

          const payload = line.replace(/^data:\s*/, '')
          let item: StreamItem
          try { item = JSON.parse(payload) as StreamItem } catch { item = { text: payload } }

          if (item.error) throw new Error(item.error)

          // Check for security alerts
          if (isSecurityEvent(item)) {
            setSecurityAlert(true)
          }

          // Capture pipeline data
          if (item.role === 'plan' && item.plan) {
            const data: Record<string, any> = {}
            if (item.plan.retrieval_strategy) data.retrieval_strategy = item.plan.retrieval_strategy
            if (item.plan.requires_validation !== undefined) data.requires_validation = item.plan.requires_validation
            setPipelineSteps((prev) => [...prev, { label: 'Plan', data }])
          }

          if (item.role === 'reflection' && item.reflection) {
            const data: Record<string, any> = {}
            if (item.reflection.confidence !== undefined) data.confidence = Number(item.reflection.confidence).toFixed(2)
            if (item.reflection.hallucination_flags) data.hallucination_flags = item.reflection.hallucination_flags.length
            if (item.reflection.citation_count !== undefined) data.citation_count = item.reflection.citation_count
            setPipelineSteps((prev) => [...prev, { label: 'Reflection', data }])
          }

          // Capture sources
          if (Array.isArray(item.provenance) && item.provenance.length > 0) {
            setCurrentSources((current) => Array.from(new Set([...current, ...item.provenance!.map(String)])))
          }

          // Capture answer text
          if (item.role === 'synthesizer' || item.role === 'revision') {
            assistantText += item.text || ''
          }

          setMessages((current) =>
            current.map((message) =>
              message.id === assistantId
                ? { ...message, text: assistantText || message.text }
                : message,
            ),
          )
        }
      }

      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? { ...message, text: assistantText || message.text || 'No answer was returned.', streaming: false }
            : message,
        ),
      )
    } catch (error: any) {
      const detail = friendlyError('retrieval')
      setWorkspaceError(detail)
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? { ...message, text: detail, streaming: false }
            : message,
        ),
      )
    } finally {
      setIsRunning(false)
      streamAbortRef.current = null
    }
  }

  /* ─── Auth guard ─── */

  if (status === 'loading' || status !== 'authenticated') {
    return null
  }

  /* ─── Render ─── */

  return (
    <div style={root}>
      {/* Header */}
      <header style={header}>
        <div style={headerLeft}>
          <span style={logo}>Agentic RAG</span>
        </div>
        <div style={headerRight}>
          <ThemeToggle />
          <span style={userLabel}>{user?.username}</span>
          <button style={logoutBtn} onClick={() => void logout()}>Log out</button>
        </div>
      </header>

      {/* Main area */}
      <div style={main}>
        {/* Upload sidebar */}
        <aside style={{ ...uploadPanel, width: uploadOpen ? 260 : 48 }}>
          <button style={sidebarToggle} onClick={() => setUploadOpen(!uploadOpen)} title={uploadOpen ? 'Collapse' : 'Expand'}>
            {uploadOpen ? <ChevronLeftIcon /> : <ChevronRightIcon />}
          </button>
          {uploadOpen && (
            <div style={uploadContent}>
              <div style={panelTitle}>Upload</div>
              <button style={uploadBtn} onClick={() => fileInputRef.current?.click()}>Upload PDF</button>

              {activeDocument ? (
                <div style={docCard}>
                  <div style={docName}>{activeDocument.fileName}</div>
                  <div style={docStatus}>
                    <span style={statusDot(activeDocument.status)} />
                    <span>{stageLabel(activeDocument.stage)}</span>
                  </div>
                  <div style={progressTrack}>
                    <div style={{ ...progressFill, width: `${activeDocument.progress}%` }} />
                  </div>
                  {activeDocument.detail && <div style={docDetail}>{activeDocument.detail}</div>}
                </div>
              ) : (
                <div style={emptyDoc}>No document uploaded</div>
              )}

              {workspaceError && <div style={errorNotice}>{workspaceError}</div>}
            </div>
          )}
        </aside>

        {/* Chat panel */}
        <main style={chatPanel}>
          <div style={transcript}>
            {messages.length === 0 && (
              <div style={emptyChat}>Upload a document and ask a question.</div>
            )}
            {messages.map((message) => (
              <div key={message.id} style={message.role === 'user' ? userBubble : assistantBubble}>
                {message.text || (message.role === 'assistant' ? '\u00A0' : '')}
                {message.streaming && <span style={cursor}>|</span>}
              </div>
            ))}
            <div ref={transcriptEndRef} />
          </div>

          <div style={inputBar}>
            <input
              style={chatInput}
              value={queryValue}
              onChange={(e) => setQueryValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  void runQuery(queryValue)
                }
              }}
              placeholder="Ask a question..."
              disabled={isRunning}
            />
            <button
              style={sendBtn}
              onClick={() => void runQuery(queryValue)}
              disabled={isRunning || !queryValue.trim()}
            >
              <SendIcon />
            </button>
          </div>
        </main>

        {/* Sources sidebar */}
        <aside style={{ ...sourcesPanel, width: sourcesOpen ? 300 : 48 }}>
          <button style={sidebarToggle} onClick={() => setSourcesOpen(!sourcesOpen)} title={sourcesOpen ? 'Collapse' : 'Expand'}>
            {sourcesOpen ? <ChevronRightIcon /> : <ChevronLeftIcon />}
          </button>
          {sourcesOpen && (
            <div style={sourcesContent}>
              <div style={panelTitle}>Sources</div>

              {securityAlert && (
                <div style={securityNotice}>Query flagged by security guard</div>
              )}

              {/* Pipeline visualization */}
              {pipelineSteps.length > 0 && (
                <div style={pipelineSection}>
                  <div style={sectionLabel}>Pipeline</div>
                  {pipelineSteps.map((step, i) => (
                    <div key={i} style={pipelineCard}>
                      <div style={pipelineStepLabel}>{step.label}</div>
                      {Object.entries(step.data).map(([k, v]) => (
                        <div key={k} style={pipelineKv}>
                          <span style={pipelineKey}>{k}</span>
                          <span style={pipelineVal}>{String(v)}</span>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              )}

              {/* Sources list */}
              <div style={sectionLabel}>Retrieved Sources</div>
              {currentSources.length === 0 ? (
                <div style={emptySources}>Sources appear here during retrieval.</div>
              ) : (
                currentSources.map((source, i) => (
                  <div key={i} style={sourceCard}>{source}</div>
                ))
              )}
            </div>
          )}
        </aside>
      </div>

      {/* Replace confirmation modal */}
      {confirmReplace && (
        <div style={modalOverlay}>
          <div style={modalCard}>
            <div style={modalTitle}>Replace document?</div>
            <div style={modalText}>
              This will replace your current document. Continue?
            </div>
            <div style={modalActions}>
              <button style={modalCancel} onClick={() => setConfirmReplace(null)}>Cancel</button>
              <button style={modalConfirm} onClick={() => void performUpload(confirmReplace)}>Replace</button>
            </div>
          </div>
        </div>
      )}

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf,.pdf"
        hidden
        onChange={(event) => { void uploadFiles(event.target.files) }}
      />
    </div>
  )
}

/* ─── Inline SVG Icons ─── */

function ChevronLeftIcon() {
  return <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" /></svg>
}
function ChevronRightIcon() {
  return <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
}
function SendIcon() {
  return <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5l7 7-7 7" /></svg>
}

/* ─── Styles ─── */

const root: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  height: '100vh',
  overflow: 'hidden',
  background: 'var(--bg)',
}

const header: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '0 20px',
  height: 52,
  borderBottom: '1px solid var(--border)',
  background: 'var(--panel)',
  flexShrink: 0,
}

const headerLeft: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 12 }

const headerRight: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 12 }

const logo: React.CSSProperties = {
  fontWeight: 700,
  fontSize: 17,
  color: 'var(--text-primary)',
  letterSpacing: '-0.02em',
}

const userLabel: React.CSSProperties = {
  fontSize: 13,
  color: 'var(--text-muted)',
}

const logoutBtn: React.CSSProperties = {
  padding: '6px 14px',
  borderRadius: 8,
  border: '1px solid var(--border)',
  background: 'transparent',
  color: 'var(--text-secondary)',
  fontSize: 13,
  cursor: 'pointer',
  fontWeight: 500,
}

const main: React.CSSProperties = {
  display: 'flex',
  flex: 1,
  minHeight: 0,
  overflow: 'hidden',
}

/* Upload Panel */

const uploadPanel: React.CSSProperties = {
  borderRight: '1px solid var(--border)',
  background: 'var(--panel)',
  display: 'flex',
  flexDirection: 'column',
  flexShrink: 0,
  overflow: 'hidden',
  transition: 'width 200ms ease',
}

const sidebarToggle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 36,
  height: 36,
  margin: '8px auto 0',
  borderRadius: 8,
  border: '1px solid var(--border)',
  background: 'transparent',
  color: 'var(--text-muted)',
  cursor: 'pointer',
  flexShrink: 0,
}

const uploadContent: React.CSSProperties = {
  padding: '12px 14px',
  display: 'flex',
  flexDirection: 'column',
  gap: 12,
  overflow: 'auto',
}

const panelTitle: React.CSSProperties = {
  fontSize: 12,
  textTransform: 'uppercase',
  letterSpacing: '0.12em',
  color: 'var(--text-muted)',
  fontWeight: 600,
}

const uploadBtn: React.CSSProperties = {
  padding: '10px 14px',
  borderRadius: 8,
  background: 'var(--primary)',
  color: '#fff',
  border: 'none',
  cursor: 'pointer',
  fontWeight: 600,
  fontSize: 13,
  textAlign: 'center',
}

const docCard: React.CSSProperties = {
  padding: 12,
  borderRadius: 10,
  border: '1px solid var(--border)',
  background: 'var(--bg-soft)',
}

const docName: React.CSSProperties = {
  fontWeight: 600,
  fontSize: 13,
  color: 'var(--text-primary)',
  marginBottom: 6,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
}

const docStatus: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  fontSize: 12,
  color: 'var(--text-secondary)',
  marginBottom: 6,
}

function statusDot(status: string): React.CSSProperties {
  const bg = status === 'completed' ? 'var(--success)' : status === 'failed' ? 'var(--danger)' : 'var(--primary)'
  return { width: 8, height: 8, borderRadius: '50%', background: bg, flexShrink: 0 }
}

const progressTrack: React.CSSProperties = {
  height: 4,
  borderRadius: 999,
  background: 'var(--border)',
  overflow: 'hidden',
  marginBottom: 6,
}

const progressFill: React.CSSProperties = {
  height: '100%',
  borderRadius: 999,
  background: 'var(--primary)',
  transition: 'width 300ms ease',
}

const docDetail: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--text-muted)',
}

const emptyDoc: React.CSSProperties = {
  fontSize: 13,
  color: 'var(--text-muted)',
  textAlign: 'center',
  padding: 16,
}

const errorNotice: React.CSSProperties = {
  padding: 10,
  borderRadius: 8,
  background: 'color-mix(in srgb, var(--danger) 10%, var(--panel))',
  border: '1px solid color-mix(in srgb, var(--danger) 20%, transparent)',
  color: 'var(--danger)',
  fontSize: 13,
}

/* Chat Panel */

const chatPanel: React.CSSProperties = {
  flex: 1,
  display: 'flex',
  flexDirection: 'column',
  minWidth: 0,
  minHeight: 0,
}

const transcript: React.CSSProperties = {
  flex: 1,
  overflow: 'auto',
  padding: '24px 32px',
  display: 'flex',
  flexDirection: 'column',
  gap: 12,
}

const emptyChat: React.CSSProperties = {
  margin: 'auto',
  color: 'var(--text-muted)',
  fontSize: 15,
  textAlign: 'center',
}

const userBubble: React.CSSProperties = {
  alignSelf: 'flex-end',
  maxWidth: '70%',
  padding: '10px 16px',
  borderRadius: '18px 18px 4px 18px',
  background: 'var(--primary)',
  color: '#fff',
  fontSize: 14,
  lineHeight: 1.6,
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
}

const assistantBubble: React.CSSProperties = {
  alignSelf: 'flex-start',
  maxWidth: '70%',
  padding: '10px 16px',
  borderRadius: '18px 18px 18px 4px',
  background: 'var(--panel)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  fontSize: 14,
  lineHeight: 1.6,
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
}

const cursor: React.CSSProperties = {
  animation: 'blink 1s step-end infinite',
  fontWeight: 400,
}

const inputBar: React.CSSProperties = {
  display: 'flex',
  gap: 8,
  padding: '12px 24px 20px',
  borderTop: '1px solid var(--border)',
  flexShrink: 0,
}

const chatInput: React.CSSProperties = {
  flex: 1,
  padding: '10px 16px',
  borderRadius: 10,
  border: '1px solid var(--border)',
  background: 'var(--bg-soft)',
  color: 'var(--text-primary)',
  fontSize: 14,
  outline: 'none',
}

const sendBtn: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 40,
  height: 40,
  borderRadius: 10,
  border: 'none',
  background: 'var(--primary)',
  color: '#fff',
  cursor: 'pointer',
  flexShrink: 0,
}

/* Sources Panel */

const sourcesPanel: React.CSSProperties = {
  borderLeft: '1px solid var(--border)',
  background: 'var(--panel)',
  display: 'flex',
  flexDirection: 'column',
  flexShrink: 0,
  overflow: 'hidden',
  transition: 'width 200ms ease',
}

const sourcesContent: React.CSSProperties = {
  padding: '12px 14px',
  display: 'flex',
  flexDirection: 'column',
  gap: 12,
  overflow: 'auto',
}

const sectionLabel: React.CSSProperties = {
  fontSize: 11,
  textTransform: 'uppercase',
  letterSpacing: '0.12em',
  color: 'var(--text-muted)',
  fontWeight: 600,
  marginTop: 4,
}

const pipelineSection: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 8,
  marginBottom: 4,
}

const pipelineCard: React.CSSProperties = {
  padding: 10,
  borderRadius: 8,
  border: '1px solid var(--border)',
  background: 'var(--bg-soft)',
}

const pipelineStepLabel: React.CSSProperties = {
  fontWeight: 700,
  fontSize: 12,
  color: 'var(--text-primary)',
  marginBottom: 4,
}

const pipelineKv: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  fontSize: 12,
  gap: 8,
}

const pipelineKey: React.CSSProperties = {
  color: 'var(--text-muted)',
}

const pipelineVal: React.CSSProperties = {
  color: 'var(--text-secondary)',
  fontWeight: 500,
}

const securityNotice: React.CSSProperties = {
  padding: 10,
  borderRadius: 8,
  background: 'color-mix(in srgb, var(--warn) 12%, var(--panel))',
  border: '1px solid color-mix(in srgb, var(--warn) 24%, transparent)',
  color: 'var(--warn)',
  fontSize: 13,
  fontWeight: 600,
}

const emptySources: React.CSSProperties = {
  fontSize: 13,
  color: 'var(--text-muted)',
  textAlign: 'center',
  padding: 12,
}

const sourceCard: React.CSSProperties = {
  padding: 10,
  borderRadius: 8,
  border: '1px solid var(--border)',
  background: 'var(--bg-soft)',
  fontSize: 13,
  color: 'var(--text-secondary)',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
}

/* Modal */

const modalOverlay: React.CSSProperties = {
  position: 'fixed',
  inset: 0,
  background: 'rgba(0,0,0,0.4)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 100,
}

const modalCard: React.CSSProperties = {
  background: 'var(--panel)',
  borderRadius: 14,
  padding: 24,
  maxWidth: 380,
  width: '100%',
  boxShadow: 'var(--shadow-md)',
  border: '1px solid var(--border)',
}

const modalTitle: React.CSSProperties = {
  fontWeight: 700,
  fontSize: 17,
  color: 'var(--text-primary)',
  marginBottom: 8,
}

const modalText: React.CSSProperties = {
  fontSize: 14,
  color: 'var(--text-secondary)',
  marginBottom: 20,
  lineHeight: 1.6,
}

const modalActions: React.CSSProperties = {
  display: 'flex',
  gap: 10,
  justifyContent: 'flex-end',
}

const modalCancel: React.CSSProperties = {
  padding: '8px 18px',
  borderRadius: 8,
  border: '1px solid var(--border)',
  background: 'transparent',
  color: 'var(--text-secondary)',
  cursor: 'pointer',
  fontSize: 13,
  fontWeight: 500,
}

const modalConfirm: React.CSSProperties = {
  padding: '8px 18px',
  borderRadius: 8,
  border: 'none',
  background: 'var(--primary)',
  color: '#fff',
  cursor: 'pointer',
  fontSize: 13,
  fontWeight: 600,
}
