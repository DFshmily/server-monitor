<script setup>
import { computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import gsap from 'gsap'

const props = defineProps({
  server: {
    type: Object,
    required: true
  }
})

const router = useRouter()
const cardRef = ref(null)
const coresExpanded = ref(false)

const latest = computed(() => props.server.latest || {})
const hasData = computed(() => !!latest.value.cpu)

// Core metrics
const cpuPercent = computed(() => latest.value.cpu?.percent ?? 0)
const memPercent = computed(() => latest.value.memory?.percent ?? 0)
const memUsedGB = computed(() => {
  const used = latest.value.memory?.used || 0
  return (used / 1024 / 1024 / 1024).toFixed(1)
})
const memTotalGB = computed(() => {
  const total = latest.value.memory?.total || 0
  return (total / 1024 / 1024 / 1024).toFixed(0)
})
const diskPercent = computed(() => {
  const partitions = latest.value.disk?.partitions
  if (!partitions || partitions.length === 0) return 0
  const root = partitions.find(p => p.mountpoint === '/') || partitions[0]
  return root.percent ?? 0
})
const diskUsedGB = computed(() => {
  const partitions = latest.value.disk?.partitions
  if (!partitions) return '0'
  const root = partitions.find(p => p.mountpoint === '/') || partitions[0]
  return ((root?.used || 0) / 1024 / 1024 / 1024).toFixed(0)
})
const diskTotalGB = computed(() => {
  const partitions = latest.value.disk?.partitions
  if (!partitions) return '0'
  const root = partitions.find(p => p.mountpoint === '/') || partitions[0]
  return ((root?.total || 0) / 1024 / 1024 / 1024).toFixed(0)
})

const load1 = computed(() => latest.value.load?.load1 ?? '-')
const load5 = computed(() => latest.value.load?.load5 ?? '-')
const load15 = computed(() => latest.value.load?.load15 ?? '-')

// Network: rates (agent-computed) + traffic totals
const netInRate = computed(() => latest.value.network?.total_recv_rate ?? 0)
const netOutRate = computed(() => latest.value.network?.total_sent_rate ?? 0)
// Lifetime totals survive reboots; fall back to session totals
const netInTotal = computed(() => latest.value.network?.lifetime_bytes_recv ?? latest.value.network?.total_bytes_recv ?? 0)
const netOutTotal = computed(() => latest.value.network?.lifetime_bytes_sent ?? latest.value.network?.total_bytes_sent ?? 0)

const formatBytes = (bytes) => {
  if (!bytes || bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

const formatRate = (bytes) => formatBytes(bytes) + '/s'

const servicesFailed = computed(() => latest.value.services?.failed ?? 0)
const servicesTotal = computed(() => latest.value.services?.total ?? 0)

const cpuCores = computed(() => latest.value.cpu?.cores ?? 0)

const uptimeSeconds = computed(() => latest.value.system?.uptime_seconds ?? 0)
const uptimeFormatted = computed(() => {
  const s = uptimeSeconds.value
  if (!s) return '-'
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (d > 0) return `${d}天 ${h}时`
  if (h > 0) return `${h}时 ${m}分`
  return `${m}分`
})

// Per-core CPU
const perCpu = computed(() => latest.value.cpu?.per_cpu || [])

const statusClass = computed(() => hasData.value ? 'online' : 'offline')

// Progress bar color by usage level
const getBarClass = (percent) => {
  if (percent > 90) return 'danger'
  if (percent > 70) return 'warning'
  return ''
}

const navigateToDetail = () => {
  router.push(`/server/${props.server.name}`)
}

// Server display name (alias > default)
const displayName = computed(() => {
  if (props.server.alias) return props.server.alias
  const name = props.server.name
  if (name === 'oracle') return 'oracle'
  if (name === 'tencent') return '广州'
  return name
})

// Server hostname subtitle (brand name)
const serverHostname = computed(() => {
  const name = props.server.name
  if (name === 'oracle') return 'ORACLE CLOUD'
  if (name === 'tencent') return 'TENCENT CLOUD'
  return name
})

// Server icon (national flag)
const serverIcon = computed(() => {
  const name = props.server.name
  if (name === 'oracle') return '🇯🇵'
  if (name === 'tencent') return '🇨🇳'
  return '🖥️'
})

onMounted(() => {
  if (cardRef.value) {
    gsap.from(cardRef.value, {
      y: 20,
      opacity: 0,
      duration: 0.5,
      ease: 'power2.out',
      clearProps: 'all'
    })
  }
})
</script>

<template>
  <div ref="cardRef" class="server-card glass-card" @click="navigateToDetail">
    <!-- Header -->
    <div class="card-header">
      <div class="server-info">
        <span class="server-icon">{{ serverIcon }}</span>
        <div class="server-name-wrap">
          <div class="server-name">{{ displayName }}</div>
          <div class="server-hostname">{{ serverHostname }}</div>
        </div>
      </div>
      <div class="header-right">
        <span class="badge" :class="statusClass === 'online' ? 'badge-online' : 'badge-offline'">
          <span class="dot"></span>
          {{ statusClass === 'online' ? '在线' : '离线' }}
        </span>
      </div>
    </div>

    <!-- No data state -->
    <div v-if="!hasData" class="no-data">
      <span>等待数据...</span>
    </div>

    <!-- Metrics -->
    <template v-else>
      <!-- Core metrics with progress bars -->
      <div class="metrics-grid">
        <div class="metric-row">
          <div class="metric-label">CPU</div>
          <div class="metric-bar-wrapper">
            <div class="metric-bar">
              <div class="metric-bar-fill" :class="getBarClass(cpuPercent)" :style="{ width: `${Math.min(cpuPercent, 100)}%` }"></div>
            </div>
          </div>
          <div class="metric-value">{{ cpuPercent.toFixed(1) }}%</div>
        </div>

        <div class="metric-row">
          <div class="metric-label">内存</div>
          <div class="metric-bar-wrapper">
            <div class="metric-bar">
              <div class="metric-bar-fill" :class="getBarClass(memPercent)" :style="{ width: `${Math.min(memPercent, 100)}%` }"></div>
            </div>
          </div>
          <div class="metric-value">{{ memPercent.toFixed(1) }}%</div>
        </div>

        <div class="metric-row">
          <div class="metric-label">磁盘</div>
          <div class="metric-bar-wrapper">
            <div class="metric-bar">
              <div class="metric-bar-fill" :class="getBarClass(diskPercent)" :style="{ width: `${Math.min(diskPercent, 100)}%` }"></div>
            </div>
          </div>
          <div class="metric-value">{{ diskPercent.toFixed(1) }}%</div>
        </div>
      </div>

      <!-- Per-core CPU mini bars (clickable) -->
      <div v-if="perCpu.length > 0" class="cpu-cores" :class="{ expanded: coresExpanded }" @click.stop="coresExpanded = !coresExpanded">
        <div class="cores-header">
          <div class="cores-label">
            <span class="cores-arrow" :class="{ open: coresExpanded }">▶</span>
            CPU 各核心
          </div>
          <div class="cores-hint">{{ coresExpanded ? '收起' : '点击展开' }}</div>
        </div>
        <div class="cores-grid">
          <div v-for="(usage, i) in perCpu" :key="i" class="core-bar" :title="`Core ${i}: ${usage}%`">
            <div class="core-bar-fill" :class="getBarClass(usage)" :style="{ height: `${Math.min(usage, 100)}%` }"></div>
          </div>
        </div>
        <!-- Expanded per-core detail -->
        <transition name="slide">
          <div v-if="coresExpanded" class="cores-detail">
            <div v-for="(usage, i) in perCpu" :key="'d'+i" class="core-detail-item">
              <div class="core-detail-name">Core {{ i }}</div>
              <div class="core-detail-bar">
                <div class="core-detail-fill" :class="getBarClass(usage)" :style="{ width: `${Math.min(usage, 100)}%` }"></div>
              </div>
              <div class="core-detail-value" :class="getBarClass(usage)">{{ usage.toFixed(1) }}%</div>
            </div>
          </div>
        </transition>
      </div>

      <!-- Detail metrics grid -->
      <div class="details-grid">
        <div class="detail-item">
          <div class="detail-icon">📡</div>
          <div class="detail-content">
            <div class="detail-label">网速</div>
            <div class="detail-value net-rate">
              <span class="up">↑ {{ formatRate(netOutRate) }}</span>
              <span class="down">↓ {{ formatRate(netInRate) }}</span>
            </div>
          </div>
        </div>

        <div class="detail-item">
          <div class="detail-icon">📦</div>
          <div class="detail-content">
            <div class="detail-label">流量</div>
            <div class="detail-value net-traffic">
              <span class="up">↑ {{ formatBytes(netOutTotal) }}</span>
              <span class="down">↓ {{ formatBytes(netInTotal) }}</span>
            </div>
          </div>
        </div>

        <div class="detail-item">
          <div class="detail-icon">📊</div>
          <div class="detail-content">
            <div class="detail-label">负载</div>
            <div class="detail-value">{{ load1 }} / {{ load5 }} / {{ load15 }}</div>
          </div>
        </div>

        <div class="detail-item">
          <div class="detail-icon">⏱️</div>
          <div class="detail-content">
            <div class="detail-label">运行</div>
            <div class="detail-value">{{ uptimeFormatted }}</div>
          </div>
        </div>

        <div class="detail-item">
          <div class="detail-icon">💾</div>
          <div class="detail-content">
            <div class="detail-label">内存</div>
            <div class="detail-value">{{ memUsedGB }}G / {{ memTotalGB }}G</div>
          </div>
        </div>

        <div class="detail-item">
          <div class="detail-icon">💿</div>
          <div class="detail-content">
            <div class="detail-label">磁盘</div>
            <div class="detail-value">{{ diskUsedGB }}G / {{ diskTotalGB }}G</div>
          </div>
        </div>

        <div class="detail-item">
          <div class="detail-icon">⚙️</div>
          <div class="detail-content">
            <div class="detail-label">服务</div>
            <div class="detail-value">
              {{ servicesTotal }} 个
              <span v-if="servicesFailed > 0" class="text-danger">({{ servicesFailed }} 异常)</span>
            </div>
          </div>
        </div>

        <div class="detail-item">
          <div class="detail-icon">💻</div>
          <div class="detail-content">
            <div class="detail-label">核心</div>
            <div class="detail-value">{{ cpuCores }} 核</div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.server-card {
  padding: 24px;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.server-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.12);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}

.server-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.server-icon {
  font-size: 28px;
  line-height: 1;
}

.server-name {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
}

.server-name-wrap {
  min-width: 0;
}

.server-hostname {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 2px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.badge-online {
  background: rgba(52, 199, 89, 0.1);
  color: #34c759;
}
.badge-online .dot {
  background: #34c759;
  box-shadow: 0 0 6px rgba(52, 199, 89, 0.5);
}

.badge-offline {
  background: rgba(255, 59, 48, 0.1);
  color: #ff3b30;
}
.badge-offline .dot {
  background: #ff3b30;
}

.no-data {
  text-align: center;
  padding: 40px 0;
  color: var(--text-tertiary);
  font-size: 14px;
}

/* Metrics progress bars */
.metrics-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 18px;
}

.metric-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.metric-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  width: 32px;
  flex-shrink: 0;
}

.metric-bar-wrapper {
  flex: 1;
}

.metric-bar {
  height: 8px;
  background: rgba(0, 0, 0, 0.04);
  border-radius: 10px;
  overflow: hidden;
}

.metric-bar-fill {
  height: 100%;
  border-radius: 10px;
  background: linear-gradient(90deg, #a78bfa, #7c3aed);
  transition: width 0.6s cubic-bezier(0.22, 1, 0.36, 1);
}

.metric-bar-fill.warning {
  background: linear-gradient(90deg, #ffb340, #ff9500);
}

.metric-bar-fill.danger {
  background: linear-gradient(90deg, #ff6b6b, #ff3b30);
}

.metric-value {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  width: 52px;
  text-align: right;
  flex-shrink: 0;
}

/* CPU cores mini bars */
.cpu-cores {
  margin-bottom: 18px;
  padding: 12px;
  background: rgba(0, 0, 0, 0.02);
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.2s ease;
}

.cpu-cores:hover {
  background: rgba(0, 0, 0, 0.04);
}

.cpu-cores.expanded {
  background: rgba(124, 58, 237, 0.03);
}

.cores-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.cores-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  display: flex;
  align-items: center;
  gap: 5px;
}

.cores-arrow {
  font-size: 7px;
  transition: transform 0.25s ease;
  display: inline-block;
}

.cores-arrow.open {
  transform: rotate(90deg);
}

.cores-hint {
  font-size: 10px;
  color: var(--purple-500);
  font-weight: 500;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.cpu-cores:hover .cores-hint {
  opacity: 1;
}

.cores-grid {
  display: flex;
  gap: 3px;
  height: 24px;
}

.core-bar {
  flex: 1;
  background: rgba(0, 0, 0, 0.04);
  border-radius: 4px;
  position: relative;
  overflow: hidden;
}

.core-bar-fill {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: linear-gradient(to top, #a78bfa, #7c3aed);
  border-radius: 4px;
  transition: height 0.5s ease;
}

.core-bar-fill.warning {
  background: linear-gradient(to top, #ffb340, #ff9500);
}

.core-bar-fill.danger {
  background: linear-gradient(to top, #ff6b6b, #ff3b30);
}

/* Expanded core detail */
.cores-detail {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid rgba(0, 0, 0, 0.05);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.core-detail-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.core-detail-name {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  width: 48px;
  flex-shrink: 0;
  font-family: 'SF Mono', 'Fira Code', monospace;
}

.core-detail-bar {
  flex: 1;
  height: 6px;
  background: rgba(0, 0, 0, 0.04);
  border-radius: 6px;
  overflow: hidden;
}

.core-detail-fill {
  height: 100%;
  border-radius: 6px;
  background: linear-gradient(90deg, #a78bfa, #7c3aed);
  transition: width 0.5s ease;
}

.core-detail-fill.warning {
  background: linear-gradient(90deg, #ffb340, #ff9500);
}

.core-detail-fill.danger {
  background: linear-gradient(90deg, #ff6b6b, #ff3b30);
}

.core-detail-value {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-primary);
  width: 42px;
  text-align: right;
  flex-shrink: 0;
}

.core-detail-value.warning { color: #ff9500; }
.core-detail-value.danger { color: #ff3b30; }

/* Slide transition */
.slide-enter-active,
.slide-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  max-height: 0;
  margin-top: 0;
  padding-top: 0;
}

.slide-enter-to,
.slide-leave-from {
  opacity: 1;
  max-height: 300px;
}

/* Detail metrics grid */
.details-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 2px;
  padding-top: 16px;
  border-top: 1px solid rgba(0, 0, 0, 0.04);
}

.detail-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 8px;
  border-radius: 8px;
  transition: background 0.15s ease;
}

.detail-item:hover {
  background: rgba(0, 0, 0, 0.02);
}

.detail-icon {
  font-size: 16px;
  line-height: 1;
  flex-shrink: 0;
}

.detail-content {
  min-width: 0;
}

.detail-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.detail-value {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}

.net-rate,
.net-traffic {
  display: flex;
  flex-direction: column;
  gap: 1px;
  line-height: 1.3;
}

.net-rate .up,
.net-traffic .up {
  color: #34c759;
  font-weight: 700;
}

.net-rate .down,
.net-traffic .down {
  color: #007aff;
  font-weight: 700;
}

.text-danger {
  color: #ff3b30 !important;
}

@media (max-width: 768px) {
  .details-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
