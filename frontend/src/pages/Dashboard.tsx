import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listSessions, deleteSession } from '../lib/api'
import type { Session } from '../lib/api'
import StatusBadge from '../components/StatusBadge'
import QRCode from 'react-qr-code'

function sessionLink(s: Session): string {
  switch (s.status) {
    case 'recording': return `/session/${s.id}/record`
    case 'generating':
    case 'complete':
    case 'error':
      return `/session/${s.id}/generate`
    default: return `/session/${s.id}/review`
  }
}

function sessionAction(status: string): string {
  switch (status) {
    case 'recording': return 'Recording...'
    case 'generating': return 'Generating...'
    case 'complete': return 'View Result'
    default: return 'Review'
  }
}

export default function Dashboard() {
  const [sessions, setSessions] = useState<Session[]>([])
  const [loading, setLoading] = useState(true)
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const [showSetup, setShowSetup] = useState(false)

  async function load() {
    try {
      const data = await listSessions()
      setSessions(data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function handleDelete(id: string) {
    await deleteSession(id)
    setDeleteId(null)
    setSessions(prev => prev.filter(s => s.id !== id))
  }

  return (
    <div className="max-w-5xl mx-auto p-8">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold">cli-any-app</h1>
        <div className="flex gap-3">
          <button
            onClick={() => setShowSetup(!showSetup)}
            className="px-4 py-2 rounded border border-gray-700 text-gray-300 hover:bg-gray-800 transition-colors"
          >
            {showSetup ? 'Hide' : 'Device'} Setup
          </button>
          <Link
            to="/session/new"
            className="bg-blue-600 px-4 py-2 rounded hover:bg-blue-700 transition-colors font-medium"
          >
            + New Session
          </Link>
        </div>
      </div>

      {showSetup && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 mb-8">
          <h2 className="text-lg font-semibold mb-4">Device Setup</h2>
          <div className="flex gap-8 items-start">
            <div className="bg-white p-3 rounded-lg shrink-0">
              <QRCode value={`${window.location.origin}/api/cert`} size={128} />
            </div>
            <div className="space-y-3 text-sm text-gray-400">
              <p className="text-gray-200 font-medium">To capture HTTPS traffic from your device:</p>
              <ol className="list-decimal list-inside space-y-2">
                <li>Scan the QR code or visit <code className="text-blue-400">/api/cert</code> to download the CA certificate</li>
                <li>Install and trust the certificate on your device</li>
                <li>Configure your device to use this machine as HTTP proxy</li>
                <li>The proxy port will be shown when you start recording a session</li>
              </ol>
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-gray-400 text-center py-12">Loading sessions...</div>
      ) : sessions.length === 0 ? (
        <div className="text-center py-16 text-gray-500">
          <p className="text-lg mb-2">No sessions yet</p>
          <p className="text-sm">Create a new session to start capturing API traffic</p>
        </div>
      ) : (
        <div className="space-y-3">
          {sessions.map(s => (
            <div key={s.id} className="bg-gray-900 p-4 rounded-lg border border-gray-800 hover:border-gray-700 transition-colors">
              <div className="flex justify-between items-center">
                <div className="flex items-center gap-4">
                  <div>
                    <div className="flex items-center gap-3">
                      <h2 className="font-semibold">{s.name}</h2>
                      <StatusBadge status={s.status} />
                    </div>
                    <p className="text-sm text-gray-400 mt-1">
                      {s.app_name}
                      {s.proxy_port ? ` \u00b7 proxy :${s.proxy_port}` : ''}
                      {' \u00b7 '}
                      {new Date(s.created_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <Link
                    to={sessionLink(s)}
                    className="text-blue-400 hover:text-blue-300 text-sm font-medium"
                  >
                    {sessionAction(s.status)}
                  </Link>
                  {deleteId === s.id ? (
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-red-400">Delete?</span>
                      <button
                        onClick={() => handleDelete(s.id)}
                        className="text-xs px-2 py-1 bg-red-600 rounded hover:bg-red-700"
                      >
                        Yes
                      </button>
                      <button
                        onClick={() => setDeleteId(null)}
                        className="text-xs px-2 py-1 bg-gray-700 rounded hover:bg-gray-600"
                      >
                        No
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setDeleteId(s.id)}
                      className="text-gray-500 hover:text-red-400 text-sm transition-colors"
                      title="Delete session"
                    >
                      Delete
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
