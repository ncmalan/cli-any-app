import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import SessionSetup from './pages/SessionSetup'
import Recording from './pages/Recording'
import SessionReview from './pages/SessionReview'
import GenerationProgress from './pages/GenerationProgress'
import Login from './pages/Login'
import { getMe } from './lib/api'

export default function App() {
  const [authState, setAuthState] = useState<'checking' | 'authenticated' | 'anonymous'>('checking')

  useEffect(() => {
    getMe()
      .then(() => setAuthState('authenticated'))
      .catch(() => setAuthState('anonymous'))
  }, [])

  if (authState === 'checking') {
    return (
      <div className="min-h-screen bg-gray-950 text-gray-400 flex items-center justify-center">
        Loading...
      </div>
    )
  }

  if (authState === 'anonymous') {
    return <Login onAuthenticated={() => setAuthState('authenticated')} />
  }

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-950 text-gray-100">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/session/new" element={<SessionSetup />} />
          <Route path="/session/:id/record" element={<Recording />} />
          <Route path="/session/:id/review" element={<SessionReview />} />
          <Route path="/session/:id/generate" element={<GenerationProgress />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}
