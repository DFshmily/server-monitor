<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useServersStore } from '../stores/servers'
import { storeToRefs } from 'pinia'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const store = useServersStore()
const { servers } = storeToRefs(store)

const serverA = ref('')
const serverB = ref('')
const selectedMetric = ref('cpu')
const selectedInterval = ref('1min')

// 对比模式: 'servers'=双机对比 | 'time'=时段对比(今vs昨 / 本周vs上周)
const compareMode = ref('servers')
const timePreset = ref('day')      // 'day' | 'week'
const serverSingle = ref('')

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

const METRICS = [
  { key: 'cpu', label: 'CPU 使用率', unit: '%', color: '#7c3aed' },
  { key: 'memory', label: '内存使用率', unit: '%', color: '#007aff' },
  { key: 'disk', label: '磁盘使用率', unit: '%', color: '#ff9500' },
  { key: 'net_in', label: '网络入速率', unit: ' B/s', color: '#34c759' },
  { key: 'net_out', label: '网络出速率', unit: ' B/s', color: '#ff3b30' },
  { key: 'load1', label: '负载 1 分钟', unit: '', color: '#a78bfa' }
]
const INTERVALS = [
  { value: 'realtime', label: '实时' },
  { value: '1min', label: '1分钟' },
  { value: '5min', label: '5分钟' },
  { value: '1h', label: '1小时' },
  { value: '1d', label: '1天' }
]

const metric = computed(() => METRICS.find(m => m.key === selectedMetric.value) || METRICS[0])
const serverList = computed(() => store.serverList)

const displayName = (name) => {
  const s = servers.value[name]
  if (s?.alias) return s.alias
  if (name === 'tencent') return '广州'
  if (name === 'oracle') return 'ORACLE'
  return name
}

// 从最新/历史数据提取指标值（与 ServerDetail 同一套路径）
function extractValue(data, key) {
  if (!data) return null
  if (key === 'cpu') return data.cpu?.percent ?? null
  if (key === 'memory') return data.memory?.percent ?? null
  if (key === 'disk') {
    const dd = data.disk || {}
    if (dd.percent !== undefined && dd.percent > 0) return dd.percent
    const parts = dd.partitions || []
    const root = parts.find(p => p.mountpoint === '/') || parts[0]
    return root?.percent ?? null
  }
  if (key === 'net_in') {
    const nd = data.network || {}
    if (nd.bytes_recv_rate !== undefined) return nd.bytes_recv_rate
    const ifaces = nd.interfaces || {}
    return Object.values(ifaces).reduce((s, i) => s + (i.bytes_recv || 0), 0) || null
  }
  if (key === 'net_out') {
    const nd = data.network || {}
    if (nd.bytes_sent_rate !== undefined) return nd.bytes_sent_rate
    const ifaces = nd.interfaces || {}
    return Object.values(ifaces).reduce((s, i) => s + (i.bytes_sent || 0), 0) || null
  }
  if (key === 'load1') return data.load?.load1 ?? null
  return null
}

const historyA = ref([])
const historyB = ref([])

// ── 时段对比: 计算当前/对比两个时间窗(北京时间对齐) ──
function timeWindows() {
  const now = Date.now() + 8 * 3600 * 1000  // Beijing
  const nowSec = Math.floor(Date.now() / 1000)
  if (timePreset.value === 'day') {
    const dayMs = 86400 * 1000
    const todayStart = Math.floor(now / dayMs) * dayMs - 8 * 3600 * 1000  // UTC unix of Beijing midnight
    return {
      cur: [Math.floor(todayStart / 1000), nowSec],
      prev: [Math.floor((todayStart - dayMs) / 1000), Math.floor(todayStart / 1000)],
    }
  }
  // week: 本周(周一起) vs 上周同一时刻
  const weekMs = 7 * 86400 * 1000
  const d = new Date(now)
  const midnight = Math.floor(now / (86400 * 1000)) * (86400 * 1000)
  const dow = d.getUTCDay() === 0 ? 7 : d.getUTCDay()
  const weekStartBeijing = midnight - (dow - 1) * 86400 * 1000
  const weekStartUnix = Math.floor((weekStartBeijing - 8 * 3600 * 1000) / 1000)
  return {
    cur: [weekStartUnix, nowSec],
    prev: [weekStartUnix - weekMs / 1000, weekStartUnix],
  }
}

async function loadTimeCompare() {
  if (!serverSingle.value) return
  const { cur, prev } = timeWindows()
  const interval = timePreset.value === 'day' ? '5min' : '1h'
  const limit = timePreset.value === 'day' ? 288 : 24 * 8
  const name = serverSingle.value
  const [c, p] = await Promise.all([
    store.fetchHistory(name, interval, limit, cur[0], cur[1]),
    store.fetchHistory(name, interval, limit, prev[0], prev[1]),
  ])
  historyA.value = c || []
  historyB.value = p || []
}

