import { useEffect, useRef, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  getSession, startRecording, stopRecording,
  createFlow, stopFlow, listFlows, listDomains, toggleDomain,
} from '../lib/api'
import type { Session, Flow, DomainInfo, TrafficEvent } from '../lib/api'
import MethodBadge from '../components/MethodBadge'

export default function Recording() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [session, setSession] = useState<Session | null>(null)
  const [flows, setFlows] = useState<Flow[]>([])
  const [activeFlow, setActiveFlow] = useState<Flow | null>(null)
  const [traffic, setTraffic] = useState<TrafficEvent[]>([])
  const [domains, setDomains] = useState<DomainInfo[]>([])
  const [showDomains, setShowDomains] = useState(false)
  const [flowInput, setFlowInput] = useState('')
  const [showFlowInput, setShowFlowInput] = useState(false)
  const [error, setError] = useState('')

  const trafficRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)

  // Load session and start recording
  useEffect(() => {
    if (!id) return
    async function init() {
      try {
        let s = await getSession(id!)
        if (s.status === 'created' || s.status === 'stopped') {
          s = await startRecording(id!)
        }
        setSession(s)
        const flowList = await listFlows(id!)
        setFlows(flowList)
        const active = flowList.find(f => !f.ended_at)
        if (active) setActiveFlow(active)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load session')
      }
    }
    init()
  }, [id])

  // WebSocket connection
  useEffect(() => {
    if (!id) return
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/traffic/${id}`)
    wsRef.current = ws

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as TrafficEvent
        setTraffic(prev => [...prev, data])
      } catch {
        // ignore parse errors
      }
    }

    ws.onerror = () => {
      // silently handle
    }

    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [id])

  // Auto-scroll traffic feed
  useEffect(() => {
    if (trafficRef.current) {
      trafficRef.current.scrollTop = trafficRef.current.scrollHeight
    }
  }, [traffic])

  // Load domains periodically
  useEffect(() => {
    if (!id) return
    const interval = setInterval(async () => {
      try {
        const d = await listDomains(id!)
        setDomains(d)
      } catch {
        // ignore
      }
    }, 5000)
    // Initial load
    listDomains(id!).then(setDomains).catch(() => {})
    return () => clearInterval(interval)
  }, [id])

  const handleStartFlow = useCallback(async () => {
    if (!id || !flowInput.trim()) return
    try {
      const flow = await createFlow(id, flowInput.trim())
      setActiveFlow(flow)
      setFlows(prev => [...prev, flow])
      setFlowInput('')
      setShowFlowInput(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create flow')
    }
  }, [id, flowInput])

  const handleStopFlow = useCallback(async () => {
    if (!id || !activeFlow) return
    try {
      const updated = await stopFlow(id, activeFlow.id)
      setActiveFlow(null)
      setFlows(prev => prev.map(f => f.id === updated.id ? updated : f))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to stop flow')
    }
  }, [id, activeFlow])

  const handleStopRecording = useCallback(async () => {
    if (!id) return
    try {
      if (activeFlow) {
        await stopFlow(id, activeFlow.id)
      }
      await stopRecording(id)
      navigate(`/session/${id}/review`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to stop recording')
    }
  }, [id, activeFlow, navigate])

  const handleToggleDomain = useCallback(async (domain: string, enabled: boolean) => {
    if (!id) return
    try {
      const updated = await toggleDomain(id, domain, enabled)
      setDomains(prev => prev.map(d => d.domain === updated.domain ? updated : d))
    } catch {
      // ignore
    }
  }, [id])

  if (error && !session) {
    return (
      <div className="max-w-4xl mx-auto p-8">
        <div className="text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg p-4">{error}</div>
      </div>
    )
  }

  return (
    <div className="h-screen flex flex-col">
      {/* Top bar */}
      <div className="flex items-center justify-between px-6 py-3 bg-gray-900 border-b border-gray-800 shrink-0">
        <div className="flex items-center gap-4">
          <span className="w-2.5 h-2.5 rounded-full bg-green-500 animate-pulse" />
          <h1 className="font-semibold text-lg">{session?.name ?? 'Loading...'}</h1>
          {session && (
            <span className="text-sm text-gray-400">
              {session.app_name} &middot; proxy :{session.proxy_port}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowDomains(!showDomains)}
            className="px-3 py-1.5 text-sm border border-gray-700 rounded hover:bg-gray-800 transition-colors"
          >
            Domains {domains.length > 0 && `(${domains.length})`}
          </button>
          <button
            onClick={handleStopRecording}
            className="px-4 py-1.5 text-sm bg-red-600 rounded hover:bg-red-700 transition-colors font-medium"
          >
            Stop Recording
          </button>
        </div>
      </div>

      {error && (
        <div className="mx-6 mt-3 text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded p-2">
          {error}
        </div>
      )}

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left panel: Flow controls */}
        <div className="w-80 border-r border-gray-800 flex flex-col shrink-0">
          <div className="p-4 border-b border-gray-800">
            <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-3">Flows</h2>

            {activeFlow ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2 bg-green-500/10 border border-green-500/20 rounded-lg p-3">
                  <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse shrink-0" />
                  <span className="text-sm font-medium text-green-400 truncate">{activeFlow.label}</span>
                </div>
                <button
                  onClick={handleStopFlow}
                  className="w-full px-3 py-2 text-sm bg-gray-800 border border-gray-700 rounded-lg hover:bg-gray-700 transition-colors"
                >
                  Stop Flow
                </button>
              </div>
            ) : showFlowInput ? (
              <div className="space-y-2">
                <input
                  type="text"
                  value={flowInput}
                  onChange={e => setFlowInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleStartFlow()}
                  placeholder="Flow label (e.g. Login)"
                  autoFocus
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500"
                />
                <div className="flex gap-2">
                  <button
                    onClick={handleStartFlow}
                    disabled={!flowInput.trim()}
                    className="flex-1 px-3 py-2 text-sm bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
                  >
                    Start
                  </button>
                  <button
                    onClick={() => { setShowFlowInput(false); setFlowInput('') }}
                    className="px-3 py-2 text-sm bg-gray-800 border border-gray-700 rounded-lg hover:bg-gray-700 transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setShowFlowInput(true)}
                className="w-full px-3 py-2 text-sm bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors font-medium"
              >
                + Start Flow
              </button>
            )}
          </div>

          {/* Completed flows */}
          <div className="flex-1 overflow-y-auto p-4 space-y-2">
            {flows.filter(f => f.ended_at).map(f => (
              <div key={f.id} className="bg-gray-900 border border-gray-800 rounded-lg p-3">
                <div className="text-sm font-medium">{f.label}</div>
                <div className="text-xs text-gray-500 mt-1">
                  Flow #{f.order}
                  {f.ended_at && ` \u00b7 completed`}
                </div>
              </div>
            ))}
            {flows.filter(f => f.ended_at).length === 0 && (
              <p className="text-xs text-gray-600 text-center py-4">
                No completed flows yet
              </p>
            )}
          </div>
        </div>

        {/* Right panel: Live traffic */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="px-4 py-2 border-b border-gray-800 flex items-center justify-between">
            <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider">
              Live Traffic
            </h2>
            <span className="text-xs text-gray-500">{traffic.length} requests</span>
          </div>
          <div ref={trafficRef} className="flex-1 overflow-y-auto p-2 space-y-0.5 font-mono text-sm">
            {traffic.length === 0 ? (
              <div className="text-center py-12 text-gray-600">
                <p>Waiting for traffic...</p>
                <p className="text-xs mt-1">Configure your device to use the proxy</p>
              </div>
            ) : (
              traffic.map((t, i) => (
                <div
                  key={i}
                  className={`flex items-center gap-2 px-2 py-1 rounded ${
                    t.is_api ? 'hover:bg-gray-900' : 'opacity-40 hover:bg-gray-900/50'
                  }`}
                >
                  <MethodBadge method={t.method} />
                  <span className={`truncate ${t.is_api ? 'text-gray-200' : 'text-gray-500'}`}>
                    {t.url}
                  </span>
                  <span className={`shrink-0 text-xs ${
                    t.status_code >= 400 ? 'text-red-400' :
                    t.status_code >= 300 ? 'text-yellow-400' : 'text-green-400'
                  }`}>
                    {t.status_code}
                  </span>
                  <span className="shrink-0 text-xs text-gray-600 hidden lg:inline">
                    {t.content_type.split(';')[0]}
                  </span>
                  {t.flow_label && (
                    <span className="shrink-0 text-xs text-blue-400/60 hidden xl:inline">
                      [{t.flow_label}]
                    </span>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        {/* Domain sidebar */}
        {showDomains && (
          <div className="w-72 border-l border-gray-800 flex flex-col shrink-0">
            <div className="p-4 border-b border-gray-800">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider">Domains</h2>
                <button
                  onClick={() => setShowDomains(false)}
                  className="text-gray-500 hover:text-gray-300 text-xs"
                >
                  Close
                </button>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => domains.forEach(d => handleToggleDomain(d.domain, true))}
                  className="text-xs text-blue-400 hover:text-blue-300"
                >
                  Select All
                </button>
                <span className="text-gray-600">|</span>
                <button
                  onClick={() => domains.forEach(d => handleToggleDomain(d.domain, false))}
                  className="text-xs text-blue-400 hover:text-blue-300"
                >
                  Deselect All
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {domains.length === 0 ? (
                <p className="text-xs text-gray-600 text-center py-4">No domains captured yet</p>
              ) : (
                domains.map(d => (
                  <div key={d.domain} className="flex items-center justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="text-sm truncate" title={d.domain}>
                        {d.domain}
                      </div>
                      <div className="text-xs text-gray-500 flex items-center gap-1">
                        {d.request_count} req
                        {d.is_noise && (
                          <span className="text-yellow-500/60 ml-1">noise</span>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={() => handleToggleDomain(d.domain, !d.enabled)}
                      className={`w-9 h-5 rounded-full transition-colors shrink-0 ${
                        d.enabled ? 'bg-blue-600' : 'bg-gray-700'
                      }`}
                    >
                      <div className={`w-3.5 h-3.5 rounded-full bg-white transition-transform ${
                        d.enabled ? 'translate-x-4.5' : 'translate-x-0.5'
                      }`} />
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
