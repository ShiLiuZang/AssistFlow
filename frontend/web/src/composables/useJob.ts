// 后台作业：读取状态，运行中每 2 秒轮询一次；启动和停止前都要确认。
import { computed } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { getJob, startJob, stopJob } from '../api/endpoints'
import { confirm } from './useConfirm'
import { errorText, toast } from './useToast'

export function useJob(name: () => string) {
  const client = useQueryClient()
  const key = computed(() => ['job', name()])

  const query = useQuery({
    queryKey: key,
    queryFn: () => getJob(name()),
    refetchInterval: (q) => (q.state.data?.status === 'running' ? 2000 : false),
  })

  const afterChange = () => {
    client.invalidateQueries({ queryKey: key.value })
    client.invalidateQueries({ queryKey: ['jobs'] })
  }

  const start = useMutation({
    mutationFn: () => startJob(name()),
    onSuccess: (job) => {
      client.setQueryData(key.value, job)
      toast(`已启动：${job.title}`)
      afterChange()
    },
    onError: (err) => toast(errorText(err), 'error'),
  })

  const stop = useMutation({
    mutationFn: () => stopJob(name()),
    onSuccess: (job) => {
      client.setQueryData(key.value, job)
      toast(`已停止：${job.title}`)
      afterChange()
    },
    onError: (err) => toast(errorText(err), 'error'),
  })

  async function confirmStart() {
    const job = query.data.value
    const ok = await confirm({
      title: `启动作业：${job?.title ?? name()}`,
      body: `执行条件：${job?.needs ?? '未知'}。${job?.heavy ? '这是耗时较长的作业，可能会调用付费模型。' : ''}启动后可以在这里查看日志，关闭页面不会停止作业。`,
      confirmText: '确认启动',
    })
    if (ok) start.mutate()
  }

  async function confirmStop() {
    const ok = await confirm({
      title: '停止作业',
      body: '停止后本次运行的结果可能不完整，需要重新运行。',
      confirmText: '确认停止',
      danger: true,
    })
    if (ok) stop.mutate()
  }

  return { query, start, stop, confirmStart, confirmStop }
}
