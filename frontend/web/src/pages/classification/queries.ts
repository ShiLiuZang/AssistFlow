// 分类器各接口的查询（同一 key 在各子页之间共享缓存）
import { watch } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { getAcceptanceData, getAcceptanceErrors, getAcceptanceEval, getAcceptanceOverview, getClassifierService, getTopicCatalog } from '../../api/endpoints'
import { reportDataTime } from '../../composables/useDataTime'

export const useOverview = () => useQuery({ queryKey: ['acceptance', 'overview'], queryFn: getAcceptanceOverview })
export const useClsData = () => useQuery({ queryKey: ['acceptance', 'data'], queryFn: getAcceptanceData })
export const useClsEval = () => useQuery({ queryKey: ['acceptance', 'eval'], queryFn: getAcceptanceEval })
export const useClsErrors = () => useQuery({ queryKey: ['acceptance', 'errors'], queryFn: getAcceptanceErrors })
export const useClsService = () => useQuery({ queryKey: ['acceptance', 'service'], queryFn: getClassifierService })
export const useCatalog = () => useQuery({ queryKey: ['topics', 'catalog'], queryFn: getTopicCatalog })

// 页脚"本次读取"跟随当前子页的主接口
export function trackTime(q: { dataUpdatedAt: { value: number } }) {
  watch(() => q.dataUpdatedAt.value, reportDataTime, { immediate: true })
}
