import SimpleModal from '../../components/SimpleModal.vue'
import { openModal } from '../../composables/useModal'
import { guideHtml } from './state'

export const openGuide = () =>
  openModal({ title: '报告读取与运行说明', view: SimpleModal, props: { html: guideHtml, closeText: '关闭', link: { label: '查看作业中心', to: '/jobs' } } })
