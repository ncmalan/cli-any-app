const statusColors: Record<string, string> = {
  recording: 'bg-green-500/20 text-green-400 border-green-500/30',
  stopped: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
  generating: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  complete: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  error: 'bg-red-500/20 text-red-400 border-red-500/30',
}

export default function StatusBadge({ status }: { status: string }) {
  const cls = statusColors[status] ?? statusColors.stopped
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${cls}`}>
      {status === 'recording' && (
        <span className="w-1.5 h-1.5 rounded-full bg-green-400 mr-1.5 animate-pulse" />
      )}
      {status}
    </span>
  )
}
