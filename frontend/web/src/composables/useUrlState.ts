// 把页面状态（tab、筛选、页码）同步到 URL 的 query 上：刷新不丢，链接可以直接分享。
import { computed, type WritableComputedRef } from 'vue'
import { useRoute, useRouter, type LocationQuery, type Router } from 'vue-router'

// 同一事件里改多个参数（如筛选 + 回到第 1 页）时合并成一次 replace，
// 否则第二次 replace 会基于旧的 query，把第一次的改动覆盖掉。
let pending: LocationQuery | null = null
function patchQuery(router: Router, base: LocationQuery, key: string, value: string | null) {
  if (!pending) {
    pending = { ...base }
    queueMicrotask(() => {
      const query = pending!
      pending = null
      router.replace({ query })
    })
  }
  if (value === null) delete pending[key]
  else pending[key] = value
}

export function useUrlState(key: string, fallback: string): WritableComputedRef<string> {
  const route = useRoute()
  const router = useRouter()
  return computed({
    get: () => {
      const value = route.query[key]
      return typeof value === 'string' && value !== '' ? value : fallback
    },
    set: (value: string) => {
      patchQuery(router, route.query, key, value === fallback || value === '' ? null : value)
    },
  })
}

export function useUrlNumber(key: string, fallback: number): WritableComputedRef<number> {
  const raw = useUrlState(key, String(fallback))
  return computed({
    get: () => {
      const n = Number(raw.value)
      return Number.isInteger(n) && n > 0 ? n : fallback
    },
    set: (value: number) => {
      raw.value = String(value)
    },
  })
}
