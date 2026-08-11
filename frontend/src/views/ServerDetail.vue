<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useServersStore } from '../stores/servers'
import { storeToRefs } from 'pinia'
import gsap from 'gsap'
import MetricChart from '../components/MetricChart.vue'
import ProcessTable from '../components/ProcessTable.vue'
import ServiceStatus from '../components/ServiceStatus.vue'

const route = useRoute()
const router = useRouter()
const store = useServersStore()
const { servers } = storeToRefs(store)

const name = computed(() => route.params.name)

// Display name mapping (consistent with ServerCard)
const displayName = computed(() => {
  if (server.value?.alias) return server.value.alias
  if (name.value === 'tencent') return '广州'
  return name.value
})

const server = computed(() => servers.value[name.value] || null)
const latest = computed(() => server.value?.latest || {})
const history = ref([])

const selectedTab = ref('overview')
const selectedInterval = ref('1min')
const dateStart = ref('')
const dateEnd = ref('')

const tabs = [
  { key: 'overview', label: '概览' },
  { key: 'cpu', label: 'CPU' },
  { key: 'memory', label: '内存' },
  { key: 'disk', label: '磁盘' },
  { key: 'network', label: '网络' },
  { key: 'process', label: '进程' },
  { key: 'services', label: '服务' },
  { key: 'docker', label: 'Docker' }
]

// 服务异常数角标
const servicesFailedCount = computed(() => latest.value.services?.failed ?? 0)

const intervals = [
  { value: 'realtime', label: '实时' },
  { value: '1min', label: '1分钟' },
  { value: '5min', label: '5分钟' },
  { value: '1h', label: '1小时' },
  { value: '1d', label: '1天' },
  { value: '1mon', label: '1个月' },
  { value: 'custom', label: '自定义' }
]

// Custom date range helpers
const todayStr = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const applyCustomRange = () => {
  if (dateStart.value && dateEnd.value) {
    selectedInterval.value = 'custom'
  }
}

const toTimestamp = (dateStr) => {
  if (!dateStr) return null
  return Math.floor(new Date(dateStr + 'T00:00:00').getTime() / 1000)
}

// Nested data paths matching collector output
const cpuPercent = computed(() => latest.value.cpu?.percent ?? 0)
const memPercent = computed(() => latest.value.memory?.percent ?? 0)
const diskPercent = computed(() => {
  const partitions = latest.value.disk?.partitions
  if (!partitions || partitions.length === 0) return 0
  const root = partitions.find(p => p.mountpoint === '/') || partitions[0]
  return root.percent ?? 0
})
const gpuPercent = computed(() => latest.value.gpu?.percent ?? null)
const load1 = computed(() => latest.value.load?.load1 ?? '-')
const load5 = computed(() => latest.value.load?.load5 ?? '-')
const load15 = computed(() => latest.value.load?.load15 ?? '-')

const processes = computed(() => latest.value.processes?.top_cpu || [])
const servicesList = computed(() => latest.value.services?.services || [])
const dockerContainers = computed(() => latest.value.docker?.containers || [])