// 时段对比的统计摘要: 当前窗口 vs 对比窗口的平均值与变化
const timeStats = computed(() => {
  if (!historyA.value.length || !historyB.value.length) return null
  const avg = (rows) => {
    const vals = rows.map(r => extractValue(r.data, selectedMetric.value)).filter(v => v !== null && !Number.isNaN(v))
    if (!vals.length) return null
    return vals.reduce((s, v) => s + v, 0) / vals.length
  }
  const aAvg = avg(historyA.value), bAvg = avg(historyB.value)
  if (aAvg === null || bAvg === null || bAvg === 0) return { aAvg, bAvg, delta: null }
  return { aAvg, bAvg, delta: ((aAvg - bAvg) / bAvg) * 100 }
})

// 时段对比合并数据: 把"对比期"平移到当前期的时刻轴上(按窗口内相对偏移对齐)
const mergedTimeData = computed(() => {
  if (!historyA.value.length) return { x: [], a: [], b: [] }
  const rows = [...historyA.value].sort((p, q) => p.timestamp - q.timestamp)
  const base = rows[0].timestamp
  const x = rows.map(r => r.timestamp)
  const a = rows.map(r => extractValue(r.data, selectedMetric.value))
  // 对比期按 (自身窗口起点 -> 当前窗口起点) 平移
  const prevRows = historyB.value.map(r => ({ ts: r.timestamp, v: extractValue(r.data, selectedMetric.value) })).filter(r => r.v !== null)
  if (!prevRows.length) return { x, a, b: [] }
  const prevBase = Math.min(...prevRows.map(r => r.ts))
  const shift = base - prevBase
  const mapB = new Map(prevRows.map(r => [r.ts + shift, r.v]))
  const b = x.map(ts => mapB.get(ts) ?? null)
  return { x, a, b }
})

async function loadBoth() {
  if (!serverA.value || !serverB.value) return
  const [a, b] = await Promise.all([
    store.fetchHistory(serverA.value, selectedInterval.value, 200),
    store.fetchHistory(serverB.value, selectedInterval.value, 200)
  ])
  historyA.value = a || []
  historyB.value = b || []
}

// 合并两条时间线（时间戳并集，各自缺失点为 null）
const mergedData = computed(() => {
  if (compareMode.value === 'time') return mergedTimeData.value
  const tsSet = new Set()
  const mapA = new Map(), mapB = new Map()
  for (const d of historyA.value) { tsSet.add(d.timestamp); mapA.set(d.timestamp, extractValue(d.data, selectedMetric.value)) }
  for (const d of historyB.value) { tsSet.add(d.timestamp); mapB.set(d.timestamp, extractValue(d.data, selectedMetric.value)) }
  const sorted = [...tsSet].sort((x, y) => x - y)
  return {
    x: sorted,
    a: sorted.map(ts => mapA.get(ts) ?? null),
    b: sorted.map(ts => mapB.get(ts) ?? null)
  }
})

const chartRef = ref(null)
let chart = null

