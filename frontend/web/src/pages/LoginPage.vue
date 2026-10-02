<!-- 员工登录：成功后回到原页面（redirect 参数），令牌只保存在当前标签页 -->
<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { post } from '../api/client'
import { setStaff, type Role } from '../auth/session'

const route = useRoute()
const router = useRouter()
const catUrl = `${import.meta.env.BASE_URL}assets/minihelp-cat.svg`
const username = ref('')
const password = ref('')
const busy = ref(false)
const error = ref('')
const expired = route.query.expired === '1'

function target() {
  const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : ''
  // 只接受站内路径，避免被构造成跳转到外部地址
  return redirect.startsWith('/') && !redirect.startsWith('//') && redirect !== '/login' ? redirect : '/overview'
}

async function submit() {
  if (busy.value || !username.value.trim() || !password.value) return
  busy.value = true
  error.value = ''
  try {
    const result = await post<{ access_token: string; username: string; role: Role }>('/api/auth/login', {
      username: username.value.trim(),
      password: password.value,
    })
    setStaff({ token: result.access_token, username: result.username, role: result.role })
    password.value = ''
    await router.replace(target())
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <form class="login-card" @submit.prevent="submit">
      <div class="login-brand"><img :src="catUrl" alt="" /><span>AssistFlow 后台</span></div>
      <h1>员工登录</h1>
      <p v-if="expired && !error" class="notice amber" role="status">登录已失效，请重新登录。</p>
      <label>用户名<input v-model="username" autocomplete="username" maxlength="64" required :disabled="busy" /></label>
      <label>密码<input v-model="password" type="password" autocomplete="current-password" maxlength="256" required :disabled="busy" /></label>
      <p v-if="error" class="notice red" role="alert">{{ error }}</p>
      <button class="btn primary" :disabled="busy || !username.trim() || !password">{{ busy ? '正在登录…' : '登录' }}</button>
      <p class="muted small">账号由管理员用 <code>python -m scripts.tasks staff-create</code> 创建。</p>
      <RouterLink to="/client" class="text-button">前往客户咨询页 →</RouterLink>
    </form>
  </main>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px 16px;
  background: var(--canvas);
}
.login-card {
  width: min(380px, 100%);
  display: grid;
  gap: 14px;
  padding: 28px;
  background: var(--white);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--small-shadow);
}
.login-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
}
.login-brand img {
  width: 28px;
  height: 28px;
}
h1 {
  margin: 0;
  font-size: 22px;
}
label {
  display: grid;
  gap: 6px;
  font-size: 13px;
  color: var(--muted);
}
input {
  font: inherit;
  padding: 9px 11px;
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  color: var(--ink);
  background: var(--paper);
}
.notice {
  margin: 0;
}
.notice.red {
  color: var(--red);
  background: var(--red-soft);
  border-color: var(--red-soft);
}
</style>
