<!-- 设置与权限（对应 V2 service-panels.js 的 settingsPage） -->
<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import Icon from '../../components/Icon.vue'
import StatusPill from '../../components/StatusPill.vue'
import { openModal } from '../../composables/useModal'
import { toast } from '../../composables/useToast'
import { showNote } from '../../demo/actions'
import Avatar from '../../demo/Avatar.vue'
import { demo, log, view } from '../../demo/store'
import MemberEditModal from './MemberEditModal.vue'
import ServiceHeading from './ServiceHeading.vue'

const router = useRouter()
const sections = [
  ['members', '成员与角色', 'users'],
  ['reception', '接待规则', 'headset'],
  ['channels', '渠道接入', 'box'],
  ['audit', '操作记录', 'file'],
]
const roles = ['管理员', '主管', '客服', '知识运营']
const permissions: [string, number[]][] = [
  ['接待与处理工单', [1, 1, 1, 0]],
  ['审核知识', [1, 1, 0, 1]],
  ['分配会话与工单', [1, 1, 0, 0]],
  ['配置成员与渠道', [1, 0, 0, 0]],
]
// 接待规则表单：编辑副本，保存时写回
const form = reactive({ ...demo.rules })
const error = ref('')
function saveRules() {
  if (form.start >= form.end) {
    error.value = '结束时间需晚于开始时间。'
    return
  }
  error.value = ''
  Object.assign(demo.rules, form)
  log('接待规则', `${form.start}–${form.end} · ${form.mode === 'assist' ? 'AI 辅助' : 'AI 自动接待'}`)
  toast('演示配置已保存，可在操作记录查看')
}
const editMember = (id: number) => openModal({ title: `${demo.members.find((m) => m.id === id)?.name} · 调整角色`, view: MemberEditModal, props: { id } })
const channelDetails = () =>
  showNote(
    '电商渠道 · 待接入项',
    '<div class="page-map"><div class="map-row"><h3>账号与授权</h3><p>明确店铺范围、授权状态、失效后的重新连接流程。</p></div><div class="map-row"><h3>消息与业务</h3><p>验证消息收发、订单查询、商品同步和人工转接。</p></div></div><p class="quiet-note">这些能力仍待后端实现，本页不进行平台登录。</p>',
  )
</script>

