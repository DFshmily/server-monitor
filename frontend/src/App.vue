<script setup>
import { RouterView, useRouter } from 'vue-router'
import { ref, onMounted } from 'vue'
import { useAuthStore } from './stores/auth'

const router = useRouter()
const auth = useAuthStore()
const showMenu = ref(false)

// 页面加载时从 localStorage 恢复登录态
onMounted(() => {
  const token = localStorage.getItem('monitor_token')
  if (token && !auth.token) {
    auth.token = token
  }
})

function go(path) {
  showMenu.value = false
  router.push(path)
}

function handleLogout() {
  auth.logout()
  showMenu.value = false
  router.push('/')
}
</script>

<template>
  <div class="app-container">
    <nav v-if="!$route.meta.guestOnly" class="top-nav">
      <div class="nav-inner">
        <div class="nav-links">
          <span class="nav-link" @click="go('/')">首页</span>
          <span v-if="auth.isAdmin()" class="nav-link" @click="go('/admin')">管理</span>
        </div>
        <div class="nav-user">
          <template v-if="auth.isLoggedIn()">
            <span class="nav-email" title="点击切换菜单" @click="showMenu = !showMenu">
              {{ auth.user?.email || '已登录' }}
            </span>
            <div v-if="showMenu" class="nav-menu">
              <div class="menu-item" @click="go('/admin')" v-if="auth.isAdmin()">管理后台</div>
              <div class="menu-item danger" @click="handleLogout">退出登录</div>
            </div>
          </template>
          <span v-else class="nav-login" @click="go('/login')">登录</span>
        </div>
      </div>
    </nav>
    <RouterView />
  </div>
</template>

<style scoped>
.app-container {
  min-height: 100vh;
  background: #f5f5f7;
}

.top-nav {
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.nav-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 12px 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.nav-links {
  display: flex;
  gap: 24px;
  align-items: center;
}

.nav-link {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  transition: color 0.2s;
}

.nav-link:hover {
  color: var(--purple-600, #7c3aed);
}

.nav-user {
  position: relative;
}

.nav-email {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  cursor: pointer;
  padding: 6px 12px;
  border-radius: 20px;
  background: rgba(124, 58, 237, 0.08);
  color: var(--purple-600, #7c3aed);
}

.nav-login {
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  background: var(--purple-600, #7c3aed);
  padding: 6px 16px;
  border-radius: 20px;
  cursor: pointer;
}

.nav-menu {
  position: absolute;
  right: 0;
  top: calc(100% + 8px);
  min-width: 140px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  padding: 6px;
  overflow: hidden;
}

.menu-item {
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  cursor: pointer;
}

.menu-item:hover {
  background: rgba(0, 0, 0, 0.04);
}

.menu-item.danger {
  color: var(--status-red);
}
</style>
