import { HttpResponse, http } from 'msw'
import { afterEach, describe, expect, it } from 'vitest'
import { clearCsrfToken, createSession, login, logout } from './api'
import { server } from '../test/server'

describe('API client CSRF handling', () => {
  afterEach(() => clearCsrfToken())

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

  it('clears the CSRF token after logout', async () => {
    let csrfHeader: string | null = 'not-called'

    server.use(
      http.post('/api/auth/login', () => HttpResponse.json({
        authenticated: true,
        username: 'local-admin',
        csrf_token: 'server-issued-csrf',
      })),
      http.post('/api/auth/logout', () => HttpResponse.json({
        authenticated: false,
        username: null,
        csrf_token: null,
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
    await logout()
    await createSession('Review', 'Care App')

    expect(csrfHeader).toBeNull()
  })

  it('clears the CSRF token on authentication failure responses', async () => {
    let requestCount = 0
    let csrfHeaderAfterFailure: string | null = 'not-called'

    server.use(
      http.post('/api/auth/login', () => HttpResponse.json({
        authenticated: true,
        username: 'local-admin',
        csrf_token: 'server-issued-csrf',
      })),
      http.post('/api/sessions', ({ request }) => {
        requestCount += 1
        if (requestCount === 1) {
          return HttpResponse.json({ detail: 'Authentication required' }, { status: 401 })
        }
        csrfHeaderAfterFailure = request.headers.get('x-csrf-token')
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
    await expect(createSession('Review', 'Care App')).rejects.toThrow('401')
    await createSession('Review', 'Care App')

    expect(csrfHeaderAfterFailure).toBeNull()
  })
})
