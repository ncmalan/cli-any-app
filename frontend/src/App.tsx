import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import SessionSetup from './pages/SessionSetup'
import Recording from './pages/Recording'
import SessionReview from './pages/SessionReview'
import GenerationProgress from './pages/GenerationProgress'

export default function App() {
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
