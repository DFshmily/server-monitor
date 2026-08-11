<script setup>
import { ref, watch, computed, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])

const props = defineProps({
  title: { type: String, default: '' },
  data: { type: Array, default: () => [] },
  xKey: { type: String, default: 'timestamp' },
  yKeys: { type: Array, default: () => ['value'] },
  yLabels: { type: Array, default: () => [''] },
  colors: { type: Array, default: () => ['#7c3aed'] },
  unit: { type: String, default: '%' },
  areaStyle: { type: Boolean, default: true },
  smooth: { type: Boolean, default: true },
  max: { type: Number, default: null }
})

const chartRef = ref(null)
let chart = null

const formatTime = (ts) => {
  if (!ts) return ''
  // Handle both unix seconds and milliseconds
  const ms = ts > 1e12 ? ts : ts * 1000
  const d = new Date(ms)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

const buildOption = () => {
  const xData = props.data.map(d => formatTime(d[props.xKey] || d.time || d.timestamp))
  const series = props.yKeys.map((key, i) => ({
    name: props.yLabels[i] || key,
    type: 'line',
    smooth: props.smooth,
    symbol: 'none',
    lineStyle: {
      width: 2.5,
      color: props.colors[i] || '#7c3aed'
    },
    itemStyle: {
      color: props.colors[i] || '#7c3aed'
    },
    areaStyle: props.areaStyle ? {
      color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: (props.colors[i] || '#7c3aed') + '40' },
        { offset: 1, color: (props.colors[i] || '#7c3aed') + '05' }
      ])
    } : undefined,
    data: props.data.map(d => d[key] ?? d[key.replace('_', '')] ?? 0)
  }))

  return {
    grid: {
      top: 30,
      right: 16,
      bottom: 24,
      left: 40
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(255, 255, 255, 0.95)',
      borderColor: 'rgba(0, 0, 0, 0.06)',
      borderWidth: 1,
      textStyle: {
        color: '#1d1d1f',
        fontSize: 12
      },
      formatter: (params) => {
        let html = `<div style="font-weight:600;margin-bottom:4px">${params[0].axisValue}</div>`
        params.forEach(p => {
          html += `<div style="display:flex;align-items:center;gap:6px;font-size:12px">
            <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${p.color}"></span>
            ${p.seriesName}: <strong>${typeof p.value === 'number' ? p.value.toFixed(1) : p.value}${props.unit}</strong>
          </div>`
        })
        return html
      }
    },
    xAxis: {
      type: 'category',
      data: xData,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: '#aeaeb2',
        fontSize: 11,
        margin: 8
      }
    },
    yAxis: {
      type: 'value',
      max: props.max,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: {
        lineStyle: {
          color: 'rgba(0, 0, 0, 0.04)',
          type: 'dashed'
        }
      },
      axisLabel: {
        color: '#aeaeb2',
        fontSize: 11,
        formatter: `{value}${props.unit}`
      }
    },
    series
  }
}

onMounted(() => {
  if (chartRef.value) {
    chart = echarts.init(chartRef.value)
    chart.setOption(buildOption())

    const observer = new ResizeObserver(() => {
      chart?.resize()
    })
    observer.observe(chartRef.value)
  }
})

watch(() => props.data, () => {
  if (chart) {
    chart.setOption(buildOption())
  }
}, { deep: true })

onUnmounted(() => {
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div class="chart-container">
    <div v-if="title" class="chart-title">{{ title }}</div>
    <div ref="chartRef" class="chart-canvas"></div>
  </div>
</template>

<style scoped>
.chart-canvas {
  width: 100%;
  height: 260px;
}
</style>
