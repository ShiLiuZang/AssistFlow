// 统一的请求函数：超时、错误信息都在这里处理，页面只管拿数据。
// 逻辑对应旧 V2 admin-data.js 里的 request()。

export class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
  ) {
    super(message)
  }
}

export async function getJson<T>(path: string, timeoutMs = 12000): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(path, {
      signal: controller.signal,
      headers: { Accept: 'application/json' },
    })
    if (res.status >= 500) {
      throw new ApiError(
        res.status === 503 ? '后台数据服务暂不可用，请检查服务后重试。' : '后台读取失败，请重试。',
        res.status,
      )
    }
    if (!res.headers.get('content-type')?.includes('application/json')) {
      throw new ApiError('服务没有返回可读取的数据。', res.status)
    }
    const data = await res.json()
    if (!res.ok) {
      const detail = typeof data?.detail === 'string' ? data.detail : `请求失败（HTTP ${res.status}）`
      throw new ApiError(detail, res.status)
    }
    return data as T
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ApiError('服务响应超时，请重试。')
    }
    if (err instanceof TypeError) {
      throw new ApiError('无法连接后台服务，请确认 FastAPI 已启动。')
    }
    throw err
  } finally {
    clearTimeout(timer)
  }
}
