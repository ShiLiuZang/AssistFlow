// 轻提示（对应 V2 的 #toast），3.3 秒后消失
import { reactive } from 'vue'

export const toastState = reactive({ message: '', show: false })
let timer: ReturnType<typeof setTimeout> | undefined

export function toast(message: string, _tone?: 'info' | 'error') {
  toastState.message = message
  toastState.show = true
  clearTimeout(timer)
  timer = setTimeout(() => (toastState.show = false), 3300)
}

export const errorText = (err: unknown) => (err instanceof Error ? err.message : String(err))
