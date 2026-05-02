import { render, screen, waitFor } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import GenerationProgress from './GenerationProgress'
import { server } from '../test/server'

const validationFailedSession = {
  id: 's1',
  name: 'Patient lookup review',
  app_name: 'Care App',
  status: 'validation_failed',
  proxy_port: 8899,
  error_message: 'Generated package failed validation',
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

function renderProgress() {
  return render(
    <MemoryRouter initialEntries={['/session/s1/generate']}>
      <Routes>
        <Route path="/session/:id/generate" element={<GenerationProgress />} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => {
  FakeWebSocket.instances = []
  vi.unstubAllGlobals()
})

describe('GenerationProgress status handling', () => {
  it('shows validation_failed on the Validate step and clears websocket handlers on cleanup', async () => {
    vi.stubGlobal('WebSocket', FakeWebSocket)
    server.use(
      http.get('/api/sessions/s1', () => HttpResponse.json(validationFailedSession)),
      http.get('/api/sessions/s1/status', () => HttpResponse.json({
        session_id: 's1',
        status: 'validation_failed',
        latest_attempt: {
          id: 'attempt-1',
          status: 'validation_failed',
          approval_status: 'pending',
          package_path: '/tmp/generated',
          cli_name: 'care-cli',
          validation: { valid: false, errors: ['bad import'], warnings: [] },
          created_at: '2026-05-01T00:00:00Z',
          completed_at: '2026-05-01T00:01:00Z',
        },
      })),
      http.get('/api/auth/ws-token', () => HttpResponse.json({ token: 'generation-ws-token' })),
    )

    const view = renderProgress()

    expect(await screen.findByText('Generation Needs Review')).toBeInTheDocument()
    expect(screen.getByText('Validate')).toHaveClass('text-red-400')
    await waitFor(() => {
      expect(FakeWebSocket.instances[0]?.url).toContain('/ws/generation/s1?token=generation-ws-token')
    })

    const ws = FakeWebSocket.instances[0]
    view.unmount()
    expect(ws.onopen).toBeNull()
    expect(ws.onclose).toBeNull()
    expect(ws.onmessage).toBeNull()
  })
})
