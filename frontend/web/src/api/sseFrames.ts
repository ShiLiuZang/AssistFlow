// SSE 文本分帧（不依赖其他模块，便于单独测试）。
export type LiveEvent = Record<string, any>

/** 把一段 SSE 文本拆成事件；返回未完整的剩余部分。注释行（心跳）忽略。 */
export function parseFrames(buffer: string, onEvent: (event: LiveEvent) => void): string {
  let boundary: RegExpExecArray | null
  while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
    const frame = buffer.slice(0, boundary.index)
    buffer = buffer.slice(boundary.index + boundary[0].length)
    const data = frame
      .split(/\r?\n/)
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trimStart())
      .join('\n')
    if (!data) continue
    try {
      onEvent(JSON.parse(data))
    } catch {
      // 单条坏数据不影响后续事件
    }
  }
  return buffer
}
