const BASE = '/api'

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.json()
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
  status_code: number
  response_headers: string
  response_body: string | null
  content_type: string
  is_api: boolean
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
  const res = await fetch(`${BASE}/sessions/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
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
  const res = await fetch(`${BASE}/sessions/${sessionId}/flows/${flowId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
}

// Domains
export async function listDomains(sessionId: string): Promise<DomainInfo[]> {
  return fetchJson(`/sessions/${sessionId}/domains`)
}

export async function toggleDomain(sessionId: string, domain: string, enabled: boolean): Promise<DomainInfo> {
  return fetchJson(`/sessions/${sessionId}/domains/${domain}`, {
    method: 'PUT', body: JSON.stringify({ enabled })
  })
}

// Generation
export async function startGeneration(sessionId: string): Promise<void> {
  await fetchJson(`/sessions/${sessionId}/generate`, { method: 'POST' })
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
