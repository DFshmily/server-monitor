<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useServersStore } from '../stores/servers'
import { storeToRefs } from 'pinia'
import gsap from 'gsap'
import ServerCard from '../components/ServerCard.vue'
import FloatingGlobe from '../components/FloatingGlobe.vue'

const store = useServersStore()
const { serverList, connected, kioskMode } = storeToRefs(store)
const containerRef = ref(null)
const titleRef = ref(null)
const focusIndex = ref(0)
let rotateTimer = null

// 大屏模式：全屏 + 卡片自动轮播聚焦
function enterKiosk() {
  store.enterKioskMode()
  focusIndex.value = 0
  startRotation()
}

function exitKiosk() {
  store.exitKioskMode()
  stopRotation()
}

function startRotation() {
  stopRotation()
  if (serverList.value.length <= 1) return
  rotateTimer = setInterval(() => {
    focusIndex.value = (focusIndex.value + 1) % serverList.value.length
    const cards = containerRef.value?.querySelectorAll('.server-card')
    const target = cards?.[focusIndex.value]
    if (target) {
      gsap.fromTo(target, { opacity: 0.4, scale: 0.98 }, { opacity: 1, scale: 1.02, duration: 0.8, ease: 'power2.out' })
    }
  }, 8000)
}

function stopRotation() {
  if (rotateTimer) {
    clearInterval(rotateTimer)
    rotateTimer = null
  }
}

// 手动刷新(iOS PWA 无下拉刷新): 重拉服务器列表+最新数据
async function manualRefresh() {
  await store.fetchServers()
  for (const server of serverList.value) {
    store.fetchLatest(server.name)
  }
}

onMounted(async () => {
  await store.fetchServers()

  // Fetch latest for each server
  for (const server of serverList.value) {
    store.fetchLatest(server.name)
  }

  store.connectWebSocket()
  // GSAP title animation
  if (titleRef.value) {
    gsap.from(titleRef.value, {
      y: -15,
      opacity: 0,
      duration: 0.4,
      ease: 'power2.out',
      clearProps: 'all'
    })
  }
})

onUnmounted(() => {
  stopRotation()
  store.disconnectWebSocket()
})
</script>

<template>
  <div class="page-container">
    <div class="page-header" ref="titleRef">
      <div>
        <h1 class="section-title">DFshmily の<FloatingGlobe /></h1>
        <p class="subtitle">实时监控所有服务器状态</p>
      </div>
      <div class="header-right">
        <span class="connection-status" :class="{ online: connected }" title="实时数据推送通道">
          <span class="status-dot"></span>
        </span>
        <button v-if="!kioskMode" class="kiosk-btn" title="手动刷新数据" @click="manualRefresh">↻ 刷新</button>
        <button v-if="!kioskMode" class="kiosk-btn" title="大屏模式（全屏自动轮播）" @click="enterKiosk">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/>
          </svg>
          大屏
        </button>
        <button v-else class="kiosk-btn active" title="退出大屏模式 (Esc)" @click="exitKiosk">退出大屏</button>
      </div>
    </div>

    <div v-if="serverList.length === 0" class="empty-state glass-card">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="color: var(--text-tertiary)">
        <rect x="2" y="2" width="20" height="8" rx="2" ry="2"/>
        <rect x="2" y="14" width="20" height="8" rx="2" ry="2"/>
        <line x1="6" y1="6" x2="6.01" y2="6"/>
        <line x1="6" y1="18" x2="6.01" y2="18"/>
      </svg>
      <p>正在等待服务器数据...</p>
    </div>

    <div v-else ref="containerRef" class="grid-2" :class="{ 'kiosk-grid': kioskMode }">
      <ServerCard
        v-for="(server, idx) in serverList"
        :key="server.name"
        :server="server"
        :class="{ 'kiosk-focus': kioskMode && focusIndex === idx, 'kiosk-dim': kioskMode && focusIndex !== idx }"
      />
    </div>
  </div>
</template>

<style scoped>
.subtitle {
  font-size: 15px;
  color: var(--text-secondary);
  margin-top: 4px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

/* 大屏模式按钮 */
.kiosk-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 20px;
  background: transparent;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s ease;
}

.kiosk-btn:hover {
  border-color: var(--purple-500, #8b5cf6);
  color: var(--purple-600, #7c3aed);
}

.kiosk-btn.active {
  background: var(--purple-600, #7c3aed);
  border-color: var(--purple-600, #7c3aed);
  color: #fff;
}

/* 大屏模式布局：卡片堆叠放大，非聚焦卡片淡化 */
.kiosk-grid {
  grid-template-columns: 1fr;
  gap: 24px;
}

.kiosk-focus {
  opacity: 1 !important;
  transform: scale(1.02);
  transition: all 0.6s ease;
}

.kiosk-dim {
  opacity: 0.35;
  transform: scale(0.98);
  transition: all 0.6s ease;
}

.connection-status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.status-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #c7c7cc;
  transition: all 0.3s ease;
}

.connection-status.online .status-dot {
  background: var(--status-green);
  box-shadow: 0 0 10px rgba(52, 199, 89, 0.5);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 60px 24px;
  text-align: center;
}

.empty-state p {
  font-size: 15px;
  color: var(--text-secondary);
}
</style>
