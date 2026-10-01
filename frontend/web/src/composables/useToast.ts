// 轻提示：右下角显示几秒后自动消失
import { reactive } from 'vue'

export const toastState = reactive({ message: '', tone: 'info' as 'info' | 'error', id: 0 })
let timer: ReturnType<typeof setTimeout> | undefined

export function toast(message: string, tone: 'info' | 'error' = 'info') {
  toastState.message = message
  toastState.tone = tone
  toastState.id += 1
  clearTimeout(timer)
  timer = setTimeout(() => (toastState.message = ''), tone === 'error' ? 6000 : 3500)
}

export const errorText = (err: unknown) => (err instanceof Error ? err.message : String(err))
