<!-- 根组件：左侧分组导航 + 右侧页面区域 + 全局确认弹窗和提示 -->
<script setup lang="ts">
import { computed } from 'vue'
import { navItems } from './router'
import ConfirmHost from './components/ConfirmHost.vue'
import ToastHost from './components/ToastHost.vue'

const groups = computed(() => {
  const map = new Map<string, typeof navItems>()
  for (const item of navItems) map.set(item.group, [...(map.get(item.group) ?? []), item])
  return [...map.entries()]
})
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">Minihelp</div>
      <nav aria-label="管理后台导航">
        <div v-for="[group, items] in groups" :key="group" class="group">
          <div class="group-title">{{ group }}</div>
          <RouterLink v-for="item in items" :key="item.path" :to="item.path" class="nav-link">
            {{ item.label }}
          </RouterLink>
        </div>
      </nav>
      <p class="motto">每一次对话，都值得被认真回应。</p>
    </aside>
    <main class="content">
      <RouterView />
    </main>
  </div>
  <ConfirmHost />
  <ToastHost />
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  min-height: 100vh;
}
.sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--rail);
  color: var(--rail-text);
  padding: 24px 14px;
  overflow-y: auto;
}
.brand {
  font-size: 22px;
  font-weight: 700;
  padding: 0 10px 20px;
}
.group {
  margin-bottom: 14px;
}
.group-title {
  padding: 4px 12px;
  font-size: 12px;
  color: var(--rail-muted);
}
.nav-link {
  display: block;
  padding: 8px 12px;
  border-radius: 8px;
  color: var(--rail-text);
  opacity: 0.82;
  text-decoration: none;
  transition: background-color 150ms;
}
.nav-link:hover {
  opacity: 1;
  background: rgb(255 255 255 / 6%);
}
.nav-link.router-link-active {
  opacity: 1;
  background: var(--rail-active);
}
.motto {
  margin-top: auto;
  padding: 0 12px;
  font-size: 12px;
  color: var(--rail-muted);
}
.content {
  padding: 32px 36px 48px;
  min-width: 0;
  max-width: 1440px;
}
@media (max-width: 800px) {
  .shell {
    grid-template-columns: 1fr;
  }
  .sidebar {
    position: static;
    height: auto;
    padding: 14px 16px;
  }
  nav {
    display: flex;
    gap: 4px;
    overflow-x: auto;
  }
  .group {
    display: contents;
  }
  .group-title,
  .motto {
    display: none;
  }
  .nav-link {
    white-space: nowrap;
  }
  .brand {
    padding-bottom: 10px;
  }
  .content {
    padding: 20px 16px 40px;
  }
}
</style>
