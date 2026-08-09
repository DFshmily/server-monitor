<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  services: {
    type: Array,
    default: () => []
  }
})

const filter = ref('all') // all | abnormal

const isAbnormal = (s) => {
  const st = (s.active || s.status || '').toLowerCase()
  return st !== 'active' && st !== 'running'
}

const sorted = computed(() => {
  const arr = [...props.services]
  // 异常/非运行置顶，其余按名称排序
  const abnormal = arr.filter(isAbnormal).sort((a, b) => a.name.localeCompare(b.name))
  const normal = arr.filter((s) => !isAbnormal(s)).sort((a, b) => a.name.localeCompare(b.name))
  return { abnormal, normal }
})

const visible = computed(() => {
  const { abnormal, normal } = sorted.value
  if (filter.value === 'abnormal') return abnormal
  return [...abnormal, ...normal]
})

const getStatusClass = (service) => {
  const st = (service.active || service.status || '').toLowerCase()
  if (st === 'active' || st === 'running') return 'active'
  if (st === 'failed') return 'failed'
  if (st === 'inactive' || st === 'dead') return 'stopped'
  return 'unknown'
}

const getStatusLabel = (service) => {
  const st = (service.active || service.status || '').toLowerCase()
  if (st === 'active' || st === 'running') return '运行中'
  if (st === 'failed') return '异常'
  if (st === 'inactive' || st === 'dead') return '已停止'
  return service.active || service.status || '未知'
}

const abnormalCount = computed(() => sorted.value.abnormal.length)
</script>

<template>
  <div class="service-status glass-card">
    <div class="table-header">
      <h3 class="chart-title">系统服务</h3>
      <div class="header-right">
        <span class="service-count">{{ services.length }} 个服务</span>
        <div class="filter-tabs">
          <button
            class="filter-tab"
            :class="{ active: filter === 'all' }"
            @click="filter = 'all'"
          >全部</button>
          <button
            class="filter-tab"
            :class="{ active: filter === 'abnormal', danger: abnormalCount > 0 }"
            @click="filter = 'abnormal'"
          >仅异常<span v-if="abnormalCount > 0" class="badge-num">{{ abnormalCount }}</span></button>
        </div>
      </div>
    </div>

    <div class="service-list">
      <div
        v-for="service in visible"
        :key="service.name"
        class="service-item"
        :class="{ 'is-abnormal': isAbnormal(service) }"
      >
        <div class="service-info">
          <span class="service-name">{{ service.name }}</span>
          <span class="service-desc">{{ service.sub || service.description || '' }}</span>
        </div>
        <span class="service-badge" :class="getStatusClass(service)">
          {{ getStatusLabel(service) }}
        </span>
      </div>
      <div v-if="visible.length === 0" class="empty">
        {{ filter === 'abnormal' ? '🎉 全部服务正常' : '暂无服务数据' }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.service-status {
  padding: 20px;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 10px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.service-count {
  font-size: 12px;
  color: var(--text-tertiary);
  font-weight: 500;
}

.filter-tabs {
  display: flex;
  gap: 4px;
  background: rgba(0, 0, 0, 0.04);
  border-radius: 10px;
  padding: 3px;
}

.filter-tab {
  border: none;
  background: transparent;
  padding: 5px 12px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.filter-tab.active {
  background: #fff;
  color: var(--text-primary);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}

.filter-tab.danger:not(.active) {
  color: var(--status-red);
}

.badge-num {
  background: var(--status-red);
  color: #fff;
  border-radius: 10px;
  font-size: 10px;
  padding: 1px 6px;
  font-weight: 700;
}

.service-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 480px;
  overflow-y: auto;
}

.service-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-radius: 10px;
  transition: background 0.15s ease;
}

.service-item:hover {
  background: rgba(0, 0, 0, 0.02);
}

.service-item.is-abnormal {
  background: rgba(255, 59, 48, 0.05);
}

.service-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.service-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: 'SF Mono', 'JetBrains Mono', monospace;
}

.service-desc {
  font-size: 11px;
  color: var(--text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.service-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
}

.service-badge.active {
  background: rgba(52, 199, 89, 0.12);
  color: var(--status-green);
}

.service-badge.failed {
  background: rgba(255, 59, 48, 0.12);
  color: var(--status-red);
}

.service-badge.stopped {
  background: rgba(255, 149, 0, 0.12);
  color: var(--status-orange);
}

.service-badge.unknown {
  background: rgba(0, 0, 0, 0.06);
  color: var(--text-secondary);
}

.empty {
  text-align: center;
  color: var(--text-tertiary);
  padding: 24px;
  font-size: 13px;
}
</style>
