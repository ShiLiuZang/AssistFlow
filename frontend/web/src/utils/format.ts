// 显示格式化。缺失值统一显示"—"，不补 0。

export const DASH = '—'

const numberFmt = new Intl.NumberFormat('zh-CN')
const dateTimeFmt = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
})
const timeFmt = new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })

export const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)

export function num(v: unknown): string {
  return isNum(v) ? numberFmt.format(v) : v === null || v === undefined || v === '' ? DASH : String(v)
}

export function pct(v: unknown, digits = 1): string {
  return isNum(v) ? `${(v * 100).toFixed(digits)}%` : DASH
}

export function fixed(v: unknown, digits = 3): string {
  return isNum(v) ? v.toFixed(digits) : DASH
}

export function dateTime(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === '') return DASH
  const d = typeof v === 'number' ? new Date(v < 1e12 ? v * 1000 : v) : new Date(v)
  return Number.isNaN(d.getTime()) ? String(v) : dateTimeFmt.format(d)
}

export function clock(ms: number | undefined): string {
  return ms ? timeFmt.format(ms) : DASH
}

export function bytes(v: unknown): string {
  if (!isNum(v)) return DASH
  if (v < 1024) return `${v} B`
  if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB`
  return `${(v / 1024 / 1024).toFixed(1)} MB`
}
