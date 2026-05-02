import { useState } from 'react'
import { login } from '../lib/api'

interface LoginProps {
  onAuthenticated: () => void
}

export default function Login({ onAuthenticated }: LoginProps) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await login(password)
      setPassword('')
      onAuthenticated()
    } catch {
      setError('Authentication failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex items-center justify-center p-6">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm border border-gray-800 bg-gray-900 p-6 rounded-lg"
      >
        <h1 className="text-xl font-semibold mb-1">cli-any-app</h1>
        <p className="text-sm text-gray-400 mb-6">Local operator sign in</p>
        <label htmlFor="password" className="block text-sm font-medium text-gray-300 mb-2">
          Admin password
        </label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          autoFocus
          className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2 text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        {error && (
          <div role="alert" className="mt-4 text-sm text-red-300 bg-red-500/10 border border-red-500/30 rounded p-3">
            {error}
          </div>
        )}
        <button
          type="submit"
          disabled={submitting || !password}
          className="mt-5 w-full bg-blue-600 px-4 py-2 rounded font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          {submitting ? 'Signing in...' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
