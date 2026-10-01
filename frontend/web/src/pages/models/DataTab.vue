<script setup lang="ts">
import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { getAcceptanceData } from '../../api/endpoints'
import Panel from '../../components/Panel.vue'
import Pill from '../../components/Pill.vue'
import StateBlock from '../../components/StateBlock.vue'
import { bytes, dateTime, num } from '../../utils/format'

const { data, error, isPending, refetch } = useQuery({ queryKey: ['acceptance', 'data'], queryFn: getAcceptanceData })
const splits = computed(() => Object.entries(data.value?.dataset.splits ?? {}))
const leakNames: Record<string, string> = { train_val: '训练 ∩ 验证', train_test: '训练 ∩ 测试', val_test: '验证 ∩ 测试' }
const fileName = (p: string) => p.split(/[\\/]/).pop()
</script>

<template>
  <StateBlock :loading="isPending" :error="error" @retry="refetch()" />
  <template v-if="data">
    <Panel title="语料流水线">
      <div class="table-wrap">
        <table class="data">
          <thead>
            <tr>
              <th>阶段</th>
              <th>文件</th>
              <th class="num">行数</th>
              <th>说明</th>
              <th>更新时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="l in data.lineage" :key="l.file">
              <td>{{ l.stage }}</td>
              <td class="mono">{{ l.file }} <Pill v-if="!l.present" tone="neutral">未生成</Pill></td>
              <td class="num">{{ num(l.lines) }}</td>
              <td class="small muted">{{ l.desc }}</td>
              <td class="small">{{ dateTime(l.mtime) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </Panel>

    <div class="grid-2">
      <Panel title="数据集划分">
        <table class="data">
          <thead>
            <tr>
              <th>集合</th>
              <th class="num">条数</th>
              <th class="num">多标签</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="[key, s] in splits" :key="key">
              <td>{{ s.desc }}</td>
              <td class="num">{{ num(s.size) }}</td>
              <td class="num">{{ num(s.multi_label) }}</td>
            </tr>
          </tbody>
        </table>
        <h3 class="sub">集合间重叠 <Pill :tone="data.dataset.clean ? 'green' : 'red'">{{ data.dataset.clean ? '零重叠' : '有重叠，分数不作数' }}</Pill></h3>
        <dl class="kv">
          <template v-for="(n, k) in data.dataset.leaks" :key="k">
            <dt>{{ leakNames[k] ?? k }}</dt>
            <dd>{{ n }} 条</dd>
          </template>
        </dl>
      </Panel>

      <Panel title="模型与导出产物">
        <p class="small muted">
          在用阈值 {{ data.model.threshold ?? '—' }} ·
          <Pill :tone="data.model.trio_ok ? 'green' : 'neutral'">{{ data.model.trio_ok ? '权重三件套齐全' : '三件套不全' }}</Pill>
        </p>
        <table class="data">
          <thead>
            <tr>
              <th>文件</th>
              <th class="num">大小</th>
              <th>更新时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="f in [...data.model.files, ...data.onnx.files]" :key="f.path">
              <td class="mono">{{ fileName(f.path) }}</td>
              <td class="num">{{ bytes(f.bytes) }}</td>
              <td class="small">{{ dateTime(f.mtime) }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="!data.model.files.length && !data.onnx.files.length" class="muted">尚无模型产物。</p>
      </Panel>
    </div>
  </template>
</template>

<style scoped>
.sub {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  margin: 16px 0 8px;
}
</style>
