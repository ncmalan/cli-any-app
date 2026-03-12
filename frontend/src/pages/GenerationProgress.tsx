import { useEffect, useState, useRef } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getSession } from '../lib/api'
import type { Session } from '../lib/api'

const STEPS = ['Normalize', 'Analyze', 'Generate', 'Validate']

function stepIndex(status: string): number {
  switch (status) {
    case 'normalizing': return 0
    case 'analyzing': return 1
    case 'generating': return 2
    case 'validating': return 3
    case 'complete': return 4
    case 'error': return -1
    default: return 0
  }
}

export default function GenerationProgress() {
  const { id } = useParams<{ id: string }>()
  const [session, setSession] = useState<Session | null>(null)
  const [error, setError] = useState('')
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!id) return

    async function poll() {
      try {
        const s = await getSession(id!)
        setSession(s)
        if (s.status === 'complete' || s.status === 'error') {
          if (intervalRef.current) {
            clearInterval(intervalRef.current)
            intervalRef.current = null
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load session')
      }
    }

    poll()
    intervalRef.current = setInterval(poll, 2000)

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [id])

  const currentStep = session ? stepIndex(session.status) : 0
  const isComplete = session?.status === 'complete'
  const isError = session?.status === 'error'

  return (
    <div className="max-w-2xl mx-auto p-8">
      <Link to="/" className="text-blue-400 hover:text-blue-300 text-sm">
        &larr; Back to Dashboard
      </Link>
      <h1 className="text-3xl font-bold mt-4 mb-2">
        {isComplete ? 'Generation Complete' : isError ? 'Generation Failed' : 'Generating CLI...'}
      </h1>
      {session && (
        <p className="text-gray-400 mb-8">{session.name} &middot; {session.app_name}</p>
      )}

      {error && (
        <div className="text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded-lg p-3 mb-6">
          {error}
        </div>
      )}

      {/* Step indicators */}
      <div className="flex items-center mb-12">
        {STEPS.map((step, i) => {
          const isActive = i === currentStep
          const isDone = i < currentStep && !isError
          const isFailed = isError && i === currentStep

          return (
            <div key={step} className="flex-1 flex items-center">
              <div className="flex flex-col items-center flex-1">
                <div className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-medium border-2 transition-all ${
                  isDone
                    ? 'bg-green-500 border-green-500 text-white'
                    : isFailed
                    ? 'bg-red-500 border-red-500 text-white'
                    : isActive
                    ? 'border-blue-500 text-blue-400 bg-blue-500/10'
                    : 'border-gray-700 text-gray-500'
                }`}>
                  {isDone ? (
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  ) : isFailed ? (
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  ) : (
                    i + 1
                  )}
                </div>
                <span className={`text-xs mt-2 ${
                  isDone ? 'text-green-400' :
                  isFailed ? 'text-red-400' :
                  isActive ? 'text-blue-400' : 'text-gray-500'
                }`}>
                  {step}
                </span>
              </div>
              {i < STEPS.length - 1 && (
                <div className={`h-0.5 w-full mx-1 ${
                  isDone ? 'bg-green-500' : 'bg-gray-800'
                }`} />
              )}
            </div>
          )
        })}
      </div>

      {/* Status content */}
      {!isComplete && !isError && (
        <div className="text-center text-gray-400">
          <div className="inline-flex items-center gap-3">
            <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            <span>Processing... this may take a few minutes</span>
          </div>
        </div>
      )}

      {isComplete && (
        <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-6 space-y-4">
          <div className="flex items-center gap-3">
            <svg className="w-6 h-6 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <h2 className="text-lg font-semibold text-green-400">CLI Generated Successfully</h2>
          </div>
          <div className="space-y-3 text-sm">
            <div>
              <span className="text-gray-400">Output directory:</span>
              <code className="ml-2 text-gray-200 bg-gray-800 px-2 py-0.5 rounded">
                ./output/{session?.app_name}/
              </code>
            </div>
            <div className="border-t border-green-500/20 pt-3">
              <p className="text-gray-400 mb-2">To install and use:</p>
              <pre className="bg-gray-900 p-3 rounded text-gray-300 text-xs overflow-x-auto">
{`cd output/${session?.app_name}
pip install -e .
${session?.app_name} --help`}
              </pre>
            </div>
          </div>
        </div>
      )}

      {isError && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-6">
          <div className="flex items-center gap-3 mb-3">
            <svg className="w-6 h-6 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <h2 className="text-lg font-semibold text-red-400">Generation Failed</h2>
          </div>
          <p className="text-sm text-gray-400">
            An error occurred during CLI generation. Please check the server logs for details
            and try again.
          </p>
        </div>
      )}

      <div className="mt-8 text-center">
        <Link
          to="/"
          className="text-blue-400 hover:text-blue-300 text-sm"
        >
          &larr; Back to Dashboard
        </Link>
      </div>
    </div>
  )
}
