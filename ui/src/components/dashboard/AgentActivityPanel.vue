<script setup lang="ts">
import { computed } from 'vue'
import { useDashboardStore } from '../../stores/dashboard'
import { formatTime } from '../../utils/format'

const dashboard = useDashboardStore()

const agentList = computed(() => {
  return Array.from(dashboard.agentActivities.values()).slice(0, 10)
})

const statusColor: Record<string, string> = {
  idle: '#8b949e',
  running: '#f0883e',
  completed: '#3fb950',
  failed: '#f85149',
}

const statusLabel: Record<string, string> = {
  idle: '空闲',
  running: '运行中',
  completed: '完成',
  failed: '失败',
}
</script>

<template>
  <div class="panel" v-if="agentList.length > 0">
    <div class="panel-header">
      <span class="panel-icon">🤖</span>
      <span class="panel-title">Agent 活动</span>
      <span class="panel-count">{{ agentList.length }}</span>
    </div>
    <div class="panel-body">
      <div v-for="agent in agentList" :key="agent.agent_id" class="agent-item">
        <div class="agent-status-dot" :style="{ background: statusColor[agent.status] }"></div>
        <div class="agent-info">
          <div class="agent-name">{{ agent.agent_name }}</div>
          <div class="agent-meta">
            <span :class="['status-badge', agent.status]">{{ statusLabel[agent.status] }}</span>
            <span v-if="agent.finished_at" class="agent-time">{{ formatTime(agent.finished_at) }}</span>
          </div>
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

.panel-icon {
  font-size: 14px;
}

.panel-title {
  flex: 1;
  font-weight: 600;
  color: #e6edf3;
}

.panel-count {
  background: #30363d;
  color: #8b949e;
  padding: 1px 6px;
  border-radius: 10px;
  font-size: 11px;
}

.panel-body {
  padding: 4px;
}

.agent-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 4px;
}

.agent-item:hover {
  background: #1c2129;
}

.agent-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.agent-info {
  flex: 1;
  min-width: 0;
}

.agent-name {
  font-size: 12px;
  color: #e6edf3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.agent-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 2px;
}

.status-badge {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
}

.status-badge.running {
  background: #f0883e22;
  color: #f0883e;
  animation: pulse 2s infinite;
}

.status-badge.completed {
  background: #3fb95022;
  color: #3fb950;
}

.status-badge.failed {
  background: #f8514922;
  color: #f85149;
}

.status-badge.idle {
  background: #8b949e22;
  color: #8b949e;
}

.agent-time {
  font-size: 10px;
  color: #484f58;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>