const fmtTime = (ts) => {
  if (!ts) return ''
  const ms = (ts > 1e12 ? ts : ts * 1000) + 8 * 3600 * 1000
  const d = new Date(ms)
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`
}

const fmtBytes = (v) => {
  if (v === null || v === undefined) return '-'
  if (v >= 1024 * 1024 * 1024) return (v / 1024 / 1024 / 1024).toFixed(2) + ' GB/s'
  if (v >= 1024 * 1024) return (v / 1024 / 1024).toFixed(1) + ' MB/s'
  if (v >= 1024) return (v / 1024).toFixed(1) + ' KB/s'
  return v.toFixed(0) + ' B/s'
}

// 首页大数字格式化：网络类显示可读速率，其余保留 1 位小数
const formatVal = (v) => {
  if (v === null || v === undefined) return '-'
  return selectedMetric.value.startsWith('net_') ? fmtBytes(v) : `${Number(v).toFixed(1)}${metric.value.unit}`
}

function buildOption() {
  const { x, a, b } = mergedData.value
  const isNet = selectedMetric.value.startsWith('net_')
  const isTimeMode = compareMode.value === 'time'
  const nameA = isTimeMode
    ? (timePreset.value === 'day' ? '今天' : '本周')
    : displayName(serverA.value) || '服务器 A'
  const nameB = isTimeMode
    ? (timePreset.value === 'day' ? '昨天' : '上周')
    : displayName(serverB.value) || '服务器 B'
  return {
    legend: {
      top: 0,
      right: 0,
      icon: 'circle',
      itemWidth: 8,
      itemHeight: 8,
      textStyle: { color: '#86868b', fontSize: 12 }
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(255, 255, 255, 0.95)',
      borderColor: 'rgba(0, 0, 0, 0.06)',
      textStyle: { color: '#1d1d1f', fontSize: 12 },
      formatter: (params) => {
        let html = `<div style="font-weight:600;margin-bottom:4px">${params[0].axisValue}</div>`
        params.forEach(p => {
          let val = p.value
          if (val === null || val === undefined) val = '-'
          else if (isNet) val = fmtBytes(val)
          else val = Number(val).toFixed(1) + metric.value.unit
          html += `<div style="display:flex;align-items:center;gap:6px;font-size:12px">
            <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${p.color}"></span>
            ${p.seriesName}: <strong>${val}</strong></div>`
        })
        return html
      }
    },
    grid: { top: 40, right: 20, bottom: 28, left: 56 },
    xAxis: {
      type: 'category',
      data: x.map(fmtTime),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#aeaeb2', fontSize: 11 }
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: 'rgba(0, 0, 0, 0.04)', type: 'dashed' } },
      axisLabel: {
        color: '#aeaeb2',
        fontSize: 11,
        formatter: (v) => isNet ? fmtBytes(v) : `${v}${metric.value.unit}`
      }
    },
    series: [
      {
        name: nameA,
        type: 'line',
        smooth: true,
        symbol: 'none',
        connectNulls: false,
        lineStyle: { width: 2.5, color: '#7c3aed' },
        itemStyle: { color: '#7c3aed' },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(124, 58, 237, 0.25)' },
          { offset: 1, color: 'rgba(124, 58, 237, 0.02)' }
        ]) },
        data: a
      },
      {
        name: nameB,
        type: 'line',
        smooth: true,
        symbol: 'none',
        connectNulls: false,
        lineStyle: { width: 2.5, color: '#007aff', type: isTimeMode ? 'dashed' : 'solid' },
        itemStyle: { color: '#007aff' },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(0, 122, 255, 0.2)' },
          { offset: 1, color: 'rgba(0, 122, 255, 0.02)' }
        ]) },
        data: b
      }
    ]
  }
}

watch(mergedData, () => {
  if (chart) chart.setOption(buildOption())
}, { deep: true })

watch([serverA, serverB, selectedInterval], () => {
  if (compareMode.value !== 'servers') return
  if (serverA.value && serverB.value) loadBoth()
})

watch(serverSingle, () => {
  if (compareMode.value === 'time') loadTimeCompare()
})

watch(timePreset, () => {
  if (compareMode.value === 'time') loadTimeCompare()
})

watch(compareMode, () => {
  if (compareMode.value === 'time') loadTimeCompare()
  else if (serverA.value && serverB.value) loadBoth()
})

watch(selectedMetric, () => {
  if (chart) chart.setOption(buildOption())
})

// 实时模式：WS 推送增量追加
watch(servers, (val) => {
  if (selectedInterval.value !== 'realtime') return
  const latestA = val[serverA.value]?.latest
  const latestB = val[serverB.value]?.latest
  if (latestA && Object.keys(latestA).length) {
    historyA.value = [...historyA.value, { timestamp: latestA.timestamp || Math.floor(Date.now() / 1000), data: latestA }].slice(-200)
  }
  if (latestB && Object.keys(latestB).length) {
    historyB.value = [...historyB.value, { timestamp: latestB.timestamp || Math.floor(Date.now() / 1000), data: latestB }].slice(-200)
  }
}, { deep: true })

onMounted(async () => {
  await store.fetchServers()
  const list = serverList.value
  if (list.length >= 2) {
    serverA.value = list[0].name
    serverB.value = list[1].name
  } else if (list.length === 1) {
    serverA.value = list[0].name
  }
  if (list.length >= 1) serverSingle.value = list[0].name
  store.connectWebSocket()
  if (chartRef.value) {
    chart = echarts.init(chartRef.value)
    chart.setOption(buildOption())
    const observer = new ResizeObserver(() => chart?.resize())
    observer.observe(chartRef.value)
  }
})

onUnmounted(() => {
  store.disconnectWebSocket()
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <h1 class="section-title">⚡ 双机对比</h1>
        <p class="subtitle">同一指标下两台服务器的实时走势对比</p>
      </div>
    </div>

    <div class="controls glass-card">
      <div class="mode-pick">
        <button class="interval-btn" :class="{ active: compareMode === 'servers' }" @click="compareMode = 'servers'">🖥 双机对比</button>
        <button class="interval-btn" :class="{ active: compareMode === 'time' }" @click="compareMode = 'time'">📅 时段对比</button>
      </div>
      <div v-if="compareMode === 'servers'" class="server-pick">
        <select v-model="serverA" class="count-input">
          <option v-for="s in serverList" :key="s.name" :value="s.name">{{ displayName(s.name) }}</option>
        </select>
        <span class="vs">VS</span>
        <select v-model="serverB" class="count-input">
          <option v-for="s in serverList" :key="s.name" :value="s.name">{{ displayName(s.name) }}</option>
        </select>
      </div>
      <div v-else class="server-pick">
        <select v-model="serverSingle" class="count-input">
          <option v-for="s in serverList" :key="s.name" :value="s.name">{{ displayName(s.name) }}</option>
        </select>
        <span class="vs">·</span>
        <button class="interval-btn" :class="{ active: timePreset === 'day' }" @click="timePreset = 'day'">今 vs 昨</button>
        <button class="interval-btn" :class="{ active: timePreset === 'week' }" @click="timePreset = 'week'">本周 vs 上周</button>
      </div>
      <div class="metric-pick">
        <button
          v-for="m in METRICS"
          :key="m.key"
          class="interval-btn"
          :class="{ active: selectedMetric === m.key }"
          @click="selectedMetric = m.key"
        >{{ m.label }}</button>
      </div>
      <div v-if="compareMode === 'servers'" class="interval-pick">
        <button
          v-for="opt in INTERVALS"
          :key="opt.value"
          class="interval-btn"
          :class="{ active: selectedInterval === opt.value }"
          @click="selectedInterval = opt.value"
        >{{ opt.label }}</button>
      </div>
    </div>

    <div v-if="compareMode === 'time' && timeStats" class="stat-row">
      <div class="stat-card glass-card">
        <div class="stat-label">当前期均值</div>
        <div class="stat-value" style="color:#7c3aed">{{ formatVal(timeStats.aAvg) }}</div>
      </div>
      <div class="stat-card glass-card">
        <div class="stat-label">对比期均值</div>
        <div class="stat-value" style="color:#007aff">{{ formatVal(timeStats.bAvg) }}</div>
      </div>
      <div class="stat-card glass-card">
        <div class="stat-label">变化</div>
        <div class="stat-value" :style="{ color: timeStats.delta == null ? '#86868b' : timeStats.delta > 0 ? '#ff3b30' : timeStats.delta < 0 ? '#34c759' : '#86868b' }">
          {{ timeStats.delta == null ? '-' : (timeStats.delta > 0 ? '+' : '') + timeStats.delta.toFixed(1) + '%' }}
        </div>
      </div>
    </div>

    <div class="stat-row">
      <div class="stat-card glass-card">
        <div class="stat-label">{{ displayName(serverA) }}</div>
        <div class="stat-value" :style="{ color: '#7c3aed' }">
          {{ extractValue(servers[serverA]?.latest, selectedMetric) === null ? '-' : formatVal(extractValue(servers[serverA]?.latest, selectedMetric)) }}
        </div>
      </div>
      <div class="stat-card glass-card">
        <div class="stat-label">{{ displayName(serverB) }}</div>
        <div class="stat-value" :style="{ color: '#007aff' }">
          {{ extractValue(servers[serverB]?.latest, selectedMetric) === null ? '-' : formatVal(extractValue(servers[serverB]?.latest, selectedMetric)) }}
        </div>
      </div>
    </div>

    <div class="glass-card chart-card">
      <div ref="chartRef" class="compare-canvas"></div>
      <div v-if="mergedData.x.length === 0" class="empty-tip">暂无数据，请选择两台服务器</div>
    </div>
  </div>
</template>

<style scoped>
.subtitle {
  font-size: 15px;
  color: var(--text-secondary);
  margin-top: 4px;
}

.controls {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 20px;
  margin-bottom: 16px;
}

.server-pick {
  display: flex;
  align-items: center;
  gap: 12px;
}

.mode-pick {
  display: flex;
  gap: 6px;
}

.server-pick .count-input {
  padding: 8px 12px;
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 10px;
  background: var(--glass-bg, #fff);
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  outline: none;
  cursor: pointer;
  min-width: 140px;
}

.server-pick .count-input:focus {
  border-color: var(--purple-500, #8b5cf6);
  box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.12);
}

.vs {
  font-weight: 700;
  font-size: 13px;
  color: var(--text-tertiary);
  letter-spacing: 1px;
}

.metric-pick,
.interval-pick {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.interval-btn {
  padding: 6px 14px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 20px;
  background: transparent;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s ease;
}

.interval-btn:hover {
  border-color: var(--purple-400, #a78bfa);
}

.interval-btn.active {
  background: var(--purple-600, #7c3aed);
  border-color: var(--purple-600, #7c3aed);
  color: #fff;
}

.stat-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}

.stat-card {
  padding: 18px 22px;
}

.stat-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.stat-value {
  font-size: 30px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.chart-card {
  padding: 18px 20px 12px;
  position: relative;
}

.compare-canvas {
  width: 100%;
  height: 380px;
}

.empty-tip {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  color: var(--text-tertiary);
  pointer-events: none;
}
</style>