<template>
  <div class="page admin-page service-page">
    <ServiceHeading eyebrow="WORKSPACE SETTINGS" title="设置与权限" desc="让团队的接待方式、成员职责和渠道状态清楚可见。" />
    <div class="settings-layout">
      <nav class="settings-nav" aria-label="设置分类">
        <button v-for="[id, label, ico] in sections" :key="id" :class="{ active: view.settingsTab === id }" :aria-pressed="view.settingsTab === id" @click="view.settingsTab = id">
          <Icon :name="ico" />{{ label }}<Icon name="chevron" />
        </button>
      </nav>
      <div class="settings-content">
        <template v-if="view.settingsTab === 'members'">
          <section class="panel">
            <div class="panel-head">
              <h2>团队成员</h2>
              <span class="small muted">演示角色，不改变实际权限</span>
            </div>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>成员</th>
                    <th>角色</th>
                    <th>范围</th>
                    <th>状态</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="m in demo.members" :key="m.id">
                    <td>
                      <div class="row"><Avatar :name="m.name" color="green" small /><strong>{{ m.name }}{{ m.self ? '（我）' : '' }}</strong></div>
                    </td>
                    <td>{{ m.role }}</td>
                    <td>喵喵优选</td>
                    <td><StatusPill :color="m.status === 'active' ? '' : 'neutral'">{{ m.status === 'active' ? '启用' : '停用' }}</StatusPill></td>
                    <td>
                      <button class="table-actions" :disabled="m.self" :title="m.self ? '当前演示管理员保留管理权限' : undefined" @click="editMember(m.id)">调整角色</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
          <section class="panel settings-secondary">
            <div class="panel-head">
              <h2>角色权限方案</h2>
              <span class="small muted">首版产品规划</span>
            </div>
            <div class="table-wrap">
              <table class="permission-table">
                <thead>
                  <tr>
                    <th>操作</th>
                    <th v-for="r in roles" :key="r">{{ r }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="[label, values] in permissions" :key="label">
                    <td>{{ label }}</td>
                    <td v-for="(v, i) in values" :key="i">
                      <span v-if="v" class="permission-yes">允许</span><span v-else class="muted">—</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </template>
        <form v-else-if="view.settingsTab === 'reception'" id="reception-form" class="panel settings-form" @submit.prevent="saveRules">
          <div class="panel-head">
            <div>
              <h2>接待规则</h2>
              <p class="field-hint">预览工作时间和自动接待配置的操作方式。</p>
            </div>
            <StatusPill color="neutral">演示配置</StatusPill>
          </div>
          <div class="settings-fields">
            <h3>服务时间</h3>
            <div class="field-pair">
              <label class="field">开始时间<input v-model="form.start" name="start" type="time" required /></label
              ><label class="field">结束时间<input v-model="form.end" name="end" type="time" required /></label>
            </div>
            <p class="field-hint">此处演示同一天的工作时段；跨夜排班将在正式版单独设置。</p>
            <h3>默认接待方式</h3>
            <div class="radio-cards">
              <label
                v-for="[value, label, text] in [
                  ['assist', 'AI 辅助', '先生成建议，由客服确认后发送。'],
                  ['auto', 'AI 自动接待', '先由助手回复，必要时进入人工队列。'],
                ]"
                :key="value"
                ><input v-model="form.mode" type="radio" name="mode" :value="value" /><span
                  ><strong>{{ label }}</strong><small>{{ text }}</small></span
                ></label
              >
            </div>
            <label class="field"
              >非工作时间<select v-model="form.offline" name="offline">
                <option value="ticket">记录问题并引导提交工单</option>
                <option value="queue">进入待接待队列</option>
              </select></label
            >
            <p id="reception-error" class="form-error" role="alert">{{ error }}</p>
          </div>
          <div class="settings-save">
            <span class="small muted">保存仅更新当前原型，不修改现有会话模式。</span><button class="btn primary" type="submit">保存演示配置</button>
          </div>
        </form>
        <template v-else-if="view.settingsTab === 'channels'">
          <section class="panel">
            <div class="panel-head">
              <h2>渠道接入</h2>
              <span class="small muted">接入状态预览</span>
            </div>
            <div class="channel-row">
              <span class="relation-icon"><Icon name="chat" /></span>
              <div>
                <h3>网站咨询</h3>
                <p>连接客户咨询页与客服工作台。</p>
              </div>
              <StatusPill color="neutral">前端演示</StatusPill><button class="btn" @click="router.push('/client')">打开咨询页</button>
            </div>
            <div class="channel-row">
              <span class="relation-icon"><Icon name="box" /></span>
              <div>
                <h3>电商平台</h3>
                <p>等待确定首发平台与正式接入方式。</p>
              </div>
              <StatusPill color="amber">待接入</StatusPill><button class="btn" @click="channelDetails">查看接入项</button>
            </div>
          </section>
          <div class="quiet-note">原型不接收账号密码、Cookie 或密钥；没有真实的登录、连接测试和平台授权。</div>
        </template>
        <section v-else class="panel">
          <div class="panel-head">
            <h2>本次演示操作</h2>
            <span class="small muted">刷新后清空</span>
          </div>
          <div v-if="demo.audit.length" class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>时间</th>
                  <th>操作人</th>
                  <th>操作</th>
                  <th>内容</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(a, i) in demo.audit" :key="i">
                  <td>{{ a.time }}</td>
                  <td>周小雨</td>
                  <td>{{ a.action }}</td>
                  <td>{{ a.detail }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="empty"><p>还没有设置变更。保存接待规则或调整成员角色后，会在这里留下演示记录。</p></div>
        </section>
      </div>
    </div>
  </div>
</template>