const formatBytes = (bytes) => {
  if (!bytes || bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

// History data comes as [{timestamp, data: {...}}]
const cpuHistory = computed(() =>
  history.value.map(d => ({
    timestamp: d.timestamp,
    value: d.data?.cpu?.percent ?? 0
  }))
)

const memHistory = computed(() =>
  history.value.map(d => ({
    timestamp: d.timestamp,
    value: d.data?.memory?.percent ?? 0
  }))
)

const diskHistory = computed(() =>
  history.value.map(d => {
    const dd = d.data?.disk || {}
    // Aggregated data has percent directly
    if (dd.percent !== undefined && dd.percent > 0) {
      return { timestamp: d.timestamp, value: dd.percent }
    }
    // Raw data has partitions
    const partitions = dd.partitions
    const root = partitions?.find(p => p.mountpoint === '/') || partitions?.[0]
    return { timestamp: d.timestamp, value: root?.percent ?? 0 }
  })
)

const netHistory = computed(() =>
  history.value.map(d => {
    const nd = d.data?.network || {}
    // Aggregated data has rate fields
    if (nd.bytes_recv_rate !== undefined) {
      return { timestamp: d.timestamp, in: nd.bytes_recv_rate, out: nd.bytes_sent_rate }
    }
    // Raw data has interfaces dict
    const ifaces = nd.interfaces || {}
    const totalIn = Object.values(ifaces).reduce((s, i) => s + (i.bytes_recv || 0), 0)
    const totalOut = Object.values(ifaces).reduce((s, i) => s + (i.bytes_sent || 0), 0)
    return { timestamp: d.timestamp, in: totalIn, out: totalOut }
  })
)

const loadHistory = computed(() =>
  history.value.map(d => ({
    timestamp: d.timestamp,
    load1: d.data?.load?.load1 ?? 0,
    load5: d.data?.load?.load5 ?? 0,
    load15: d.data?.load?.load15 ?? 0
  }))
)

const fetchHistory = async () => {
  if (!name.value) return
  let iv = selectedInterval.value
  let limit = 200
  let start = null
  let end = null

  if (iv === '1mon') {
    // Last 30 days: daily aggregation points
    iv = '1d'
    limit = 31
    end = Math.floor(Date.now() / 1000)
    start = end - 30 * 86400
  } else if (iv === 'custom') {
    if (!dateStart.value || !dateEnd.value) {
      history.value = []
      return
    }
    iv = '1d'
    limit = 366
    start = toTimestamp(dateStart.value)
    end = toTimestamp(dateEnd.value) + 86400 - 1
  }

  const data = await store.fetchHistory(name.value, iv, limit, start, end)
  history.value = data || []
}

const goBack = () => {
  router.push('/')
}

const sectionRef = ref(null)

onMounted(async () => {
  await store.fetchLatest(name.value)
  await fetchHistory()
  store.connectWebSocket()

  if (sectionRef.value) {
    const elements = sectionRef.value.querySelectorAll('.animate-in')
    gsap.from(elements, {
      y: 30,
      opacity: 0,
      duration: 0.5,
      stagger: 0.08,
      ease: 'power2.out'
    })
  }
})

watch(selectedInterval, () => {
  fetchHistory()
})

// 实时模式：WebSocket 每 2 秒推送最新值 → 增量追加到图表，保持 200 点滚动窗口
watch(latest, (newData) => {
  if (selectedInterval.value !== 'realtime') return
  if (!newData || Object.keys(newData).length === 0) return
  const ts = newData.timestamp || Math.floor(Date.now() / 1000)
  history.value = [...history.value, { timestamp: ts, data: newData }].slice(-200)
})

watch(selectedTab, () => {
  setTimeout(() => {
    const elements = sectionRef.value?.querySelectorAll('.animate-in')
    if (elements && elements.length > 0) {
      gsap.from(elements, {
        y: 20,
        opacity: 0,
        duration: 0.4,
        stagger: 0.06,
        ease: 'power2.out'
      })
    }
  }, 50)
})

onUnmounted(() => {
  store.disconnectWebSocket()
})
</script>

<template>
  <div class="page-container" ref="sectionRef">
    <!-- Header -->
    <div class="page-header animate-in">
      <div style="display:flex;align-items:center;gap:16px">
        <button class="back-button" @click="goBack">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
          返回
        </button>
        <div>
          <h1 class="section-title" style="text-transform:capitalize">{{ displayName }}</h1>
          <span class="badge badge-online" v-if="latest.cpu">在线</span>
          <span class="badge badge-offline" v-else>离线</span>
        </div>
      </div>
      <div class="interval-selector">
        <button
          v-for="opt in intervals"
          :key="opt.value"
          class="interval-btn"
          :class="{ active: selectedInterval === opt.value }"
          @click="selectedInterval = opt.value"
        >
          {{ opt.label }}
        </button>
        <div v-if="selectedInterval === 'custom'" class="custom-range">
          <input type="date" v-model="dateStart" :max="dateEnd || todayStr()" @change="applyCustomRange" />
          <span class="range-sep">—</span>
          <input type="date" v-model="dateEnd" :min="dateStart" :max="todayStr()" @change="applyCustomRange" />
        </div>
      </div>
    </div>

    <!-- Quick Stats -->
    <div class="quick-stats animate-in">
      <div class="stat-card glass-card">
        <div class="stat-value" :class="{ warning: cpuPercent > 80, danger: cpuPercent > 95 }">
          {{ cpuPercent.toFixed(1) }}%
        </div>
        <div class="stat-label">CPU</div>
      </div>
      <div class="stat-card glass-card">
        <div class="stat-value" :class="{ warning: memPercent > 80, danger: memPercent > 95 }">
          {{ memPercent.toFixed(1) }}%
        </div>
        <div class="stat-label">内存</div>
      </div>
      <div class="stat-card glass-card">
        <div class="stat-value" :class="{ warning: diskPercent > 80, danger: diskPercent > 95 }">
          {{ diskPercent.toFixed(1) }}%
        </div>
        <div class="stat-label">磁盘</div>
      </div>
      <div class="stat-card glass-card" v-if="gpuPercent !== null">
        <div class="stat-value">{{ gpuPercent.toFixed(1) }}%</div>
        <div class="stat-label">GPU</div>
      </div>
      <div class="stat-card glass-card">
        <div class="stat-value load">{{ load1 }}</div>
        <div class="stat-label">负载 (1/5/15)</div>
        <div class="stat-sub">{{ load5 }} / {{ load15 }}</div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="tab-container animate-in">
      <div
        v-for="tab in tabs"
        :key="tab.key"
        class="tab-item"
        :class="{ active: selectedTab === tab.key }"
        @click="selectedTab = tab.key"
      >
        {{ tab.label }}
        <span v-if="tab.key === 'services' && servicesFailedCount > 0" class="tab-badge">
          {{ servicesFailedCount }}
        </span>
      </div>
    </div>

    <!-- Tab Content -->
    <div class="tab-content">
      <!-- Overview -->
      <template v-if="selectedTab === 'overview'">
        <div class="grid-2">
          <MetricChart
            class="animate-in"
            title="CPU 使用率"
            :data="cpuHistory"
            :yKeys="['value']"
            :yLabels="['CPU']"
            :colors="['#7c3aed']"
            unit="%"
            :max="100"
          />
          <MetricChart
            class="animate-in"
            title="内存使用率"
            :data="memHistory"
            :yKeys="['value']"
            :yLabels="['内存']"
            :colors="['#007aff']"
            unit="%"
            :max="100"
          />
          <MetricChart
            class="animate-in"
            title="磁盘使用率"
            :data="diskHistory"
            :yKeys="['value']"
            :yLabels="['磁盘']"
            :colors="['#ff9500']"
            unit="%"
            :max="100"
          />
          <MetricChart
            class="animate-in"
            title="网络流量"
            :data="netHistory"
            :yKeys="['in', 'out']"
            :yLabels="['入站', '出站']"
            :colors="['#34c759', '#ff3b30']"
            unit=" B"
          />
        </div>
      </template>

      <!-- CPU -->
      <template v-if="selectedTab === 'cpu'">
        <MetricChart
          class="animate-in"
          title="CPU 使用率趋势"
          :data="cpuHistory"
          :yKeys="['value']"
          :yLabels="['CPU']"
          :colors="['#7c3aed']"
          unit="%"
          :max="100"
        />
        <MetricChart
          class="animate-in"
          title="系统负载"
          :data="loadHistory"
          :yKeys="['load1', 'load5', 'load15']"
          :yLabels="['1分钟', '5分钟', '15分钟']"
          :colors="['#7c3aed', '#a78bfa', '#c4b5fd']"
          unit=""
        />
      </template>

      <!-- Memory -->
      <template v-if="selectedTab === 'memory'">
        <MetricChart
          class="animate-in"
          title="内存使用率趋势"
          :data="memHistory"
          :yKeys="['value']"
          :yLabels="['内存']"
          :colors="['#007aff']"
          unit="%"
          :max="100"
        />
      </template>

      <!-- Disk -->
      <template v-if="selectedTab === 'disk'">
        <MetricChart
          class="animate-in"
          title="磁盘使用率趋势"
          :data="diskHistory"
          :yKeys="['value']"
          :yLabels="['磁盘']"
          :colors="['#ff9500']"
          unit="%"
          :max="100"
        />
      </template>

      <!-- Network -->
      <template v-if="selectedTab === 'network'">
        <MetricChart
          class="animate-in"
          title="网络流量趋势"
          :data="netHistory"
          :yKeys="['in', 'out']"
          :yLabels="['入站', '出站']"
          :colors="['#34c759', '#ff3b30']"
          unit=" B"
        />
      </template>

      <!-- Process -->
      <template v-if="selectedTab === 'process'">
        <ProcessTable class="animate-in" :processes="processes" />
      </template>

      <!-- Services -->
      <template v-if="selectedTab === 'services'">
        <ServiceStatus class="animate-in" :services="servicesList" />
      </template>

      <!-- Docker -->
      <template v-if="selectedTab === 'docker'">
        <div class="docker-section animate-in glass-card" style="padding:20px">
          <h3 class="chart-title">Docker 容器</h3>
          <div v-if="dockerContainers.length === 0" class="empty">暂无 Docker 数据</div>
          <div v-else class="docker-grid">
            <div v-for="c in dockerContainers" :key="c.name || c.id" class="docker-item">
              <div class="docker-name">{{ c.name }}</div>
              <span class="service-badge" :class="c.status === 'running' ? 'active' : 'failed'">
                {{ c.status }}
              </span>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.interval-selector {
  display: flex;
  gap: 4px;
  padding: 4px;
  background: rgba(0, 0, 0, 0.04);
  border-radius: 10px;
  flex-wrap: wrap;
}

.interval-btn {
  padding: 7px 14px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  border: none;
  background: none;
  transition: all 0.2s ease;
}

.interval-btn:hover {
  color: var(--text-primary);
  background: rgba(255, 255, 255, 0.5);
}

.interval-btn.active {
  background: white;
  color: var(--purple-600);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
}

.custom-range {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 4px 2px 10px;
}

.custom-range input[type="date"] {
  padding: 6px 8px;
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 8px;
  font-size: 12px;
  font-family: inherit;
  color: var(--text-primary);
  background: white;
  outline: none;
}

.custom-range input[type="date"]:focus {
  border-color: var(--purple-500);
}

.range-sep {
  color: var(--text-tertiary);
  font-size: 12px;
}

.quick-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}

.stat-card {
  padding: 20px;
  text-align: center;
}

.stat-value {
  font-size: 32px;
  font-weight: 700;
  letter-spacing: -0.03em;
  color: var(--text-primary);
  line-height: 1.1;
}

.stat-value.warning { color: var(--status-orange); }
.stat-value.danger { color: var(--status-red); }
.stat-value.load { font-size: 24px; }

.stat-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-top: 6px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.stat-sub {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 2px;
}

.tab-content { min-height: 300px; }

.service-summary {
  display: flex;
  gap: 20px;
  font-size: 15px;
  font-weight: 600;
}

.docker-grid { display: flex; flex-direction: column; gap: 2px; }

.docker-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  border-radius: 10px;
  transition: background 0.15s ease;
}

.docker-item:hover { background: rgba(0, 0, 0, 0.02); }
.docker-name { font-weight: 600; font-size: 14px; }

.service-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
}

.service-badge.active { background: rgba(52, 199, 89, 0.12); color: var(--status-green); }
.service-badge.failed { background: rgba(255, 59, 48, 0.12); color: var(--status-red); }

.empty {
  text-align: center;
  padding: 40px;
  color: var(--text-tertiary);
  font-size: 14px;
}
</style>
