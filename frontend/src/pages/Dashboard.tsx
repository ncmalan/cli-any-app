import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchJson } from '../lib/api'
import type { Session } from '../lib/api'

export default function Dashboard() {
  const [sessions, setSessions] = useState<Session[]>([])

  useEffect(() => {
    fetchJson<Session[]>('/sessions').then(setSessions)
  }, [])

  return (
    <div className="max-w-4xl mx-auto p-8">
      <h1 className="text-3xl font-bold mb-8">cli-any-app</h1>
      <Link to="/session/new" className="bg-blue-600 px-4 py-2 rounded hover:bg-blue-700">
        New Session
      </Link>
      <div className="mt-8 space-y-4">
        {sessions.map(s => (
          <div key={s.id} className="bg-gray-900 p-4 rounded border border-gray-800">
            <div className="flex justify-between items-center">
              <div>
                <h2 className="font-semibold">{s.name}</h2>
                <p className="text-sm text-gray-400">{s.app_name} · {s.status}</p>
              </div>
              <Link to={s.status === 'recording' ? `/session/${s.id}/record` : `/session/${s.id}/review`}
                className="text-blue-400 hover:text-blue-300">
                {s.status === 'recording' ? 'Recording...' : 'View'}
              </Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
