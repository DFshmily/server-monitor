<script setup>
defineProps({
  processes: {
    type: Array,
    default: () => []
  },
  sortBy: {
    type: String,
    default: 'cpu'
  }
})
</script>

<template>
  <div class="process-table glass-card">
    <div class="table-header">
      <h3 class="chart-title">Top 进程</h3>
      <span class="sort-label">按 {{ sortBy === 'cpu' ? 'CPU' : '内存' }} 排序</span>
    </div>
    <div class="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>进程名</th>
            <th>PID</th>
            <th>CPU%</th>
            <th>内存%</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(proc, index) in processes" :key="proc.pid || index">
            <td class="rank">{{ index + 1 }}</td>
            <td class="process-name">{{ proc.name || proc.command }}</td>
            <td class="pid">{{ proc.pid }}</td>
            <td>
              <span class="cpu-value" :class="{ high: (proc.cpu_percent || proc.cpu) > 50 }">
                {{ (proc.cpu_percent || proc.cpu || 0).toFixed(1) }}%
              </span>
            </td>
            <td>
              <span class="mem-value" :class="{ high: (proc.mem_percent || proc.memory) > 50 }">
                {{ (proc.mem_percent || proc.memory || 0).toFixed(1) }}%
              </span>
            </td>
            <td>
              <span class="status-dot" :class="proc.status || 'running'"></span>
              {{ proc.status || '运行中' }}
            </td>
          </tr>
          <tr v-if="processes.length === 0">
            <td colspan="6" class="empty">暂无数据</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.process-table {
  padding: 20px;
  overflow: hidden;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.sort-label {
  font-size: 12px;
  color: var(--text-tertiary);
  font-weight: 500;
}

.table-wrapper {
  overflow-x: auto;
}

.rank {
  color: var(--text-tertiary);
  font-weight: 600;
  font-size: 12px;
}

.process-name {
  font-weight: 600;
  color: var(--text-primary);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pid {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 12px;
  color: var(--text-secondary);
}

.cpu-value, .mem-value {
  font-weight: 600;
  font-size: 13px;
}

.cpu-value.high, .mem-value.high {
  color: var(--status-red);
}

.status-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-right: 6px;
  background: var(--status-green);
}

.status-dot.stopped, .status-dot.dead {
  background: var(--status-red);
}

.status-dot.sleeping {
  background: var(--status-orange);
}

.empty {
  text-align: center;
  color: var(--text-tertiary);
  padding: 24px !important;
}
</style>
