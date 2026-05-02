import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { createSession } from '../lib/api'

export default function SessionSetup() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [appName, setAppName] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim() || !appName.trim()) {
      setError('Both fields are required')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      const session = await createSession(name.trim(), appName.trim())
      navigate(`/session/${session.id}/record`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create session')
      setSubmitting(false)
    }
  }

  return (
    <div className="max-w-lg mx-auto p-8">
      <Link to="/" className="text-blue-400 hover:text-blue-300 text-sm">
        &larr; Back to Dashboard
      </Link>
      <h1 className="text-3xl font-bold mt-4 mb-8">New Session</h1>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <label htmlFor="name" className="block text-sm font-medium text-gray-300 mb-2">
            Session Name
          </label>
          <input
            id="name"
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="e.g. Capture login + checkout flow"
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2.5 text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          />
        </div>

        <div>
          <label htmlFor="app_name" className="block text-sm font-medium text-gray-300 mb-2">
            App Name
          </label>
          <input
            id="app_name"
            type="text"
            value={appName}
            onChange={e => setAppName(e.target.value)}
            placeholder="e.g. my-saas-tool"
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2.5 text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          />
          <p className="text-xs text-gray-500 mt-1">This will be used as the CLI tool name</p>
        </div>

        {error && (
          <div className="text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded-lg p-3">
            {error}
          </div>
        )}

        <div className="flex gap-3 pt-2">
          <button
            type="submit"
            disabled={submitting}
            className="bg-blue-600 px-6 py-2.5 rounded-lg hover:bg-blue-700 transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? 'Creating...' : 'Create Session'}
          </button>
          <Link
            to="/"
            className="px-6 py-2.5 rounded-lg border border-gray-700 text-gray-300 hover:bg-gray-800 transition-colors"
          >
            Cancel
          </Link>
        </div>
      </form>
    </div>
  )
}
