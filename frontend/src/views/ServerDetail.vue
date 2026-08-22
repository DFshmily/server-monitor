<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useServersStore } from '../stores/servers'
import { storeToRefs } from 'pinia'
import gsap from 'gsap'
import MetricChart from '../components/MetricChart.vue'
import ProcessTable from '../components/ProcessTable.vue'
import ServiceStatus from '../components/ServiceStatus.vue'
import TrafficDailyChart from '../components/TrafficDailyChart.vue'

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
  { key: 'updates', label: '待更新' },
  { key: 'docker', label: 'Docker' },
  { key: 'hardware', label: '硬件健康' }
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
  // Force Beijing time (UTC+8)
  const d = new Date(Date.now() + 8 * 3600 * 1000)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}`
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

// 自定义监控项（agent 定期执行命令上报）
const customItems = computed(() => latest.value.custom || {})
const aptUpdates = computed(() => latest.value.apt_updates || {})
const aptCount = computed(() => (aptUpdates.value.ok ? aptUpdates.value.count : null))
// 待更新软件列表(登录用户可见)
const aptPackages = computed(() => {
  const pkgs = aptUpdates.value.packages
  return Array.isArray(pkgs) ? pkgs : []
})

// 自定义监控项历史曲线
const customHistory = ref([])
const selectedCustomItem = ref('')
const showCustomHistory = ref(false)
async function loadCustomHistory(item) {
  if (!name.value || !item) return
  selectedCustomItem.value = item
  showCustomHistory.value = true
  try {
    const token = localStorage.getItem('monitor_token')
    const res = await fetch(`/api/servers/${name.value}/custom-history?item=${encodeURIComponent(item)}&hours=24`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
    if (!res.ok) return
    const data = await res.json()
    customHistory.value = data.map(p => ({ timestamp: p.timestamp, value: p.value }))
  } catch (e) {
    customHistory.value = []
  }
}

const processes = computed(() => latest.value.processes?.top_cpu || [])
const servicesList = computed(() => latest.value.services?.services || [])
const dockerContainers = computed(() => latest.value.docker?.containers || [])

// ── 硬件健康 (SMART) ──
const smartDisks = computed(() => {
  const s = latest.value.disk_smart || {}
  return Object.entries(s).map(([dev, d]) => ({ dev, ...d }))
})
const fmtPowerHours = (h) => {
  if (h == null) return '—'
  const days = Math.floor(h / 24)
  return days > 0 ? `${days} 天 ${h % 24} 小时` : `${h} 小时`
}

const formatBytes = (bytes) => {
  if (!bytes || bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

// 本月流量汇总 (agent 采集, 每机独立配额/时区)
const monthTraffic = computed(() => latest.value.traffic_month || {})
const monthUsed = computed(() => monthTraffic.value.total_bytes || 0)
const monthQuotaGB = computed(() => monthTraffic.value.quota_gb || 0)
const monthUsedPct = computed(() => monthTraffic.value.used_percent ?? null)
const monthPctClass = computed(() => {
  const p = monthUsedPct.value
  if (p === null || p === undefined) return ''
  if (p > 90) return 'danger'
  if (p > 70) return 'warning'
  return ''
})
const monthTzLabel = computed(() => (monthTraffic.value.tz === 'UTC' ? 'UTC 月结' : '北京时间月结'))

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

// ── 事件标注（Grafana Annotations 风格）──
const events = ref([])
const maintenance = ref([])
const annotations = computed(() => events.value.map(e => ({ ts: e.ts, kind: e.kind, message: e.message })))
const markAreas = computed(() => maintenance.value.map(m => ({ start: m.start, end: m.end, note: m.note })))
const eventsHours = computed(() => {
  const iv = selectedInterval.value
  if (iv === 'realtime' || iv === '1min' || iv === '5min') return 3
  if (iv === '1h') return 24
  if (iv === '1d') return 48
  return 720
})
const fetchEvents = async () => {
  if (!name.value) return
  try {
    const token = localStorage.getItem('monitor_token')
    const res = await fetch(`/api/servers/${name.value}/events?hours=${eventsHours.value}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
    if (!res.ok) return
    const data = await res.json()
    events.value = data.events || []
    maintenance.value = data.maintenance || []
  } catch (e) {
    // 事件标注加载失败不影响图表
  }
}

