export type ChatEvent = Record<string, any>

/** 按 SSE 帧解析，兼容任意网络分片、CRLF、命名错误事件。 */
export async function readChatStream(response: Response, onEvent: (event: ChatEvent) => void) {
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(typeof data?.detail === 'string' ? data.detail : `请求失败（${response.status}）`)
  }
  if (!response.headers.get('content-type')?.includes('text/event-stream') || !response.body) throw new Error('未收到聊天事件流')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = '', ended = false
  const consume = (frame: string) => {
    const lines = frame.split(/\r?\n/)
    const eventName = lines.find(l => l.startsWith('event:'))?.slice(6).trim()
    const payload = lines.filter(l => l.startsWith('data:')).map(l => l.slice(5).trimStart()).join('\n')
    if (!payload) return
    if (payload === '[DONE]') { ended = true; return }
    const event = JSON.parse(payload)
    if (eventName === 'error' || event.event === 'error') throw new Error(event.message || '回复生成失败')
    onEvent(event)
  }
  try {
    while (!ended) {
      const { done, value } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      let boundary: RegExpExecArray | null
      while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
        consume(buffer.slice(0, boundary.index))
        buffer = buffer.slice(boundary.index + boundary[0].length)
        if (ended) break
      }
      if (done) {
        if (buffer.trim() && !ended) consume(buffer)
        break
      }
    }
    if (!ended) throw new Error('连接提前结束，请重新读取会话确认结果')
  } finally {
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}
