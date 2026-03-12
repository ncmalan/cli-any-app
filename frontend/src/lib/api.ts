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
