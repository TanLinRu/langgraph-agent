<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'

defineProps<{
  data: {
    label?: string
    condition?: string
  }
}>()
</script>

<template>
  <div class="condition-node">
    <Handle type="target" :position="Position.Left" />
    <div class="node-header">
      <span class="node-icon">🔀</span>
      <span class="node-label">{{ data?.label || '条件分支' }}</span>
    </div>
    <div v-if="data?.condition" class="node-condition">{{ data.condition.substring(0, 30) }}</div>
    <Handle type="source" :position="Position.Right" id="true" />
    <Handle type="source" :position="Position.Bottom" id="false" />
  </div>
</template>

<style scoped>
.condition-node {
  padding: 10px 14px;
  border-radius: 8px;
  border: 2px solid #f0883e;
  background: #1c1a14;
  min-width: 120px;
}

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

.node-condition {
  font-size: 10px;
  color: #8b949e;
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
