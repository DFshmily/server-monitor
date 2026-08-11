<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps({
  days: { type: Number, default: 14 }
})

const chartRef = ref(null)
let chart = null
let fetchTimer = null

async function loadStats() {
  try {
    const res = await fetch(`/api/alerts/stats?days=${props.days}`, {
      headers: { Authorization: `Bearer ${localStorage.getItem('monitor_token')}` }
    })
    if (!res.ok) return
    const rows = await res.json()
    if (chart) {
      chart.setOption({
        xAxis: { data: rows.map(r => r.date) },
        series: [
          { name: '告警', data: rows.map(r => r.threshold) },
          { name: '离线', data: rows.map(r => r.offline) },
          { name: '恢复', data: rows.map(r => r.recovered) }
        ]
      })
    }
  } catch (e) {
    console.error('Failed to load alert stats:', e)
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
        textStyle: { color: '#1d1d1f', fontSize: 12 }
      },
      legend: {
        top: 0,
        right: 0,
        icon: 'circle',
        itemWidth: 8,
        itemHeight: 8,
        textStyle: { color: '#86868b', fontSize: 12 }
      },
      grid: { top: 36, right: 16, bottom: 24, left: 40 },
      xAxis: {
        type: 'category',
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#aeaeb2', fontSize: 11 }
      },
      yAxis: {
        type: 'value',
        minInterval: 1,
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: 'rgba(0, 0, 0, 0.04)', type: 'dashed' } },
        axisLabel: { color: '#aeaeb2', fontSize: 11 }
      },
      series: [
        { name: '告警', type: 'bar', stack: 'a', barWidth: '45%', itemStyle: { color: '#7c3aed', borderRadius: [0, 0, 0, 0] } },
        { name: '离线', type: 'bar', stack: 'a', barWidth: '45%', itemStyle: { color: '#ff9500' } },
        { name: '恢复', type: 'bar', stack: 'a', barWidth: '45%', itemStyle: { color: '#34c759', borderRadius: [4, 4, 0, 0] } }
      ]
    })

    const observer = new ResizeObserver(() => chart?.resize())
    observer.observe(chartRef.value)

    loadStats()
    // Auto-refresh every 2 minutes while the admin page is open
    fetchTimer = setInterval(loadStats, 120000)
  }
})

onUnmounted(() => {
  clearInterval(fetchTimer)
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div class="alert-stats">
    <h4 style="margin:0 0 8px;font-size:13px;color:var(--text-secondary)">近 {{ days }} 天告警统计</h4>
    <div ref="chartRef" class="stats-canvas"></div>
  </div>
</template>

<style scoped>
.stats-canvas {
  width: 100%;
  height: 200px;
}
</style>
