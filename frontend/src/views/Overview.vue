<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useServersStore } from '../stores/servers'
import { storeToRefs } from 'pinia'
import gsap from 'gsap'
import ServerCard from '../components/ServerCard.vue'
import FloatingGlobe from '../components/FloatingGlobe.vue'

const store = useServersStore()
const { serverList, connected } = storeToRefs(store)
const containerRef = ref(null)
const titleRef = ref(null)

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

    <div v-else ref="containerRef" class="grid-2">
      <ServerCard
        v-for="server in serverList"
        :key="server.name"
        :server="server"
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
