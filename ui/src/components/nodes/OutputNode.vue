<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'

defineProps<{
  data: {
    label?: string
    outputFormat?: string
  }
}>()
</script>

<template>
  <div class="output-node">
    <Handle type="target" :position="Position.Left" />
    <div class="node-header">
      <span class="node-icon">📤</span>
      <span class="node-label">{{ data?.label || '输出' }}</span>
    </div>
    <div class="node-type">{{ data?.outputFormat || 'text' }}</div>
    <Handle type="source" :position="Position.Right" />
  </div>
</template>

<style scoped>
.output-node {
  padding: 10px 14px;
  border-radius: 8px;
  border: 2px solid #db61a2;
  background: #1c1420;
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

.node-type {
  font-size: 10px;
  color: #8b949e;
  padding: 2px 6px;
  background: #21262d;
  border-radius: 4px;
  display: inline-block;
  margin-top: 4px;
}
</style>
