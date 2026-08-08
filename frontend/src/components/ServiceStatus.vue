<script setup>
defineProps({
  services: {
    type: Array,
    default: () => []
  }
})

const getStatusClass = (status) => {
  const s = (status || '').toLowerCase()
  if (s.includes('running') || s.includes('active')) return 'active'
  if (s.includes('dead') || s.includes('failed') || s.includes('inactive')) return 'failed'
  if (s.includes('exit') || s.includes('stop')) return 'stopped'
  return 'unknown'
}

const getStatusLabel = (status) => {
  const s = (status || '').toLowerCase()
  if (s.includes('running') || s.includes('active')) return '运行中'
  if (s.includes('dead') || s.includes('failed')) return '异常'
  if (s.includes('inactive') || s.includes('stop')) return '已停止'
  if (s.includes('exit')) return '已退出'
  return status || '未知'
}
</script>

<template>
  <div class="service-status glass-card">
    <div class="table-header">
      <h3 class="chart-title">系统服务</h3>
      <span class="service-count">{{ services.length }} 个服务</span>
    </div>
    <div class="service-list">
      <div
        v-for="service in services"
        :key="service.name"
        class="service-item"
      >
        <div class="service-info">
          <span class="service-name">{{ service.name || service.unit }}</span>
          <span class="service-desc" v-if="service.description">{{ service.description }}</span>
        </div>
        <span class="service-badge" :class="getStatusClass(service.status || service.active)">
          {{ getStatusLabel(service.status || service.active) }}
        </span>
      </div>
      <div v-if="services.length === 0" class="empty">暂无服务数据</div>
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
}

.service-count {
  font-size: 12px;
  color: var(--text-tertiary);
  font-weight: 500;
}

.service-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.service-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  border-radius: 10px;
  transition: background 0.15s ease;
}

.service-item:hover {
  background: rgba(0, 0, 0, 0.02);
}

.service-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.service-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
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
