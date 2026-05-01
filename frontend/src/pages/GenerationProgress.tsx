import { useEffect, useState, useRef } from 'react'
import { Link, useParams } from 'react-router-dom'
import { approveGenerationAttempt, getGenerationStatus, getSession, getWsToken } from '../lib/api'
import type { GenerationAttempt, Session } from '../lib/api'

const STEPS = ['Normalize', 'Analyze', 'Generate', 'Validate']

interface LogEntry {
  step: string
  message: string
  detail?: string | null
  timestamp: Date
}

function stepIndex(status: string): number {
  switch (status) {
    case 'normalizing': return 0
    case 'analyzing': return 1
    case 'generating': return 2
    case 'validating': return 3
    case 'complete': return 4
    case 'error': return -1
    default: return 0
  }
}

function stepFromLog(step: string): number {
  switch (step) {
    case 'normalizing': return 0
    case 'analyzing': return 1
    case 'generating': return 2
    case 'validating': return 3
    default: return -1
  }
}

function stepColor(step: string): string {
  switch (step) {
    case 'normalizing': return 'text-purple-400'
    case 'analyzing': return 'text-blue-400'
    case 'generating': return 'text-emerald-400'
    case 'validating': return 'text-yellow-400'
    case 'complete': return 'text-green-400'
    case 'error': return 'text-red-400'
    default: return 'text-gray-400'
  }
}

function stepLabel(step: string): string {
  switch (step) {
    case 'normalizing': return 'NORMALIZE'
    case 'analyzing': return 'ANALYZE'
    case 'generating': return 'GENERATE'
    case 'validating': return 'VALIDATE'
    case 'complete': return 'DONE'
    case 'error': return 'ERROR'
    case 'starting': return 'START'
    default: return step.toUpperCase()
  }
}

