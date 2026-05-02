import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'
import { createSession, login } from './api'
import { server } from '../test/server'

describe('API client CSRF handling', () => {
  it('sends the server-issued CSRF token on state-changing requests', async () => {
    let csrfHeader: string | null = null

    server.use(
      http.post('/api/auth/login', () => HttpResponse.json({
        authenticated: true,
        username: 'local-admin',
        csrf_token: 'server-issued-csrf',
      })),
      http.post('/api/sessions', ({ request }) => {
        csrfHeader = request.headers.get('x-csrf-token')
        return HttpResponse.json({
          id: 's1',
          name: 'Review',
          app_name: 'Care App',
          status: 'created',
          proxy_port: 8899,
          error_message: null,
          created_at: '2026-05-01T00:00:00Z',
        })
      }),
    )

    await login('test-password')
    await createSession('Review', 'Care App')

    expect(csrfHeader).toBe('server-issued-csrf')
  })
})
