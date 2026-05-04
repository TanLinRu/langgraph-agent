<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'

defineProps<{
  data: {
    label?: string
    description?: string
    isBuiltin?: boolean
  }
}>()
</script>

<template>
  <div :class="['agent-node', data?.isBuiltin ? 'builtin' : 'custom']">
    <Handle type="target" :position="Position.Left" />
    <div class="node-header">
      <span class="node-icon">{{ data?.isBuiltin ? '🤖' : '🔧' }}</span>
      <span class="node-label">{{ data?.label || 'Agent' }}</span>
    </div>
    <div v-if="data?.description" class="node-desc">{{ data.description.substring(0, 40) }}...</div>
    <Handle type="source" :position="Position.Right" />
  </div>
</template>

<style scoped>
.agent-node {
  padding: 10px 14px;
  border-radius: 8px;
  border: 2px solid #30363d;
  background: #161b22;
  min-width: 120px;
}

.agent-node.builtin { border-color: #1f6feb; }
.agent-node.custom { border-color: #238636; }

.node-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.node-icon { font-size: 14px; }

.node-label {
  font-size: 12px;
  font-weight: 600;
  color: #e1e4e8;
}

.node-desc {
  font-size: 10px;
  color: #8b949e;
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
