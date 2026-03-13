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
  const [setupTab, setSetupTab] = useState<'ios' | 'android'>('ios')

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

          {/* QR Code and cert download */}
          <div className="flex gap-8 items-start mb-6">
            <div className="bg-white p-3 rounded-lg shrink-0">
              <QRCode value={`${window.location.origin}/api/cert`} size={128} />
            </div>
            <div className="space-y-2 text-sm text-gray-400">
              <p className="text-gray-200 font-medium">1. Download the CA Certificate</p>
              <p>Scan the QR code with your device camera, or open this URL in your device's browser:</p>
              <code className="block text-blue-400 bg-gray-950 px-3 py-1.5 rounded text-xs">
                {window.location.origin}/api/cert
              </code>
            </div>
          </div>

          {/* Platform tabs */}
          <div className="flex gap-1 mb-4 bg-gray-950 rounded-lg p-1 w-fit">
            <button
              onClick={() => setSetupTab('ios')}
              className={`px-4 py-1.5 rounded text-sm font-medium transition-colors ${
                setupTab === 'ios' ? 'bg-gray-700 text-white' : 'text-gray-400 hover:text-gray-300'
              }`}
            >
              iPhone / iPad
            </button>
            <button
              onClick={() => setSetupTab('android')}
              className={`px-4 py-1.5 rounded text-sm font-medium transition-colors ${
                setupTab === 'android' ? 'bg-gray-700 text-white' : 'text-gray-400 hover:text-gray-300'
              }`}
            >
              Android
            </button>
          </div>

          {setupTab === 'ios' ? (
            <div className="space-y-5 text-sm text-gray-400">
              {/* iOS Certificate */}
              <div>
                <p className="text-gray-200 font-medium mb-2">2. Install &amp; Trust the Certificate</p>
                <ol className="list-decimal list-inside space-y-1.5 ml-1">
                  <li>After downloading, go to <span className="text-gray-200">Settings &rarr; General &rarr; VPN &amp; Device Management</span></li>
                  <li>Tap the <span className="text-gray-200">mitmproxy</span> profile and tap <span className="text-gray-200">Install</span> (enter your passcode if prompted)</li>
                  <li>Go to <span className="text-gray-200">Settings &rarr; General &rarr; About &rarr; Certificate Trust Settings</span></li>
                  <li>Enable full trust for the <span className="text-gray-200">mitmproxy</span> certificate</li>
                </ol>
              </div>

              {/* iOS Proxy */}
              <div>
                <p className="text-gray-200 font-medium mb-2">3. Configure the Proxy</p>
                <ol className="list-decimal list-inside space-y-1.5 ml-1">
                  <li>Go to <span className="text-gray-200">Settings &rarr; Wi-Fi</span> and tap the <span className="text-gray-200">(i)</span> next to your connected network</li>
                  <li>Scroll down and tap <span className="text-gray-200">Configure Proxy &rarr; Manual</span></li>
                  <li>Set <span className="text-gray-200">Server</span> to the LAN IP of this machine (e.g. <code className="text-blue-400">192.168.x.x</code>)</li>
                  <li>Set <span className="text-gray-200">Port</span> to <code className="text-blue-400">8080</code> (or the port shown on the recording screen)</li>
                  <li>Tap <span className="text-gray-200">Save</span></li>
                </ol>
                <p className="mt-2 text-xs text-yellow-500/70">Remember to turn off the proxy when you're done recording, or your device will lose internet access.</p>
              </div>
            </div>
          ) : (
            <div className="space-y-5 text-sm text-gray-400">
              {/* Android Certificate */}
              <div>
                <p className="text-gray-200 font-medium mb-2">2. Install the Certificate</p>
                <ol className="list-decimal list-inside space-y-1.5 ml-1">
                  <li>After downloading the <code className="text-blue-400">.pem</code> file, go to <span className="text-gray-200">Settings &rarr; Security &rarr; Encryption &amp; credentials</span></li>
                  <li>Tap <span className="text-gray-200">Install a certificate &rarr; CA certificate</span></li>
                  <li>Tap <span className="text-gray-200">Install anyway</span> when warned</li>
                  <li>Select the downloaded <code className="text-blue-400">mitmproxy-ca-cert.pem</code> file</li>
                </ol>
                <p className="mt-2 text-xs text-gray-500">Note: On Android 7+, user-installed CA certs are only trusted by apps that explicitly opt in. Some apps may not route through the proxy. For full coverage, a rooted device with the cert installed as a system CA is needed.</p>
              </div>

              {/* Android Proxy */}
              <div>
                <p className="text-gray-200 font-medium mb-2">3. Configure the Proxy</p>
                <ol className="list-decimal list-inside space-y-1.5 ml-1">
                  <li>Go to <span className="text-gray-200">Settings &rarr; Wi-Fi</span> and long-press your connected network, then tap <span className="text-gray-200">Modify network</span></li>
                  <li>Tap <span className="text-gray-200">Advanced options</span></li>
                  <li>Set <span className="text-gray-200">Proxy</span> to <span className="text-gray-200">Manual</span></li>
                  <li>Set <span className="text-gray-200">Proxy hostname</span> to the LAN IP of this machine (e.g. <code className="text-blue-400">192.168.x.x</code>)</li>
                  <li>Set <span className="text-gray-200">Proxy port</span> to <code className="text-blue-400">8080</code> (or the port shown on the recording screen)</li>
                  <li>Tap <span className="text-gray-200">Save</span></li>
                </ol>
                <p className="mt-2 text-xs text-yellow-500/70">Remember to turn off the proxy when you're done recording, or your device will lose internet access.</p>
              </div>
            </div>
          )}
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
