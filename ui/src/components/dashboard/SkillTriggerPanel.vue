<script setup lang="ts">
import { computed } from 'vue'
import { useDashboardStore } from '../../stores/dashboard'
import { formatTime } from '../../utils/format'

const dashboard = useDashboardStore()

const triggers = computed(() => dashboard.skillTriggers.slice(0, 15))
</script>

<template>
  <div class="panel" v-if="triggers.length > 0">
    <div class="panel-header">
      <span class="panel-icon">🔧</span>
      <span class="panel-title">技能触发</span>
      <span class="panel-count">{{ triggers.length }}</span>
    </div>
    <div class="panel-body">
      <div v-for="(trigger, i) in triggers" :key="i" class="trigger-item">
        <span class="trigger-name">{{ trigger.skill_name }}</span>
        <span class="trigger-time">{{ formatTime(trigger.triggered_at) }}</span>
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

.panel-body { padding: 4px; }

.trigger-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 5px 8px;
  border-radius: 4px;
}

.trigger-item:hover { background: #1c2129; }

.trigger-name {
  font-size: 12px;
  color: #e6edf3;
  font-family: monospace;
}

.trigger-time {
  font-size: 10px;
  color: #484f58;
}
</style>
