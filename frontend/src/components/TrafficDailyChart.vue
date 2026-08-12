<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps({
  serverName: { type: String, required: true },
  days: { type: Number, default: 30 }
})

const chartRef = ref(null)
let chart = null
let loadTimer = null

const fmtBytes = (v) => {
  if (v === null || v === undefined || v < 0) return '-'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.min(Math.floor(Math.log(Math.max(v, 1)) / Math.log(1024)), units.length - 1)
  return `${(v / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

async function loadDaily() {
  try {
    const token = localStorage.getItem('monitor_token')
    const res = await fetch(`/api/servers/${props.serverName}/traffic/daily?days=${props.days}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {}
    })
    if (!res.ok) return
    const rows = await res.json()
    if (!chart) return
    chart.setOption({
      xAxis: { data: rows.map(r => r.date) },
      series: [
        { name: '入站', data: rows.map(r => r.recv_bytes) },
        { name: '出站', data: rows.map(r => r.sent_bytes) }
      ]
    })
  } catch (e) {
    console.error('Failed to load daily traffic:', e)
  }
}

onMounted(() => {
  if (chartRef.value) {
    chart = echarts.init(chartRef.value)
    chart.setOption({
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(255, 255, 255, 0.95)',
        borderColor: 'rgba(0, 0, 0, 0.06)',
        textStyle: { color: '#1d1d1f', fontSize: 12 },
        formatter: (params) => {
          let html = `<div style="font-weight:600;margin-bottom:4px">${params[0].axisValue}</div>`
          params.forEach(p => {
            html += `<div style="display:flex;align-items:center;gap:6px;font-size:12px">
              <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${p.color}"></span>
              ${p.seriesName}: <strong>${fmtBytes(p.value)}</strong></div>`
          })
          return html
        }
      },
      legend: {
        top: 0,
        right: 0,
        icon: 'circle',
        itemWidth: 8,
        itemHeight: 8,
        textStyle: { color: '#86868b', fontSize: 12 }
      },
      grid: { top: 36, right: 16, bottom: 24, left: 56 },
      xAxis: {
        type: 'category',
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#aeaeb2', fontSize: 11 }
      },
      yAxis: {
        type: 'value',
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: 'rgba(0, 0, 0, 0.04)', type: 'dashed' } },
        axisLabel: { color: '#aeaeb2', fontSize: 11, formatter: (v) => fmtBytes(v) }
      },
      series: [
        { name: '入站', type: 'bar', stack: 't', barWidth: '50%', itemStyle: { color: '#34c759' }, data: [] },
        { name: '出站', type: 'bar', stack: 't', barWidth: '50%', itemStyle: { color: '#ff3b30', borderRadius: [4, 4, 0, 0] }, data: [] }
      ]
    })

    const observer = new ResizeObserver(() => chart?.resize())
    observer.observe(chartRef.value)

    loadDaily()
    loadTimer = setInterval(loadDaily, 300000) // 5 分钟自动刷新
  }
})

onUnmounted(() => {
  clearInterval(loadTimer)
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div class="traffic-daily">
    <h4 style="margin:0 0 8px;font-size:13px;color:var(--text-secondary)">近 {{ days }} 天每日流量</h4>
    <div ref="chartRef" class="daily-canvas"></div>
  </div>
</template>

<style scoped>
.daily-canvas {
  width: 100%;
  height: 260px;
}
</style>
