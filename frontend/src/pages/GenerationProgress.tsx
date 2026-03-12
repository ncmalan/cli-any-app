import { Link, useParams } from 'react-router-dom'

export default function GenerationProgress() {
  const { id } = useParams()

  return (
    <div className="max-w-4xl mx-auto p-8">
      <Link to="/" className="text-blue-400 hover:text-blue-300 text-sm">&larr; Back to Dashboard</Link>
      <h1 className="text-3xl font-bold mt-4 mb-8">Generation Progress</h1>
      <p className="text-gray-400">Session {id} — CLI generation progress will be shown here.</p>
    </div>
  )
}
