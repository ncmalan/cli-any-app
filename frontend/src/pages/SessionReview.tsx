import { useEffect, useState, useCallback } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import {
  getSession, listFlows, listDomains, deleteFlow,
  toggleDomain, startGeneration, getApiKeyStatus, setApiKey, listRequests,
} from '../lib/api'
import type { Session, Flow, DomainInfo } from '../lib/api'
import MethodBadge from '../components/MethodBadge'
import StatusBadge from '../components/StatusBadge'

interface RequestDetail {
  id: string
  method: string
  url: string
  status_code: number
  content_type: string
  request_headers: string
  request_body: string | null
  request_body_size: number
  request_body_hash: string | null
  response_headers: string
  response_body: string | null
  response_body_size: number
  response_body_hash: string | null
  redaction_status: string
  is_api: boolean
}

function tryFormatJson(str: string | null): string {
  if (!str) return ''
  try {
    return JSON.stringify(JSON.parse(str), null, 2)
  } catch {
    return str
  }
}

export default function SessionReview() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [session, setSession] = useState<Session | null>(null)
  const [flows, setFlows] = useState<Flow[]>([])
  const [domains, setDomains] = useState<DomainInfo[]>([])
  const [expandedFlow, setExpandedFlow] = useState<string | null>(null)
  const [flowRequests, setFlowRequests] = useState<Record<string, RequestDetail[]>>({})
  const [deleteFlowId, setDeleteFlowId] = useState<string | null>(null)
  const [expandedRequest, setExpandedRequest] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [generating, setGenerating] = useState(false)
  const [hasApiKey, setHasApiKey] = useState(false)
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [savingKey, setSavingKey] = useState(false)
  const enabledRequestCount = domains
    .filter(domain => domain.enabled)
    .reduce((total, domain) => total + domain.request_count, 0)

  useEffect(() => {
    if (!id) return
    async function load() {
      try {
        const [s, f, d, keyStatus] = await Promise.all([
          getSession(id!),
          listFlows(id!),
          listDomains(id!),
          getApiKeyStatus(),
        ])
        setSession(s)
        setFlows(f)
        setDomains(d)
        setHasApiKey(keyStatus.has_key)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load session')
      }
    }
    load()
  }, [id])

  const handleSaveApiKey = useCallback(async () => {
    if (!apiKeyInput.trim()) return
    setSavingKey(true)
    try {
      const result = await setApiKey(apiKeyInput.trim())
      setHasApiKey(result.has_key)
      setApiKeyInput('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save API key')
    } finally {
      setSavingKey(false)
    }
  }, [apiKeyInput])

  const handleExpandFlow = useCallback(async (flowId: string) => {
    if (expandedFlow === flowId) {
      setExpandedFlow(null)
      return
    }
    setExpandedFlow(flowId)
    if (!flowRequests[flowId] && id) {
      try {
        const data = await listRequests(id, flowId)
        setFlowRequests(prev => ({ ...prev, [flowId]: data }))
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load flow requests')
      }
    }
  }, [expandedFlow, flowRequests, id])

  const handleDeleteFlow = useCallback(async (flowId: string) => {
    if (!id) return
    try {
      await deleteFlow(id, flowId)
      setFlows(prev => prev.filter(f => f.id !== flowId))
      setDeleteFlowId(null)
      if (expandedFlow === flowId) setExpandedFlow(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete flow')
    }
  }, [id, expandedFlow])

  const handleToggleDomain = useCallback(async (domain: string, enabled: boolean) => {
    if (!id) return
    try {
      const updated = await toggleDomain(id, domain, enabled)
      setDomains(prev => prev.map(d => (
        d.domain === updated.domain
          ? { ...updated, request_count: updated.request_count || d.request_count }
          : d
      )))
    } catch {
      // ignore
    }
  }, [id])

  const handleGenerate = useCallback(async () => {
    if (!id) return
    setGenerating(true)
    try {
      await startGeneration(id)
      navigate(`/session/${id}/generate`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start generation')
      setGenerating(false)
    }
  }, [id, navigate])

  return (
    <div className="max-w-6xl mx-auto p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <Link to="/" className="text-blue-400 hover:text-blue-300 text-sm">
            &larr; Back to Dashboard
          </Link>
          <div className="flex items-center gap-3 mt-2">
            <h1 className="text-3xl font-bold">{session?.name ?? 'Session Review'}</h1>
            {session && <StatusBadge status={session.status} />}
          </div>
          {session && (
            <p className="text-sm text-gray-400 mt-1">{session.app_name}</p>
          )}
        </div>
        <div className="flex flex-col items-end gap-3">
          <button
            onClick={() => navigate(`/session/${id}/record`)}
            className="px-4 py-2 text-sm border border-gray-700 rounded-lg hover:bg-gray-800 transition-colors"
          >
            + Add More Flows
          </button>
          <div className="flex flex-col items-end gap-2">
            {!hasApiKey && (
              <div className="flex items-center gap-2">
                <input
                  type="password"
                  placeholder="Anthropic API Key"
                  value={apiKeyInput}
                  onChange={e => setApiKeyInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSaveApiKey()}
                  className="bg-gray-900 border border-gray-700 rounded px-3 py-1.5 text-sm w-64 focus:outline-none focus:border-blue-500"
                />
                <button
                  onClick={handleSaveApiKey}
                  disabled={savingKey || !apiKeyInput.trim()}
                  className="bg-gray-700 px-3 py-1.5 rounded text-sm hover:bg-gray-600 transition-colors disabled:opacity-50"
                >
                  {savingKey ? 'Saving...' : 'Set Key'}
                </button>
              </div>
            )}
            {hasApiKey && (
              <span className="text-xs text-green-400">API key configured</span>
            )}
            <button
              onClick={handleGenerate}
              disabled={generating || flows.length === 0 || !hasApiKey || enabledRequestCount === 0}
              className="bg-blue-600 px-6 py-2.5 rounded-lg hover:bg-blue-700 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {generating ? 'Starting...' : 'Generate CLI'}
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div role="alert" className="text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded-lg p-3 mb-6">
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <div className="bg-gray-900 border border-gray-800 rounded p-3">
          <div className="text-xs text-gray-500">Flows</div>
          <div className="text-lg font-semibold">{flows.length}</div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded p-3">
          <div className="text-xs text-gray-500">Enabled domains</div>
          <div className="text-lg font-semibold">{domains.filter(d => d.enabled).length}</div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded p-3">
          <div className="text-xs text-gray-500">Selected requests</div>
          <div className="text-lg font-semibold">{enabledRequestCount}</div>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded p-3">
          <div className="text-xs text-gray-500">Redaction</div>
          <div className="text-sm font-medium text-green-400">Metadata-first</div>
        </div>
      </div>

      <div className="flex gap-8">
        {/* Flows panel */}
        <div className="flex-1 min-w-0">
          <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-4">
            Flows ({flows.length})
          </h2>

          {flows.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              <p>No flows captured in this session</p>
            </div>
          ) : (
            <div className="space-y-3">
              {flows.map(f => (
                <div key={f.id} className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
                  <div className="flex items-center justify-between p-4 hover:bg-gray-800/50 transition-colors">
                    <button
                      type="button"
                      className="flex min-w-0 flex-1 items-center gap-3 text-left"
                      onClick={() => handleExpandFlow(f.id)}
                      aria-expanded={expandedFlow === f.id}
                    >
                      <span className={`text-gray-500 transition-transform ${expandedFlow === f.id ? 'rotate-90' : ''}`}>
                        &#9654;
                      </span>
                      <div className="min-w-0">
                        <div className="font-medium">{f.label}</div>
                        <div className="text-xs text-gray-500">
                          Flow #{f.order}
                          {f.ended_at ? ' \u00b7 completed' : ' \u00b7 in progress'}
                        </div>
                      </div>
                    </button>
                    <div className="flex items-center gap-3">
                      {deleteFlowId === f.id ? (
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-red-400">Delete?</span>
                          <button
                            onClick={() => handleDeleteFlow(f.id)}
                            className="text-xs px-2 py-1 bg-red-600 rounded hover:bg-red-700"
                          >
                            Yes
                          </button>
                          <button
                            onClick={() => setDeleteFlowId(null)}
                            className="text-xs px-2 py-1 bg-gray-700 rounded hover:bg-gray-600"
                          >
                            No
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setDeleteFlowId(f.id)}
                          className="text-gray-500 hover:text-red-400 text-xs transition-colors"
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </div>

                  {expandedFlow === f.id && (
                    <div className="border-t border-gray-800 p-4">
                      {flowRequests[f.id] ? (
                        flowRequests[f.id].length === 0 ? (
                          <p className="text-sm text-gray-500">No requests in this flow</p>
                        ) : (
                          <div className="space-y-2">
                            {flowRequests[f.id].map(r => (
                              <div key={r.id} className="bg-gray-950 rounded border border-gray-800">
                                <button
                                  type="button"
                                  className="w-full flex items-center gap-2 p-2 text-left hover:bg-gray-900 transition-colors"
                                  onClick={() => setExpandedRequest(expandedRequest === r.id ? null : r.id)}
                                  aria-expanded={expandedRequest === r.id}
                                >
                                  <MethodBadge method={r.method} />
                                  <span className="text-sm truncate">{r.url}</span>
                                  <span className={`shrink-0 text-xs ${
                                    r.status_code >= 400 ? 'text-red-400' :
                                    r.status_code >= 300 ? 'text-yellow-400' : 'text-green-400'
                                  }`}>
                                    {r.status_code}
                                  </span>
                                </button>
                                {expandedRequest === r.id && (
                                  <div className="border-t border-gray-800 p-3 space-y-3 text-xs">
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-gray-400">
                                      <div>Request body: {r.request_body_size} bytes</div>
                                      <div>Response body: {r.response_body_size} bytes</div>
                                      <div>Redaction: {r.redaction_status}</div>
                                      <div>Content type: {r.content_type || 'unknown'}</div>
                                    </div>
                                    {r.request_body && (
                                      <div>
                                        <div className="text-gray-500 mb-1">Redacted Request Sample</div>
                                        <pre className="bg-gray-900 p-2 rounded overflow-x-auto text-gray-300 max-h-48 overflow-y-auto">
                                          {tryFormatJson(r.request_body)}
                                        </pre>
                                      </div>
                                    )}
                                    {r.response_body && (
                                      <div>
                                        <div className="text-gray-500 mb-1">Redacted Response Sample</div>
                                        <pre className="bg-gray-900 p-2 rounded overflow-x-auto text-gray-300 max-h-48 overflow-y-auto">
                                          {tryFormatJson(r.response_body)}
                                        </pre>
                                      </div>
                                    )}
                                    {!r.request_body && !r.response_body && (
                                      <p className="text-gray-500">Raw bodies are not stored by default.</p>
                                    )}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )
                      ) : (
                        <p className="text-sm text-gray-500">
                          Loading requests...
                        </p>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Domain filter sidebar */}
        <div className="w-64 shrink-0">
          <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-4">
            Domains ({domains.length})
          </h2>
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            {domains.length === 0 ? (
              <p className="text-sm text-gray-500">No domains captured</p>
            ) : (
              <>
                <div className="flex gap-2 mb-4">
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
                <div className="space-y-3">
                  {domains.map(d => (
                    <div key={d.domain} className="flex items-center justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="text-sm truncate" title={d.domain}>{d.domain}</div>
                        <div className="text-xs text-gray-500 flex items-center gap-1">
                          {d.request_count} req
                          {d.is_noise && <span className="text-yellow-500/60 ml-1">noise</span>}
                        </div>
                      </div>
                      <button
                        onClick={() => handleToggleDomain(d.domain, !d.enabled)}
                        role="switch"
                        aria-checked={d.enabled}
                        aria-label={`${d.enabled ? 'Disable' : 'Enable'} ${d.domain}`}
                        className={`w-9 h-5 rounded-full transition-colors shrink-0 ${
                          d.enabled ? 'bg-blue-600' : 'bg-gray-700'
                        }`}
                      >
                        <div className={`w-3.5 h-3.5 rounded-full bg-white transition-transform ${
                          d.enabled ? 'translate-x-4.5' : 'translate-x-0.5'
                        }`} />
                      </button>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
