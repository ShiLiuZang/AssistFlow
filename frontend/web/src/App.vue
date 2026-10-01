<!-- 根组件：左侧导航 + 右侧页面区域。<RouterView> 会根据 URL 显示对应页面 -->
<script setup lang="ts">
const navItems = [{ to: '/knowledge', label: '知识中心' }]
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">Minihelp</div>
      <nav aria-label="管理后台导航">
        <!-- RouterLink 渲染成 <a>，当前页面会自动加上 router-link-active 类 -->
        <RouterLink v-for="item in navItems" :key="item.to" :to="item.to" class="nav-link">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>
    <main class="content">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  min-height: 100vh;
}
.sidebar {
  background: var(--rail);
  color: var(--rail-text);
  padding: 24px 14px;
}
.brand {
  font-size: 22px;
  font-weight: 700;
  padding: 0 10px 24px;
}
.nav-link {
  display: block;
  padding: 9px 12px;
  border-radius: 8px;
  color: var(--rail-muted);
  text-decoration: none;
  transition: background-color 150ms;
}
.nav-link:hover {
  color: var(--rail-text);
  background: rgb(255 255 255 / 6%);
}
.nav-link.router-link-active {
  color: var(--rail-text);
  background: var(--rail-active);
}
.content {
  padding: 32px 36px;
  min-width: 0;
}
@media (max-width: 700px) {
  .shell {
    grid-template-columns: 1fr;
  }
  .sidebar {
    padding: 14px 16px;
  }
  .content {
    padding: 20px 16px;
  }
}
</style>
