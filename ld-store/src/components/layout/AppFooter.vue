<template>
  <nav v-if="showFooter" class="app-footer" aria-label="移动端主导航">
    <router-link
      v-for="item in navItems"
      :key="item.path"
      :to="item.path"
      :class="['nav-item', { active: isActive(item.path) }]"
      :aria-current="isActive(item.path) ? 'page' : undefined"
    >
      <span class="nav-icon" aria-hidden="true">
        <component :is="item.iconComponent" :size="22" :stroke-width="2" />
      </span>
      <span class="nav-label">{{ item.label }}</span>
    </router-link>
  </nav>
</template>

<script setup>
import { ClipboardList, Megaphone, House, LogIn, Search, UserRound } from '@lucide/vue'
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const userStore = useUserStore()

// 是否显示底部导航（仅移动端）
const showFooter = computed(() => {
  // 某些页面不显示底部导航
  const hideOnRoutes = ['Login', 'AuthCallback', 'ProductDetail', 'OrderConfirm', 'Publish', 'Edit', 'OrderDetail', 'Docs', 'DocsSection']
  return !hideOnRoutes.includes(route.name)
})

// 导航项
const navItems = computed(() => {
  const items = [
    { path: '/', iconComponent: House, label: '首页' },
    { path: '/search', iconComponent: Search, label: '搜索' },
    { path: '/announcements', iconComponent: Megaphone, label: '公告' }
  ]
  
  if (userStore.isLoggedIn) {
    items.push(
      { path: '/user/orders', iconComponent: ClipboardList, label: '订单' },
      { path: '/user', iconComponent: UserRound, label: '我的' }
    )
  } else {
    items.push(
      { path: '/login', iconComponent: LogIn, label: '登录' }
    )
  }
  
  return items
})

// 判断是否为当前路由
function isActive(path) {
  if (path === '/') {
    return route.path === '/'
  }
  return route.path.startsWith(path)
}
</script>

<style scoped>
.app-footer {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  display: none;
  background: var(--glass-bg-heavy);
  border-top: 1px solid var(--border-light);
  padding-bottom: env(safe-area-inset-bottom, 0);
  z-index: 100;
}

.nav-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 10px 0;
  text-decoration: none;
  transition: color var(--motion-duration-fast) var(--motion-ease-standard), background-color var(--motion-duration-fast) var(--motion-ease-standard), border-color var(--motion-duration-fast) var(--motion-ease-standard), box-shadow var(--motion-duration-fast) var(--motion-ease-standard), opacity var(--motion-duration-fast) var(--motion-ease-standard), transform var(--motion-duration-fast) var(--motion-ease-standard);
}

.nav-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 2px;
  color: var(--text-tertiary);
  opacity: 0.6;
  transition: color var(--motion-duration-fast) var(--motion-ease-standard), background-color var(--motion-duration-fast) var(--motion-ease-standard), border-color var(--motion-duration-fast) var(--motion-ease-standard), box-shadow var(--motion-duration-fast) var(--motion-ease-standard), opacity var(--motion-duration-fast) var(--motion-ease-standard), transform var(--motion-duration-fast) var(--motion-ease-standard);
}

.nav-label {
  font-size: 10px;
  color: var(--text-tertiary);
  transition: color 0.2s;
}

.nav-item.active .nav-icon {
  color: var(--color-primary);
  opacity: 1;
  transform: scale(1.1);
}

.nav-item.active .nav-label {
  color: var(--color-primary);
  font-weight: 600;
}

/* 仅在移动端显示底部导航 */
@media (max-width: 768px) {
  .app-footer {
    display: flex;
  }
}
</style>
