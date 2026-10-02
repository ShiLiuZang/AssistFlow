import { openModal } from '../../composables/useModal'
import GuideModal from './GuideModal.vue'
export const openClsGuide = () => openModal({ title: '主题与分类器 · 查询范围', view: GuideModal, cls: 'classification-dialog' })
