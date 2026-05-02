import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import App from './App'
import { server } from './test/server'

describe('App auth gate', () => {
  it('requires local operator login before rendering the dashboard', async () => {
    server.use(
      http.get('/api/auth/me', () => HttpResponse.json({ detail: 'Authentication required' }, { status: 401 })),
      http.post('/api/auth/login', () => HttpResponse.json({
        authenticated: true,
        username: 'local-admin',
        csrf_token: 'csrf',
      })),
      http.get('/api/sessions', () => HttpResponse.json([])),
    )

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'cli-any-app' })).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText(/admin password/i), 'test-password')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByRole('link', { name: /\+ new session/i })).toBeInTheDocument()
  })
})
