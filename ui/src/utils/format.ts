export function formatTime(dateStr: string): string {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 1) return '刚刚'
    if (diffMins < 60) return diffMins + '分钟前'
    if (diffHours < 24) return diffHours + '小时前'
    if (diffDays < 7) return diffDays + '天前'
    return date.toLocaleDateString('zh-CN')
  } catch {
    return dateStr
  }
}

export function truncate(s: string, maxLen: number): string {
  if (!s) return '(空)'
  return s.length > maxLen ? s.slice(0, maxLen) + '...' : s
}

export function formatValue(v: unknown): string {
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(4)
  return String(v)
}

export function truncateTool(output: string, maxLen = 200): string {
  if (!output) return '(empty)'
  return output.length > maxLen ? output.slice(0, maxLen) + '...' : output
}

export function formatToolInput(input: Record<string, unknown>): string {
  if (!input || Object.keys(input).length === 0) return '{}'
  return JSON.stringify(input, null, 2)
}
