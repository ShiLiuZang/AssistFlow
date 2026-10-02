// 管理页底部"本次读取 HH:MM:SS"：页面在数据读取成功时上报时间
import { ref } from 'vue'
export const dataTime = ref<string | null>(null)
export function reportDataTime(ms: number | undefined) {
  dataTime.value = ms ? new Date(ms).toLocaleTimeString('zh-CN') : null
}