export default function GenerationProgress() {
  const { id } = useParams<{ id: string }>()
  const [session, setSession] = useState<Session | null>(null)
  const [error, setError] = useState('')
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [activeStep, setActiveStep] = useState(0)
  const [wsState, setWsState] = useState<'connecting' | 'connected' | 'disconnected'>('connecting')
  const [latestAttempt, setLatestAttempt] = useState<GenerationAttempt | null>(null)
  const [approvalReason, setApprovalReason] = useState('')
  const [approving, setApproving] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const logRef = useRef<HTMLDivElement>(null)

  // Poll session status
  useEffect(() => {
    if (!id) return

    async function poll() {
      try {
        const [s, status] = await Promise.all([getSession(id!), getGenerationStatus(id!)])
        setSession(s)
        setLatestAttempt(status.latest_attempt)
        if (['complete', 'error', 'validation_failed'].includes(s.status)) {
          if (intervalRef.current) {
            clearInterval(intervalRef.current)
            intervalRef.current = null
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load session')
      }
    }

    poll()
    intervalRef.current = setInterval(poll, 2000)

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [id])

  // WebSocket for live progress
  useEffect(() => {
    if (!id) return
    let cancelled = false
    async function connect() {
      setWsState('connecting')
      try {
        const token = await getWsToken()
        if (cancelled) return
        const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const ws = new WebSocket(`${proto}//${window.location.host}/ws/generation/${id}?token=${encodeURIComponent(token)}`)
        wsRef.current = ws
        ws.onopen = () => setWsState('connected')
        ws.onclose = () => setWsState('disconnected')
        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            const entry: LogEntry = {
              step: data.step,
              message: data.message,
              detail: data.detail,
              timestamp: new Date(),
            }
            setLogs(prev => [...prev.slice(-499), entry])

            const idx = stepFromLog(data.step)
            if (idx >= 0) setActiveStep(idx)
          } catch {
            // ignore parse errors
          }
        }
      } catch {
        setWsState('disconnected')
      }
    }
    connect()
    return () => {
      cancelled = true
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [id])

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [logs])

  const currentStep = session ? stepIndex(session.status) : activeStep
  const isComplete = session?.status === 'complete'
  const isError = session?.status === 'error' || session?.status === 'validation_failed'
  const isApproved = latestAttempt?.approval_status === 'approved'
  const isApprovalPending = isComplete && latestAttempt && !isApproved
  const installPackagePath = latestAttempt?.package_path || 'data/generated/...'
  const installCliName = latestAttempt?.cli_name || 'generated-cli'

  async function handleApprove() {
    if (!id || !latestAttempt || !approvalReason.trim()) return
    setApproving(true)
    setError('')
    try {
      const approved = await approveGenerationAttempt(id, latestAttempt.id, approvalReason.trim())
      setLatestAttempt(approved)
      setApprovalReason('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to approve generated package')
    } finally {
      setApproving(false)
    }
  }

  return (
    <div className="max-w-3xl mx-auto p-8">
      <Link to="/" className="text-blue-400 hover:text-blue-300 text-sm">
        &larr; Back to Dashboard
      </Link>
      <h1 className="text-3xl font-bold mt-4 mb-2">
        {isComplete ? 'Generation Complete' : isError ? 'Generation Needs Review' : 'Generating CLI...'}
      </h1>
      {session && (
        <p className="text-gray-400 mb-8">{session.name} &middot; {session.app_name}</p>
      )}

      {error && (
        <div role="alert" className="text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded-lg p-3 mb-6">
          {error}
        </div>
      )}

      {/* Step indicators */}
      <div className="flex items-center mb-8">
        {STEPS.map((step, i) => {
          const isActive = i === currentStep
          const isDone = i < currentStep && !isError
          const isFailed = isError && i === currentStep

          return (
            <div key={step} className="flex-1 flex items-center">
              <div className="flex flex-col items-center flex-1">
                <div className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-medium border-2 transition-all ${
                  isDone
                    ? 'bg-green-500 border-green-500 text-white'
                    : isFailed
                    ? 'bg-red-500 border-red-500 text-white'
                    : isActive
                    ? 'border-blue-500 text-blue-400 bg-blue-500/10'
                    : 'border-gray-700 text-gray-500'
                }`}>
                  {isDone ? (
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  ) : isFailed ? (
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  ) : isActive && !isComplete ? (
                    <div className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                  ) : (
                    i + 1
                  )}
                </div>
                <span className={`text-xs mt-2 ${
                  isDone ? 'text-green-400' :
                  isFailed ? 'text-red-400' :
                  isActive ? 'text-blue-400' : 'text-gray-500'
                }`}>
                  {step}
                </span>
              </div>
              {i < STEPS.length - 1 && (
                <div className={`h-0.5 w-full mx-1 ${
                  isDone ? 'bg-green-500' : 'bg-gray-800'
                }`} />
              )}
            </div>
          )
        })}
      </div>

      {/* Live log */}
      <div className="bg-gray-950 border border-gray-800 rounded-lg overflow-hidden">
        <div className="px-4 py-2 border-b border-gray-800 flex items-center justify-between">
          <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider">Live Progress</h2>
          {!isComplete && !isError && (
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
              <span className="text-xs text-gray-500">{wsState}</span>
            </div>
          )}
        </div>
        <div
          ref={logRef}
          className="p-4 h-80 overflow-y-auto font-mono text-sm space-y-1"
        >
          {logs.length === 0 && !isComplete && !isError && (
            <div className="text-gray-600 text-center py-8">
              Connecting to generation pipeline...
            </div>
          )}
          {logs.map((entry, i) => (
            <div key={i} className="flex gap-2">
              <span className="text-gray-600 shrink-0 text-xs leading-5">
                {entry.timestamp.toLocaleTimeString()}
              </span>
              <span className={`shrink-0 text-xs font-medium leading-5 w-20 ${stepColor(entry.step)}`}>
                [{stepLabel(entry.step)}]
              </span>
              <span className="text-gray-300 leading-5">{entry.message}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Result sections */}
      {isComplete && (
        <div className="mt-6 bg-green-500/10 border border-green-500/20 rounded-lg p-6 space-y-4">
          <div className="flex items-center gap-3">
            <svg className="w-6 h-6 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <h2 className="text-lg font-semibold text-green-400">CLI Generated Successfully</h2>
          </div>
          <div className="space-y-3 text-sm">
            <div>
              <span className="text-gray-400">Output directory:</span>
              <code className="ml-2 text-gray-200 bg-gray-800 px-2 py-0.5 rounded">
                {latestAttempt?.package_path || './data/generated/...'}
              </code>
            </div>
            {isApprovalPending && (
              <div className="border-t border-green-500/20 pt-3 space-y-3">
                <p className="text-gray-300">Approval is required before install instructions are shown.</p>
                <label htmlFor="approval_reason" className="block text-xs text-gray-500">
                  Approval reason
                </label>
                <input
                  id="approval_reason"
                  value={approvalReason}
                  onChange={e => setApprovalReason(e.target.value)}
                  className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2 text-gray-100 focus:outline-none focus:ring-2 focus:ring-green-500"
                />
                <button
                  onClick={handleApprove}
                  disabled={approving || !approvalReason.trim()}
                  className="bg-green-600 px-4 py-2 rounded text-sm font-medium hover:bg-green-700 disabled:opacity-50"
                >
                  {approving ? 'Approving...' : 'Approve Generated Package'}
                </button>
              </div>
            )}
            {isApproved && (
              <div className="border-t border-green-500/20 pt-3">
              <p className="text-gray-400 mb-2">To install and use:</p>
              <pre className="bg-gray-900 p-3 rounded text-gray-300 text-xs overflow-x-auto">
{`cd ${installPackagePath}
pip install -e .
${installCliName} --help`}
              </pre>
              </div>
            )}
          </div>
        </div>
      )}

      {isError && (
        <div className="mt-6 bg-red-500/10 border border-red-500/20 rounded-lg p-6">
          <div className="flex items-center gap-3 mb-3">
            <svg className="w-6 h-6 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <h2 className="text-lg font-semibold text-red-400">Generation Failed</h2>
          </div>
          {session?.error_message ? (
            <pre className="text-sm text-red-300 bg-red-950/50 p-3 rounded overflow-x-auto whitespace-pre-wrap mb-3">
              {session.error_message}
            </pre>
          ) : (
            <p className="text-sm text-gray-400 mb-3">
              An error occurred during CLI generation.
            </p>
          )}
          <Link
            to={`/session/${id}/review`}
            className="text-sm text-blue-400 hover:text-blue-300"
          >
            Back to review to retry
          </Link>
        </div>
      )}

      <div className="mt-8 text-center">
        <Link
          to="/"
          className="text-blue-400 hover:text-blue-300 text-sm"
        >
          &larr; Back to Dashboard
        </Link>
      </div>
    </div>
  )
}
