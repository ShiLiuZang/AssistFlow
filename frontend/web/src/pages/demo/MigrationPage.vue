<!-- 原功能对照（对应 V2 admin-panels.js 的 migration） -->
<script setup lang="ts">
import { useRouter } from 'vue-router'
import Icon from '../../components/Icon.vue'
import VPanel from '../../components/VPanel.vue'
import VTable from '../../components/VTable.vue'

const router = useRouter()
// [原页面, 原路径, 新入口, 打开位置, 必须保留的能力, 本轮原型状态]
const mapping = [
  ['客户聊天', '/', '客户咨询页', '/client', '历史会话、流式消息、引用、反馈、订单选择、工单确认、续跑', '部分演示；SSE 与历史回载待接入'],
  ['后台首页', '/admin', '管理总览', '/overview', '六模块读数、缺数据和异常提示', '布局演示'],
  ['知识库录入', '/kb', '知识中心', '/knowledge', '录入、切块、查重、来源、挖 QA、审核、双写、向量化、检索', '主要交互演示；无真实切块/索引'],
  ['飞轮待审', '/review', '知识缺口', '/review', '来源、频次、原问题、检索快照、审核和写回', '审核状态演示'],
  ['RAG 评估', '/rag-eval', 'RAG 质量', '/quality', '四策略、覆盖、生成、拒答、编造个案与处置', '示例报告和个案处理'],
  ['观测与成本', '/observability', '观测与成本', '/observability', '意图消耗、评估趋势、置信度校准', '三类示例报表'],
  ['主题分布', '/topics', '咨询主题', '/topics', '17 类统计、多标签计数、样例', '演示问题统计'],
  ['类目问题', '/topics/questions', '咨询主题 → 问题明细', '/topics', '类目筛选、问题明细、服务端分页', '筛选演示；分页待接入'],
  ['分类器验收', '/acceptance', '分类器 → 验收总览', '/models', '九项验收、产物缺失、服务状态、作业入口', '状态占位与任务演示'],
  ['评测详情', '/acceptance/eval', '分类器 → 评测与阈值', '/models?tab=evaluation', 'P/R/F1、容错红线、阈值扫描、混淆矩阵、单句分类', '示例指标与预设分类'],
  ['数据产物', '/acceptance/data', '分类器 → 数据与产物', '/models?tab=data', '语料来源、数据划分、泄漏检查、权重与 ONNX', '清单布局；无目录读取'],
  ['错例复核', '/acceptance/errors', '分类器 → 错例复核', '/models?tab=errors', '标准/预测对照、错误方向、近邻边界', '示例错例'],
  ['共享作业', '各后台页 /api/jobs', '作业中心 + 页内入口', '/jobs', '白名单、前置条件、启动、状态与日志；停止接口', '22 项浏览器内模拟'],
]
</script>

<template>
  <div class="page admin-page">
    <div class="page-title between">
      <div>
        <div class="eyebrow">FUNCTION MIGRATION</div>
        <h1>原页面的能力，一项都要有去处。</h1>
        <p>先核对功能，再迁移界面。下表明确区分已有逻辑、原型效果和待接入部分。</p>
      </div>
      <div class="page-actions"></div>
    </div>
    <div class="demo-strip"><span class="dot amber"></span>本页为交互原型 · 数据、指标及运行结果均为示例，未连接原项目服务。</div>
    <div class="migration-summary">
      <div><strong>12</strong><span>原有页面</span></div>
      <div><strong>6</strong><span>原后台模块</span></div>
      <div><strong>22</strong><span>已有作业定义</span></div>
      <div><strong>0</strong><span>被替换的原项目页面</span></div>
    </div>
    <VPanel title="页面与功能对照">
      <VTable :heads="['原页面', '新入口', '必须保留的能力', '本轮原型状态', '查看']">
        <tr v-for="[old, path, next, dest, features, stage] in mapping" :key="old">
          <td><b>{{ old }}</b><span class="table-sub mono">{{ path }}</span></td>
          <td>{{ next }}</td>
          <td class="wide-cell">{{ features }}</td>
          <td class="wide-cell muted">{{ stage }}</td>
          <td><button class="table-actions" @click="router.push(dest)">打开 <Icon name="arrow" /></button></td>
        </tr>
      </VTable>
    </VPanel>
    <div class="two-col section-gap">
      <VPanel title="已经有的，按契约迁移">
        <div class="panel-pad"><p>保留原接口、结果字段、错误状态和历史数据来源。新页面接入后逐项核对；原路径在迁移期间仍可访问。</p></div>
      </VPanel>
      <VPanel title="需要新建的，单独交付">
        <div class="panel-pad"><p>真实登录权限、人工认领、可靠人工收发、工单负责人和处理流、发布版本、真实商家接入，按后端计划补建。</p></div>
      </VPanel>
    </div>
    <div class="notice section-gap">完整迁移检查表保存在同目录 LEGACY_PAGE_MAP.md。页面入口可见不等于后端迁移完成，也不等于模型通过验收。</div>
  </div>
</template>
