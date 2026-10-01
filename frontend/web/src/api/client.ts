// 统一请求：超时、错误信息都在这里处理，页面只管拿数据。

export class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
  ) {
    super(message)
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST'
  body?: unknown
  timeoutMs?: number
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, timeoutMs = 15000 } = options
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(path, {
      method,
      signal: controller.signal,
      cache: 'no-store',
      headers: {
        Accept: 'application/json',
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
    const isJson = res.headers.get('content-type')?.includes('application/json')
    const data = isJson ? await res.json() : null
    if (!res.ok) {
      const detail =
        typeof data?.detail === 'string'
          ? data.detail
          : res.status === 503
            ? '后台数据服务暂不可用，请检查服务后重试。'
            : `请求失败（HTTP ${res.status}）`
      throw new ApiError(detail, res.status)
    }
    if (!isJson) throw new ApiError('服务没有返回可读取的数据。', res.status)
    return data as T
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ApiError('服务响应超时。写操作可能已在后台完成，请先刷新核对，不要直接重复提交。')
    }
    if (err instanceof TypeError) {
      throw new ApiError('无法连接后台服务，请确认 FastAPI 已在 8000 端口启动。')
    }
    throw err
  } finally {
    clearTimeout(timer)
  }
}

export const get = <T>(path: string, timeoutMs?: number) => request<T>(path, { timeoutMs })
export const post = <T>(path: string, body?: unknown, timeoutMs?: number) =>
  request<T>(path, { method: 'POST', body, timeoutMs })
