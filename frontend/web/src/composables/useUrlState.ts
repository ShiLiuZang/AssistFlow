// 把页面状态（tab、筛选、页码）同步到 URL 的 query 上：刷新不丢，链接可以直接分享。
import { computed, type WritableComputedRef } from 'vue'
import { useRoute, useRouter } from 'vue-router'

export function useUrlState(key: string, fallback: string): WritableComputedRef<string> {
  const route = useRoute()
  const router = useRouter()
  return computed({
    get: () => {
      const value = route.query[key]
      return typeof value === 'string' && value !== '' ? value : fallback
    },
    set: (value: string) => {
      const query = { ...route.query }
      if (value === fallback || value === '') delete query[key]
      else query[key] = value
      router.replace({ query })
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
