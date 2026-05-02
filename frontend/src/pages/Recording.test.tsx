import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Recording from './Recording'
import { server } from '../test/server'

const baseSession = {
  id: 's1',
  name: 'Regulated trace',
  app_name: 'Care App',
  status: 'created',
  proxy_port: 0,
  error_message: null,
  created_at: '2026-05-01T00:00:00Z',
}

class FakeWebSocket {
  static instances: FakeWebSocket[] = []

  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onmessage: ((event: MessageEvent<string>) => void) | null = null
  readonly url: string

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
    queueMicrotask(() => this.onopen?.())
  }

  close() {
    this.onclose?.()
  }
}

function renderRecording() {
  return render(
    <MemoryRouter initialEntries={['/session/s1/record']}>
      <Routes>
        <Route path="/session/:id/record" element={<Recording />} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => {
  FakeWebSocket.instances = []
  vi.unstubAllGlobals()
})

describe('Recording regulated capture workflow', () => {
  it('does not start capture on route load and requires the explicit Start Capture action', async () => {
    let startCalls = 0
    vi.stubGlobal('WebSocket', FakeWebSocket)
    server.use(
      http.get('/api/sessions/s1', () => HttpResponse.json(baseSession)),
      http.get('/api/sessions/s1/flows', () => HttpResponse.json([])),
      http.get('/api/sessions/s1/domains', () => HttpResponse.json([])),
      http.get('/api/auth/ws-token', () => HttpResponse.json({ token: 'ws-test-token' })),
      http.post('/api/sessions/s1/start-recording', () => {
        startCalls += 1
        return HttpResponse.json({ ...baseSession, status: 'recording', proxy_port: 8899 })
      }),
    )

    const view = renderRecording()

    expect(await screen.findByText(/capture is stopped/i)).toBeInTheDocument()
    expect(startCalls).toBe(0)

    await userEvent.click(screen.getByRole('button', { name: /start capture/i }))

    await waitFor(() => expect(startCalls).toBe(1))
    expect(await screen.findByRole('button', { name: /stop recording/i })).toBeInTheDocument()
    await waitFor(() => {
      expect(FakeWebSocket.instances[0]?.url).toContain('/ws/traffic/s1?token=ws-test-token')
    })

    const ws = FakeWebSocket.instances[0]
    view.unmount()
    expect(ws.onopen).toBeNull()
    expect(ws.onclose).toBeNull()
    expect(ws.onmessage).toBeNull()
  })
})
