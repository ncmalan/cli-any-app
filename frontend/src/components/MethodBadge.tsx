const methodColors: Record<string, string> = {
  GET: 'bg-green-500/20 text-green-400',
  POST: 'bg-blue-500/20 text-blue-400',
  PUT: 'bg-yellow-500/20 text-yellow-400',
  PATCH: 'bg-orange-500/20 text-orange-400',
  DELETE: 'bg-red-500/20 text-red-400',
}

export default function MethodBadge({ method }: { method: string }) {
  const cls = methodColors[method.toUpperCase()] ?? 'bg-gray-500/20 text-gray-400'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-bold ${cls}`}>
      {method.toUpperCase()}
    </span>
  )
}
