// 长连接事件流（人工坐席与顾客页面的实时推送）。
// 用 fetch 读 SSE，而不是 EventSource：这样能带 Authorization 头，令牌不进 URL。
// 断线后按 1、2、4…最长 30 秒重连；每次（重新）连上都会回调 onOpen，调用方借此重新拉取一次数据。
import { authFetch } from '../auth/session'
import { parseFrames, type LiveEvent } from './sseFrames'

export type { LiveEvent }

export interface Subscription {
  close(): void
}

export function subscribe(
  path: string,
  handlers: { onEvent: (event: LiveEvent) => void; onOpen?: () => void; onState?: (connected: boolean) => void },
): Subscription {
  let closed = false
  let controller: AbortController | undefined
  let retry = 0
  let timer: ReturnType<typeof setTimeout> | undefined

  const connect = async () => {
    if (closed) return
    controller = new AbortController()
    try {
      const response = await authFetch(path, { headers: { Accept: 'text/event-stream' }, signal: controller.signal, cache: 'no-store' })
      if (response.status === 401 || response.status === 403 || response.status === 404) {
        // 身份失效或无权访问：不重连，交给页面处理
        handlers.onState?.(false)
        return
      }
      if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`)
      retry = 0
      handlers.onState?.(true)
      handlers.onOpen?.()
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (!closed) {
        const { done, value } = await reader.read()
        if (done) break
        buffer = parseFrames(buffer + decoder.decode(value, { stream: true }), handlers.onEvent)
      }
    } catch {
      // 网络错误或主动断开，下面统一处理
    }
    if (closed) return
    handlers.onState?.(false)
    const delay = Math.min(30000, 1000 * 2 ** retry++)
    timer = setTimeout(connect, delay)
  }

  connect()
  return {
    close() {
      closed = true
      clearTimeout(timer)
      controller?.abort()
    },
  }
}
