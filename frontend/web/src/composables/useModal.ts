// 全局弹窗（对应 V2 的 #modal）。调用方传入一个组件作为弹窗内容，
// 内容组件自己渲染 .modal-body 和 .modal-foot，结构与 V2 完全一致。
import { markRaw, reactive, type Component } from 'vue'

export const modalState = reactive<{
  open: boolean
  title: string
  cls: string
  view: Component | null
  props: Record<string, unknown>
  key: number
}>({ open: false, title: '', cls: '', view: null, props: {}, key: 0 })

export function openModal(options: { title: string; view: Component; props?: Record<string, unknown>; cls?: string }) {
  modalState.title = options.title
  modalState.cls = options.cls ?? ''
  modalState.view = markRaw(options.view)
  modalState.props = options.props ?? {}
  modalState.key += 1
  modalState.open = true
}

export function closeModal() {
  modalState.open = false
}
