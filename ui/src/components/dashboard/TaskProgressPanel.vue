<script setup lang="ts">
import { computed } from 'vue'
import { useDashboardStore } from '../../stores/dashboard'

const dashboard = useDashboardStore()

const tasks = computed(() => Array.from(dashboard.taskProgresses.values()))
</script>

<template>
  <div class="panel" v-if="tasks.length > 0">
    <div class="panel-header">
      <span class="panel-icon">📊</span>
      <span class="panel-title">任务进度</span>
      <span class="panel-count">{{ tasks.length }}</span>
    </div>
    <div class="panel-body">
      <div v-for="task in tasks" :key="task.execution_id" class="task-item">
        <div class="task-header">
          <span class="task-id">{{ task.execution_id.slice(0, 8) }}...</span>
          <span class="task-step">{{ task.current_step }}/{{ task.total_steps }}</span>
        </div>
        <div class="progress-bar">
          <div
            class="progress-fill"
            :style="{ width: (task.current_step / task.total_steps * 100) + '%' }"
          ></div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.panel {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 6px;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border-bottom: 1px solid #21262d;
  font-size: 12px;
  color: #8b949e;
}

.panel-icon { font-size: 14px; }
.panel-title { flex: 1; font-weight: 600; color: #e6edf3; }
.panel-count {
  background: #30363d; color: #8b949e;
  padding: 1px 6px; border-radius: 10px; font-size: 11px;
}

.panel-body { padding: 6px 8px; }

.task-item {
  padding: 4px 0;
}

.task-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
}

.task-id {
  font-size: 11px;
  color: #8b949e;
  font-family: monospace;
}

.task-step {
  font-size: 11px;
  color: #f0883e;
}

.progress-bar {
  height: 4px;
  background: #21262d;
  border-radius: 2px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: #f0883e;
  border-radius: 2px;
  transition: width 0.3s ease;
}
</style>
