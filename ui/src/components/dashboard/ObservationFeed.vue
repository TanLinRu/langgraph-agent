<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDashboardStore } from '../../stores/dashboard'
import { formatTime } from '../../utils/format'

const dashboard = useDashboardStore()

const observations = computed(() => dashboard.observations.slice(0, 50))

const eventTypeConfig: Record<string, { icon: string; label: string; color: string }> = {
  agent_status: { icon: '🤖', label: 'Agent', color: '#58a6ff' },
  skill_trigger: { icon: '🔧', label: '技能', color: '#f0883e' },
  task_progress: { icon: '📊', label: '进度', color: '#3fb950' },
  step_complete: { icon: '✅', label: '完成', color: '#3fb950' },
}

function getConfig(type: string) {
  return eventTypeConfig[type] || { icon: '📌', label: type, color: '#8b949e' }
}

function getDataSummary(data: Record<string, unknown>): string {
  if (data.agent_name) return String(data.agent_name)
  if (data.tool_name) return String(data.tool_name)
  if (data.execution_id) return `执行 ${String(data.execution_id).slice(0, 6)}...`
  return JSON.stringify(data).slice(0, 60)
}
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <span class="panel-icon">📋</span>
      <span class="panel-title">观察日志</span>
      <span class="panel-count">{{ dashboard.observations.length }}</span>
    </div>
    <div class="panel-body">
      <div v-if="observations.length === 0" class="empty-hint">
        暂无事件，等待 Agent 活动...
      </div>
      <div v-for="obs in observations" :key="obs.id" class="obs-item">
        <span class="obs-icon">{{ getConfig(obs.event_type).icon }}</span>
        <span class="obs-type" :style="{ color: getConfig(obs.event_type).color }">
          {{ getConfig(obs.event_type).label }}
        </span>
        <span class="obs-data">{{ getDataSummary(obs.data) }}</span>
        <span class="obs-time">{{ formatTime(obs.timestamp) }}</span>
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
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
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

.panel-body {
  padding: 4px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}

.empty-hint {
  padding: 20px;
  text-align: center;
  color: #484f58;
  font-size: 12px;
}

.obs-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 11px;
}

.obs-item:hover {
  background: #1c2129;
}

.obs-icon {
  font-size: 12px;
  flex-shrink: 0;
}

.obs-type {
  font-weight: 600;
  flex-shrink: 0;
  min-width: 30px;
}

.obs-data {
  color: #8b949e;
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.obs-time {
  color: #484f58;
  flex-shrink: 0;
  font-size: 10px;
}
</style>
