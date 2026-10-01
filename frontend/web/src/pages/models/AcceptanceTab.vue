<script setup lang="ts">
import { ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { getAcceptanceOverview } from '../../api/endpoints'
import JobCard from '../../components/JobCard.vue'
import Pill from '../../components/Pill.vue'
import StatCard from '../../components/StatCard.vue'
import StateBlock from '../../components/StateBlock.vue'
import { acceptanceStatus } from '../../utils/labels'

const { data, error, isPending, refetch } = useQuery({ queryKey: ['acceptance', 'overview'], queryFn: getAcceptanceOverview })
const openJobs = ref<string | null>(null)
</script>

<template>
  <StateBlock :loading="isPending" :error="error" @retry="refetch()" />
  <template v-if="data">
    <section class="stat-strip">
      <StatCard label="通过验收" :value="`${data.passed} / ${data.total}`" foot="后端逐项判定" />
      <StatCard label="未达标" :value="data.blocks.filter((b) => b.status === 'fail').length" unit="项" foot="产物存在但条件未满足" />
      <StatCard label="未生成" :value="data.blocks.filter((b) => b.status === 'missing').length" unit="项" foot="缺少所需产物或报告" />
      <StatCard label="分类服务" :value="data.classifier.online ? '在线' : '离线'" foot=":8110 健康检查" :tone="data.classifier.online ? 'normal' : 'warn'" />
    </section>
    <p class="notice" :class="{ warn: !data.all_pass }">
      {{ data.all_pass ? '九项全部达标。' : '尚未全部达标：' }}文件齐全、评测达标与服务在线分别判断，完整验收需要所有项目满足条件。
    </p>

    <div class="grid-3">
      <article v-for="b in data.blocks" :key="b.key" class="block">
        <header>
          <span class="no mono">{{ String(b.no).padStart(2, '0') }}</span>
          <h3>{{ b.title }}</h3>
          <Pill :tone="acceptanceStatus[b.status][1]">{{ acceptanceStatus[b.status][0] }}</Pill>
        </header>
        <p class="headline">{{ b.headline }}</p>
        <p class="small muted">{{ b.note }}</p>
        <button class="btn small ghost" type="button" @click="openJobs = openJobs === b.key ? null : b.key">
          {{ openJobs === b.key ? '收起作业' : `相关作业（${b.jobs.length}）` }}
        </button>
        <div v-if="openJobs === b.key" class="jobs">
          <JobCard v-for="j in b.jobs" :key="j" :name="j" compact />
        </div>
      </article>
    </div>
  </template>
</template>

<style scoped>
.block {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px 18px;
  background: var(--white);
  border: 1px solid var(--line);
  border-radius: var(--radius);
}
header {
  display: flex;
  align-items: center;
  gap: 8px;
}
h3 {
  margin: 0;
  font-size: 15px;
  flex: 1;
}
.no {
  color: var(--muted);
}
.headline {
  margin: 0;
  font-size: 14px;
}
.small {
  margin: 0;
}
.jobs {
  border-top: 1px solid var(--line);
}
.btn {
  align-self: flex-start;
}
</style>
