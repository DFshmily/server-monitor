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
  max: { type: Number, default: null },
  // 事件标注（Grafana Annotations 风格）：[{ts, kind, message}]
  annotations: { type: Array, default: () => [] },
  // 维护窗口区域高亮：[{start, end, note}]
  markAreas: { type: Array, default: () => [] }
})

const chartRef = ref(null)
let chart = null

const tsOf = (d) => d?.[props.xKey] ?? d?.time ?? d?.timestamp
const fmtTime = (ts, withDate) => {
  if (!ts) return ''
  // Handle both unix seconds and milliseconds; force Beijing time (UTC+8)
  const ms = (ts > 1e12 ? ts : ts * 1000) + 8 * 3600 * 1000
  const d = new Date(ms)
  const p = (n) => String(n).padStart(2, '0')
  return withDate
    ? `${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`
    : `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`
}
// 数据跨度 > 1.5 天时 x 轴带日期（1d / 1mon / 自定义视图）
const spanDays = computed(() => {
  const d = props.data
  if (!d || d.length < 2) return 0
  const first = tsOf(d[0]) || 0
  const last = tsOf(d[d.length - 1]) || 0
  return Math.abs(last - first) / 86400
})
const withDate = computed(() => spanDays.value > 1.5)

const MARK_STYLE = {
  threshold: { color: '#ff3b30', label: '🚨' },
  offline: { color: '#ff9500', label: '⚠️' },
  recovered: { color: '#34c759', label: '✅' }
}

// 事件 ts → 最近数据点索引（category 轴按索引定位最可靠）
const indexOfTs = (ts) => {
  const d = props.data
  if (!d || d.length === 0) return 0
  let best = 0
  let bestDiff = Infinity
  d.forEach((row, i) => {
    const diff = Math.abs((tsOf(row) || 0) - ts)
    if (diff < bestDiff) {
      bestDiff = diff
      best = i
    }
  })
  return best
}

const buildMarkLine = () => {
  // 最多标 40 条，避免图表被线淹没
  const xData = props.data.map(d => fmtTime(tsOf(d), withDate.value))
  const list = (props.annotations || []).slice(-40)
  if (list.length === 0 || xData.length === 0) return undefined
  return {
    symbol: 'none',
    animation: false,
    // category 轴用最近数据点的类目名定位；两点([min,max])让竖线贯穿绘图区
    data: list.map(a => {
      const st = MARK_STYLE[a.kind] || { color: '#8e8e93', label: '•' }
      const x = xData[indexOfTs(a.ts)]
      return [{
        xAxis: x,
        yAxis: 'min',
        lineStyle: { color: st.color, width: 1.2, type: 'dashed' },
        label: { formatter: st.label, position: 'insideStartBottom', fontSize: 10, color: st.color },
        tooltip: { formatter: () => a.message || a.kind }
      }, {
        xAxis: x,
        yAxis: 'max'
      }]
    })
  }
}

const buildMarkArea = () => {
  const list = props.markAreas || []
  const xData = props.data.map(d => fmtTime(tsOf(d), withDate.value))
  if (list.length === 0 || xData.length === 0) return undefined
  return {
    silent: true,
    itemStyle: { color: 'rgba(124, 58, 237, 0.10)' },
    data: list.map(m => [{
      xAxis: xData[indexOfTs(m.start)],
      name: m.note || '维护'
    }, {
      xAxis: xData[indexOfTs(m.end)]
    }])
  }
}

const buildOption = () => {
  const xData = props.data.map(d => fmtTime(tsOf(d), withDate.value))
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
    markLine: i === 0 ? buildMarkLine() : undefined,
    markArea: i === 0 ? buildMarkArea() : undefined,
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

watch(() => [props.data, props.annotations, props.markAreas], () => {
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
