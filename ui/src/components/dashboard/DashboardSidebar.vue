<script setup lang="ts">
import { useDashboardStore } from '../../stores/dashboard'
import AgentActivityPanel from './AgentActivityPanel.vue'
import SkillTriggerPanel from './SkillTriggerPanel.vue'
import TaskProgressPanel from './TaskProgressPanel.vue'
import ObservationFeed from './ObservationFeed.vue'

const dashboard = useDashboardStore()
</script>

<template>
  <div :class="['dashboard-sidebar', { open: dashboard.isOpen }]">
    <div class="dashboard-toggle" @click="dashboard.toggle" :title="dashboard.isOpen ? '收起面板' : '展开面板'">
      <span class="toggle-icon">{{ dashboard.isOpen ? '▶' : '◀' }}</span>
      <span v-if="!dashboard.isOpen" class="toggle-label">面板</span>
      <span v-if="dashboard.isOpen" class="connection-dot" :class="{ connected: dashboard.connected }"></span>
    </div>

    <div v-if="dashboard.isOpen" class="dashboard-content">
      <div class="dashboard-header">
        <h3>实时观察</h3>
        <span class="connection-status" :class="{ connected: dashboard.connected }">
          {{ dashboard.connected ? '已连接' : '未连接' }}
        </span>
      </div>

      <div class="dashboard-panels">
        <AgentActivityPanel />
        <SkillTriggerPanel />
        <TaskProgressPanel />
        <ObservationFeed />
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboard-sidebar {
  display: flex;
  flex-shrink: 0;
  width: 36px;
  overflow: hidden;
  transition: width 0.3s ease;
  background: #0d1117;
  border-left: 1px solid #30363d;
}

.dashboard-sidebar.open {
  width: 360px;
}

.dashboard-toggle {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  padding: 12px 6px;
  cursor: pointer;
  background: #161b22;
  border-right: 1px solid #30363d;
  min-width: 36px;
  gap: 8px;
  user-select: none;
}

.dashboard-toggle:hover {
  background: #1c2129;
}

.toggle-icon {
  font-size: 10px;
  color: #8b949e;
}

.toggle-label {
  writing-mode: vertical-rl;
  font-size: 11px;
  color: #8b949e;
  letter-spacing: 2px;
}

.connection-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #f85149;
}

.connection-dot.connected {
  background: #3fb950;
}

.dashboard-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.dashboard-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid #30363d;
}

.dashboard-header h3 {
  margin: 0;
  font-size: 14px;
  color: #e6edf3;
}

.connection-status {
  font-size: 11px;
  color: #f85149;
}

.connection-status.connected {
  color: #3fb950;
}

.dashboard-panels {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.dashboard-panels::-webkit-scrollbar {
  width: 6px;
}

.dashboard-panels::-webkit-scrollbar-thumb {
  background: #30363d;
  border-radius: 3px;
}
</style>
