// 全局确认弹窗：await confirm({...}) 返回 true/false。
// 所有写操作（入库、审核、启动作业）都先经过这里。
import { reactive } from 'vue'

export interface ConfirmOptions {
  title: string
  body: string
  confirmText?: string
  danger?: boolean
}

export const confirmState = reactive<{
  open: boolean
  options: ConfirmOptions
  resolve: ((ok: boolean) => void) | null
}>({
  open: false,
  options: { title: '', body: '' },
  resolve: null,
})

export function confirm(options: ConfirmOptions): Promise<boolean> {
  confirmState.resolve?.(false)
  confirmState.options = options
  confirmState.open = true
  return new Promise((resolve) => {
    confirmState.resolve = resolve
  })
}

export function settleConfirm(ok: boolean) {
  confirmState.resolve?.(ok)
  confirmState.resolve = null
  confirmState.open = false
}
