/** Format a millisecond duration as m:ss, or h:mm:ss past an hour. */
export function formatDuration(ms?: number | null): string {
  if (ms === undefined || ms === null || !Number.isFinite(ms) || ms < 0) return ''
  const totalSeconds = Math.floor(ms / 1000)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  if (hours > 0) {
    return `${hours}:${pad(minutes)}:${pad(seconds)}`
  }
  return `${minutes}:${pad(seconds)}`
}
