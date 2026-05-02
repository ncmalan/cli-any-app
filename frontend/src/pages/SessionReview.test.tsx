import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axe } from 'jest-axe'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import SessionReview from './SessionReview'
import { server } from '../test/server'

const stoppedSession = {
  id: 's1',
  name: 'Patient lookup review',
  app_name: 'Care App',
  status: 'stopped',
  proxy_port: 8899,
  error_message: null,
  created_at: '2026-05-01T00:00:00Z',
}

function renderReview() {
  return render(
    <MemoryRouter initialEntries={['/session/s1/review']}>
      <Routes>
        <Route path="/session/:id/review" element={<SessionReview />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('SessionReview safety defaults', () => {
  it('shows redacted metadata by default and has no obvious accessibility violations', async () => {
    server.use(
      http.get('/api/sessions/s1', () => HttpResponse.json(stoppedSession)),
      http.get('/api/sessions/s1/flows', () => HttpResponse.json([
        {
          id: 'f1',
          session_id: 's1',
          label: 'Patient lookup',
          order: 1,
          started_at: '2026-05-01T00:00:00Z',
          ended_at: '2026-05-01T00:01:00Z',
        },
      ])),
      http.get('/api/sessions/s1/domains', () => HttpResponse.json([
        {
          domain: 'api.example.test',
          request_count: 1,
          api_request_count: 1,
          is_noise: false,
          enabled: true,
        },
      ])),
      http.get('/api/settings', () => HttpResponse.json({ has_key: true })),
      http.get('/api/sessions/s1/flows/f1/requests', () => HttpResponse.json([
        {
          id: 'r1',
          flow_id: 'f1',
          timestamp: '2026-05-01T00:00:10Z',
          method: 'GET',
          url: 'https://api.example.test/patients/<REDACTED>',
          request_headers: '{}',
          request_body: null,
          request_body_size: 128,
          request_body_hash: 'hash-request',
          status_code: 200,
          response_headers: '{}',
          response_body: null,
          response_body_size: 256,
          response_body_hash: 'hash-response',
          redaction_status: 'metadata_only',
          content_type: 'application/json',
          is_api: true,
        },
      ])),
    )

    const { container } = renderReview()

    expect(await screen.findByText('Metadata-first')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /patient lookup/i }))
    await userEvent.click(await screen.findByRole('button', { name: /https:\/\/api\.example\.test\/patients/i }))

    expect(await screen.findByText(/raw bodies are not stored by default/i)).toBeInTheDocument()
    expect(screen.queryByText(/jane doe/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/patient-token/i)).not.toBeInTheDocument()

    const results = await axe(container)
    expect(results.violations).toHaveLength(0)
  })

  it('gates generation on API request count returned by a domain toggle', async () => {
    server.use(
      http.get('/api/sessions/s1', () => HttpResponse.json(stoppedSession)),
      http.get('/api/sessions/s1/flows', () => HttpResponse.json([
        {
          id: 'f1',
          session_id: 's1',
          label: 'Patient lookup',
          order: 1,
          started_at: '2026-05-01T00:00:00Z',
          ended_at: '2026-05-01T00:01:00Z',
        },
      ])),
      http.get('/api/sessions/s1/domains', () => HttpResponse.json([
        {
          domain: 'api.example.test',
          request_count: 3,
          api_request_count: 0,
          is_noise: false,
          enabled: false,
        },
      ])),
      http.get('/api/settings', () => HttpResponse.json({ has_key: true })),
      http.put('/api/sessions/s1/domains/api.example.test', () => HttpResponse.json({
        domain: 'api.example.test',
        request_count: 3,
        api_request_count: 0,
        is_noise: false,
        enabled: true,
      })),
    )

    renderReview()

    const selectedRequestsLabel = await screen.findByText('Selected API requests')
    expect(selectedRequestsLabel.nextElementSibling).toHaveTextContent('0')
    expect(screen.getByText('0 API / 3 req')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /generate cli/i })).toBeDisabled()
    await userEvent.click(screen.getByRole('switch', { name: /enable api\.example\.test/i }))

    await waitFor(() => expect(selectedRequestsLabel.nextElementSibling).toHaveTextContent('0'))
    expect(screen.getByText('0 API / 3 req')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /generate cli/i })).toBeDisabled()
    expect(screen.getByRole('switch', { name: /disable api\.example\.test/i })).toBeInTheDocument()
  })
})
