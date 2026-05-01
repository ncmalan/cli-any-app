import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import { createSession } from './api'
import { server } from '../test/server'

describe('API client CSRF handling', () => {
  it('reads CSRF cookies even when cookie segments have no spaces', async () => {
    const cookieGetter = vi
      .spyOn(document, 'cookie', 'get')
      .mockReturnValue('other=value;cli_any_app_csrf=csrf-token')

    let csrfHeader = ''
    server.use(
      http.post('/api/sessions', ({ request }) => {
        csrfHeader = request.headers.get('x-csrf-token') ?? ''
        return HttpResponse.json({
          id: 's1',
          name: 'Trace',
          app_name: 'Care App',
          status: 'created',
          proxy_port: 0,
          error_message: null,
          created_at: '2026-05-01T00:00:00Z',
        }, { status: 201 })
      }),
    )

    await createSession('Trace', 'Care App')

    expect(csrfHeader).toBe('csrf-token')
    cookieGetter.mockRestore()
  })
})
