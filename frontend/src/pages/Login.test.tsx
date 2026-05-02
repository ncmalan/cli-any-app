import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import Login from './Login'
import { server } from '../test/server'

describe('Login', () => {
  it('resets submit state and clears the password after successful login', async () => {
    const onAuthenticated = vi.fn()
    server.use(
      http.post('/api/auth/login', () => HttpResponse.json({
        authenticated: true,
        username: 'local-admin',
        csrf_token: 'csrf',
      })),
    )

    render(<Login onAuthenticated={onAuthenticated} />)

    const password = screen.getByLabelText(/admin password/i)
    await userEvent.type(password, 'test-password')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(onAuthenticated).toHaveBeenCalledTimes(1))
    expect(password).toHaveValue('')
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  })
})