// 导出当前视图数据为 CSV
const exportCSV = () => {
  if (!history.value || history.value.length === 0) {
    alert('暂无可导出的数据')
    return
  }
  const fmt = (ts) => {
    // Force Beijing time (UTC+8)
    const ms = (ts > 1e12 ? ts : ts * 1000) + 8 * 3600 * 1000
    const d = new Date(ms)
    const p = (n) => String(n).padStart(2, '0')
    return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}`
  }
  const diskOf = (dd) => {
    const parts = dd?.partitions
    const root = parts?.find(p => p.mountpoint === '/') || parts?.[0]
    return root?.percent ?? (dd?.percent ?? '')
  }
  const netOf = (nd) => nd?.bytes_recv_rate ?? ''
  const rows = [['时间', 'CPU%', '内存%', '磁盘%', '网络入(B/s)', '网络出(B/s)', '负载1']]
  history.value.forEach(d => {
    rows.push([
      fmt(d.timestamp),
      d.data?.cpu?.percent ?? '',
      d.data?.memory?.percent ?? '',
      diskOf(d.data?.disk),
      netOf(d.data?.network),
      d.data?.network?.bytes_sent_rate ?? '',
      d.data?.load?.load1 ?? ''
    ])
  })
  const csv = rows.map(r => r.map(v => `"${v}"`).join(',')).join('\n')
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${name.value}_${selectedInterval.value}_${Date.now()}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
}

const sectionRef = ref(null)

onMounted(async () => {
  await store.fetchLatest(name.value)
  await fetchHistory()
  fetchEvents()
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
  fetchEvents()
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
        <button class="csv-btn" title="导出当前数据为 CSV" @click="exportCSV">⬇ 导出</button>
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
      <!-- 自定义监控项 -->
      <div
        v-for="(item, key) in customItems"
        :key="key"
        class="stat-card glass-card"
        :title="item.raw ? `${key}: ${item.raw}` : ''"
      >
        <div class="stat-value" :class="{ err: !item.ok }">
          {{ item.ok ? (item.value != null ? `${item.value}${item.unit || ''}` : item.raw) : '—' }}
        </div>
        <div class="stat-label">{{ key }}</div>
        <div v-if="!item.ok" class="stat-sub err">{{ item.error || '获取失败' }}</div>
        <button v-if="item.ok" class="stat-hist-btn" @click="loadCustomHistory(key)">📈 历史</button>
      </div>
      <!-- apt 更新提醒 -->
      <div class="stat-card glass-card" v-if="aptCount !== null">
        <div class="stat-value" :class="{ warning: aptCount > 0 }">
          {{ aptCount }}
        </div>
        <div class="stat-label">待更新</div>
      </div>
      <div class="stat-card glass-card">
        <div class="stat-value load">{{ load1 }}</div>
        <div class="stat-label">负载 (1/5/15)</div>
        <div class="stat-sub">{{ load5 }} / {{ load15 }}</div>
      </div>
    </div>

    <!-- 自定义监控项历史曲线 -->
    <div v-if="showCustomHistory && customHistory.length > 1" class="custom-history-area animate-in">
      <MetricChart
        :annotations="annotations"
        :mark-areas="markAreas"
        :title="`${selectedCustomItem} · 最近 24 小时`"
        :data="customHistory"
        :yKeys="['value']"
        :yLabels="[selectedCustomItem]"
        :colors="['#34c759']"
        unit=""
      />
      <button class="hist-close" @click="showCustomHistory = false">收起历史 ✕</button>
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
        <span v-if="tab.key === 'updates' && aptCount > 0" class="tab-badge warning">
          {{ aptCount }}
        </span>
      </div>
    </div>

    <!-- Tab Content -->
    <div class="tab-content">
      <!-- Overview -->
      <template v-if="selectedTab === 'overview'">
        <div class="grid-2">
          <MetricChart
            :annotations="annotations"
            :mark-areas="markAreas"
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
            :annotations="annotations"
            :mark-areas="markAreas"
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
            :annotations="annotations"
            :mark-areas="markAreas"
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
            :annotations="annotations"
            :mark-areas="markAreas"
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
            :annotations="annotations"
            :mark-areas="markAreas"
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
            :annotations="annotations"
            :mark-areas="markAreas"
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
            :annotations="annotations"
            :mark-areas="markAreas"
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
            :annotations="annotations"
            :mark-areas="markAreas"
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
        <!-- 本月流量汇总 -->
        <div class="month-summary glass-card animate-in">
          <div class="month-summary-head">
            <span class="month-summary-title">📅 本月流量 <span class="month-tz">{{ monthTzLabel }}</span></span>
            <span v-if="monthQuotaGB > 0" class="month-pct" :class="monthPctClass">{{ monthUsedPct }}%</span>
          </div>
          <div class="month-summary-body">
            <div class="month-used">{{ formatBytes(monthUsed) }}<span v-if="monthQuotaGB > 0" class="month-quota"> / {{ monthQuotaGB }} GB</span></div>
            <div v-if="monthQuotaGB > 0" class="month-bar">
              <div class="month-bar-fill" :class="monthPctClass" :style="{ width: `${Math.min(monthUsedPct || 0, 100)}%` }"></div>
            </div>
            <div class="month-hint">跨月自动归零 · 按厂商账单口径结算</div>
          </div>
        </div>

        <MetricChart
            :annotations="annotations"
            :mark-areas="markAreas"
          class="animate-in"
          title="网络流量趋势"
          :data="netHistory"
          :yKeys="['in', 'out']"
          :yLabels="['入站', '出站']"
          :colors="['#34c759', '#ff3b30']"
          unit=" B"
        />
        <TrafficDailyChart class="animate-in" :server-name="name" :days="30" />
      </template>

      <!-- Process -->
      <template v-if="selectedTab === 'process'">
        <ProcessTable class="animate-in" :processes="processes" />
      </template>

      <!-- Services -->
      <template v-if="selectedTab === 'services'">
        <ServiceStatus class="animate-in" :services="servicesList" />
      </template>

      <!-- 待更新软件 -->
      <template v-if="selectedTab === 'updates'">
        <div class="apt-status glass-card animate-in">
          <div class="table-header">
            <h3 class="chart-title">待更新软件</h3>
            <div class="header-right">
              <span class="apt-count">{{ aptCount }} 个待更新</span>
            </div>
          </div>
          <div class="apt-list">
            <div v-for="(pkg, i) in aptPackages" :key="pkg.name + i" class="apt-item">
              <div class="apt-info">
                <span class="apt-name">{{ pkg.name }}</span>
                <span class="apt-vers">
                  <span class="apt-old">{{ pkg.old_version || '—' }}</span>
                  <span class="apt-arrow">→</span>
                  <span class="apt-new">{{ pkg.version || '—' }}</span>
                </span>
              </div>
              <span class="apt-badge">待更新</span>
            </div>
            <div v-if="aptCount > aptPackages.length" class="apt-more">
              … 还有 {{ aptCount - aptPackages.length }} 个未显示
            </div>
            <div v-if="aptPackages.length === 0" class="empty">
              🎉 没有待更新软件
            </div>
          </div>
        </div>
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

      <!-- 硬件健康 (SMART) -->
      <template v-if="selectedTab === 'hardware'">
        <div class="apt-status glass-card animate-in">
          <div class="table-header">
            <h3 class="chart-title">磁盘 S.M.A.R.T. 健康</h3>
            <div class="header-right">
              <span class="apt-count">{{ smartDisks.length }} 块物理盘</span>
            </div>
          </div>
          <div v-if="smartDisks.length === 0" class="empty">
            暂无 SMART 数据 · 云主机虚拟盘或未安装 smartctl 时不采集
          </div>
          <div v-for="d in smartDisks" :key="d.dev" class="smart-disk">
            <div class="smart-head">
              <span class="smart-dev">{{ d.dev }}</span>
              <span class="service-badge" :class="d.ok ? 'active' : 'failed'">
                {{ d.overall || '未知' }}
              </span>
            </div>
            <div class="smart-grid">
              <div class="smart-item">
                <span class="smart-label">温度</span>
                <span class="smart-value">{{ d.temperature != null ? d.temperature + ' °C' : '—' }}</span>
              </div>
              <div class="smart-item">
                <span class="smart-label">重映射扇区</span>
                <span class="smart-value" :class="{ warn: (d.reallocated_sectors || 0) > 0 }">
                  {{ d.reallocated_sectors != null ? d.reallocated_sectors : '—' }}
                </span>
              </div>
              <div class="smart-item">
                <span class="smart-label">待映射扇区</span>
                <span class="smart-value" :class="{ warn: (d.pending_sectors || 0) > 0 }">
                  {{ d.pending_sectors != null ? d.pending_sectors : '—' }}
                </span>
              </div>
              <div class="smart-item">
                <span class="smart-label">通电时长</span>
                <span class="smart-value">{{ fmtPowerHours(d.power_on_hours) }}</span>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
/* SMART 硬件健康 */
.smart-disk { padding: 14px 0; border-bottom: 1px solid rgba(128,128,128,.15); }
.smart-disk:last-child { border-bottom: none; }
.smart-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.smart-dev { font-family: 'SF Mono', Menlo, Consolas, monospace; font-weight: 600; }
.smart-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 8px; }
.smart-item {
  display: flex; flex-direction: column; gap: 2px;
  background: rgba(128,128,128,.08); border-radius: 8px; padding: 8px 12px;
}
.smart-label { font-size: 11px; opacity: .6; }
.smart-value { font-family: 'SF Mono', Menlo, Consolas, monospace; font-size: 14px; }
.smart-value.warn { color: #ff9500; font-weight: 700; }

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

.csv-btn {
  padding: 7px 12px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--purple-600);
  cursor: pointer;
  border: 1px solid rgba(124, 58, 237, 0.3);
  background: rgba(124, 58, 237, 0.06);
  transition: all 0.2s ease;
}

.csv-btn:hover {
  background: rgba(124, 58, 237, 0.12);
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
.stat-value.err { color: var(--status-red); font-size: 20px; }
.stat-sub.err { color: var(--status-red); font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 130px; }
.stat-hist-btn {
  margin-top: 4px;
  padding: 2px 10px;
  border: 1px solid rgba(52, 199, 89, 0.35);
  border-radius: 8px;
  background: rgba(52, 199, 89, 0.08);
  color: var(--status-green);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}
.stat-hist-btn:hover { background: rgba(52, 199, 89, 0.16); }
.custom-history-area {
  position: relative;
  margin: 12px 0;
  padding: 14px;
  border-radius: 16px;
  background: rgba(0, 0, 0, 0.02);
  border: 1px solid rgba(0, 0, 0, 0.06);
}
.hist-close {
  position: absolute;
  top: 12px;
  right: 14px;
  border: none;
  background: none;
  color: var(--text-tertiary);
  font-size: 12px;
  cursor: pointer;
  z-index: 5;
}
.hist-close:hover { color: var(--status-red); }

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

/* 待更新软件(参照"系统服务"展示风格) */
.apt-status {
  padding: 20px;
}
.apt-count {
  font-size: 12px;
  color: var(--text-tertiary);
  font-weight: 500;
}
.apt-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 480px;
  overflow-y: auto;
}
.apt-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-radius: 10px;
  transition: background 0.15s ease;
}
.apt-item:hover {
  background: rgba(0, 0, 0, 0.02);
}
.apt-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  margin-right: 12px;
}
.apt-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: 'SF Mono', 'JetBrains Mono', monospace;
}
.apt-vers {
  display: inline-flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 11px;
  font-family: 'SF Mono', 'JetBrains Mono', monospace;
}
.apt-old {
  color: var(--text-tertiary);
  word-break: break-all;
}
.apt-arrow {
  color: var(--status-orange, #ff9500);
  font-weight: 700;
  flex-shrink: 0;
}
.apt-new {
  color: var(--status-green, #34c759);
  font-weight: 600;
  word-break: break-all;
}
.apt-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
  background: rgba(255, 149, 0, 0.12);
  color: var(--status-orange, #ff9500);
}
.apt-more {
  padding: 8px 4px 2px;
  font-size: 11px;
  color: var(--text-tertiary);
  text-align: center;
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

/* 本月流量汇总条 */
.month-summary {
  padding: 16px 20px;
  margin-bottom: 16px;
}

.month-summary-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.month-summary-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

.month-tz {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
  background: rgba(0, 0, 0, 0.05);
  border-radius: 8px;
  padding: 1px 6px;
  margin-left: 6px;
}

.month-pct {
  font-size: 14px;
  font-weight: 700;
  color: var(--status-green, #34c759);
}

.month-pct.warning { color: #ff9500; }
.month-pct.danger { color: #ff3b30; }

.month-used {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.month-quota {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-tertiary);
}

.month-bar {
  height: 6px;
  background: rgba(0, 0, 0, 0.05);
  border-radius: 6px;
  overflow: hidden;
  margin-top: 10px;
}

.month-bar-fill {
  height: 100%;
  border-radius: 6px;
  background: linear-gradient(90deg, #a78bfa, #7c3aed);
  transition: width 0.6s cubic-bezier(0.22, 1, 0.36, 1);
}

.month-bar-fill.warning { background: linear-gradient(90deg, #ffb340, #ff9500); }
.month-bar-fill.danger { background: linear-gradient(90deg, #ff6b6b, #ff3b30); }

.month-hint {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 8px;
}

.empty {
  text-align: center;
  padding: 40px;
  color: var(--text-tertiary);
  font-size: 14px;
}
</style>
