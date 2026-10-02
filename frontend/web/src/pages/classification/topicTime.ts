// history_topics 保存无时区 UTC；沿用原主题页把该接口时间按 UTC 解释的约定。
// 只在展示时换算，避免把 04:08 UTC 直接显示成北京时间 04:08。
export function topicTime(value?: string | null, short = false): string {
  if (!value) return '—'
  const iso = value.replace(' ', 'T')
  const date = new Date(/(Z|[+-]\d{2}:\d{2})$/i.test(iso) ? iso : iso + 'Z')
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Singapore',
    ...(short ? {} : { year: 'numeric' as const }),
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(date)
}
