const BASE = '/api'

function csrfToken(): string {
  const match = document.cookie
    .split(';')
    .map(row => row.trim())
    .find(row => row.startsWith('cli_any_app_csrf='))
  return match ? decodeURIComponent(match.split('=')[1]) : ''
}

async function safeError(res: Response): Promise<Error> {
  try {
    const data = await res.json()
    const detail = typeof data.detail === 'string' ? data.detail : 'Request failed'
    return new Error(`${res.status}: ${detail}`)
  } catch {
    return new Error(`${res.status}: Request failed`)
  }
}

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? 'GET').toUpperCase()
  const headers = new Headers(init?.headers)
  headers.set('Content-Type', 'application/json')
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    headers.set('X-CSRF-Token', csrfToken())
  }
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    credentials: 'same-origin',
    headers,
  })
  if (!res.ok) throw await safeError(res)
  if (res.status === 204) return undefined as T
  return res.json()
}

export interface AuthStatus {
  authenticated: boolean
  username: string | null
  csrf_token: string | null
}

export interface Session {
  id: string
  name: string
  app_name: string
  status: string
  proxy_port: number
  error_message: string | null
  created_at: string
}

export interface Flow {
  id: string
  session_id: string
  label: string
  order: number
  started_at: string
  ended_at: string | null
}

export interface DomainInfo {
  domain: string
  request_count: number
  is_noise: boolean
  enabled: boolean
}

export interface TrafficEvent {
  type: string
  method: string
  url: string
  status_code: number
  content_type: string
  is_api: boolean
  domain: string
  flow_label: string
}

export interface CapturedRequest {
  id: string
  flow_id: string
  timestamp: string
  method: string
  url: string
  request_headers: string
  request_body: string | null
  request_body_size: number
  request_body_hash: string | null
  status_code: number
  response_headers: string
  response_body: string | null
  response_body_size: number
  response_body_hash: string | null
  redaction_status: string
  content_type: string
  is_api: boolean
}

export interface GenerationAttempt {
  id: string
  status: string
  approval_status: string
  package_path: string
  validation: { valid?: boolean; errors?: string[]; warnings?: string[] }
  created_at: string
  completed_at: string | null
}

export interface GenerationStatus {
  session_id: string
  status: string
  latest_attempt: GenerationAttempt | null
}

// Auth
export async function login(password: string): Promise<AuthStatus> {
  return fetchJson('/auth/login', { method: 'POST', body: JSON.stringify({ password }) })
}

export async function logout(): Promise<AuthStatus> {
  return fetchJson('/auth/logout', { method: 'POST' })
}

export async function getMe(): Promise<AuthStatus> {
  return fetchJson('/auth/me')
}

export async function getWsToken(): Promise<string> {
  const result = await fetchJson<{ token: string }>('/auth/ws-token')
  return result.token
}

// Sessions
export async function listSessions(): Promise<Session[]> {
  return fetchJson('/sessions')
}

export async function createSession(name: string, app_name: string): Promise<Session> {
  return fetchJson('/sessions', { method: 'POST', body: JSON.stringify({ name, app_name }) })
}

export async function getSession(id: string): Promise<Session> {
  return fetchJson(`/sessions/${id}`)
}

export async function deleteSession(id: string): Promise<void> {
  await fetchJson(`/sessions/${id}`, { method: 'DELETE' })
}

export async function startRecording(id: string): Promise<Session> {
  return fetchJson(`/sessions/${id}/start-recording`, { method: 'POST' })
}

export async function stopRecording(id: string): Promise<Session> {
  return fetchJson(`/sessions/${id}/stop-recording`, { method: 'POST' })
}

// Flows
export async function createFlow(sessionId: string, label: string): Promise<Flow> {
  return fetchJson(`/sessions/${sessionId}/flows`, { method: 'POST', body: JSON.stringify({ label }) })
}

export async function listFlows(sessionId: string): Promise<Flow[]> {
  return fetchJson(`/sessions/${sessionId}/flows`)
}

export async function stopFlow(sessionId: string, flowId: string): Promise<Flow> {
  return fetchJson(`/sessions/${sessionId}/flows/${flowId}/stop`, { method: 'POST' })
}

export async function deleteFlow(sessionId: string, flowId: string): Promise<void> {
  await fetchJson(`/sessions/${sessionId}/flows/${flowId}`, { method: 'DELETE' })
}

// Domains
export async function listDomains(sessionId: string): Promise<DomainInfo[]> {
  return fetchJson(`/sessions/${sessionId}/domains`)
}

export async function toggleDomain(sessionId: string, domain: string, enabled: boolean): Promise<DomainInfo> {
  return fetchJson(`/sessions/${sessionId}/domains/${encodeURIComponent(domain)}`, {
    method: 'PUT', body: JSON.stringify({ enabled })
  })
}

// Generation
export async function startGeneration(sessionId: string): Promise<void> {
  await fetchJson(`/sessions/${sessionId}/generate`, {
    method: 'POST',
    body: JSON.stringify({ reviewer_acknowledged: true }),
  })
}

export async function getGenerationStatus(sessionId: string): Promise<GenerationStatus> {
  return fetchJson(`/sessions/${sessionId}/status`)
}

export async function approveGenerationAttempt(
  sessionId: string,
  attemptId: string,
  reason: string,
): Promise<GenerationAttempt> {
  return fetchJson(`/sessions/${sessionId}/generation-attempts/${attemptId}/approve`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  })
}

// Network
export interface NetworkInterface {
  interface: string
  ip: string
}

export async function listNetworkInterfaces(): Promise<NetworkInterface[]> {
  return fetchJson('/network/interfaces')
}

// Settings
export async function getApiKeyStatus(): Promise<{ has_key: boolean }> {
  return fetchJson('/settings')
}

export async function setApiKey(api_key: string): Promise<{ has_key: boolean }> {
  return fetchJson('/settings', { method: 'PUT', body: JSON.stringify({ api_key }) })
}

// Requests (for review page)
export async function listRequests(sessionId: string, flowId: string): Promise<CapturedRequest[]> {
  return fetchJson(`/sessions/${sessionId}/flows/${flowId}/requests`)
}
