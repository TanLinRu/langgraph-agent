<script setup lang="ts">
import { ref, computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'

const props = defineProps<{
  data: {
    step_id: string
    agent_name: string
    description: string
    status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
    result?: string
    error?: string
    duration_ms?: number
  }
}>()

const emit = defineEmits<{
  (e: 'rollback', stepId: string): void
  (e: 'select', stepId: string): void
}>()

const expanded = ref(false)

const statusIcon = computed(() => {
  const map: Record<string, string> = {
    pending: '⏳',
    running: '🔄',
    completed: '✅',
    failed: '❌',
    skipped: '⏭️',
  }
  return map[props.data?.status] || '⏳'
})

const statusClass = computed(() => props.data?.status || 'pending')

const durationLabel = computed(() => {
  const ms = props.data?.duration_ms
  if (!ms) return ''
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
})

const resultPreview = computed(() => {
  const r = props.data?.result
  if (!r) return ''
  return r.length > 80 ? r.substring(0, 80) + '...' : r
})

function handleClick() {
  emit('select', props.data?.step_id)
  expanded.value = !expanded.value
}

function handleRollback(e: Event) {
  e.stopPropagation()
  emit('rollback', props.data?.step_id)
}
</script>

<template>
  <div :class="['orchestrator-node', statusClass]" @click="handleClick">
    <Handle type="target" :position="Position.Left" />

    <div class="node-header">
      <span class="status-icon" :class="{ spinning: data?.status === 'running' }">
        {{ statusIcon }}
      </span>
      <span class="agent-name">{{ data?.agent_name || 'Step' }}</span>
      <span v-if="durationLabel" class="duration">{{ durationLabel }}</span>
    </div>

    <div class="node-desc">{{ data?.description || '' }}</div>

    <div v-if="expanded && (data?.result || data?.error)" class="node-detail">
      <div v-if="data?.result" class="result-text">{{ resultPreview }}</div>
      <div v-if="data?.error" class="error-text">{{ data.error.substring(0, 100) }}</div>
    </div>

    <div
      v-if="data?.status === 'completed' || data?.status === 'failed'"
      class="node-actions"
    >
      <button class="reexecute-btn" @click="handleRollback" title="Re-execute from here">
        🔁
      </button>
    </div>

    <Handle type="source" :position="Position.Right" />
  </div>
</template>

<style scoped>
.orchestrator-node {
  padding: 10px 14px;
  border-radius: 8px;
  border: 2px solid #30363d;
  background: #161b22;
  min-width: 160px;
  max-width: 240px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.orchestrator-node:hover {
  box-shadow: 0 0 8px rgba(88, 166, 255, 0.3);
}

.orchestrator-node.pending { border-color: #6e7681; }
.orchestrator-node.running { border-color: #58a6ff; box-shadow: 0 0 10px rgba(88, 166, 255, 0.4); }
.orchestrator-node.completed { border-color: #3fb950; }
.orchestrator-node.failed { border-color: #f85149; }
.orchestrator-node.skipped { border-color: #6e7681; opacity: 0.6; }

.node-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.status-icon {
  font-size: 13px;
  flex-shrink: 0;
}

.status-icon.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.agent-name {
  font-size: 12px;
  font-weight: 600;
  color: #e1e4e8;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.duration {
  font-size: 10px;
  color: #8b949e;
  flex-shrink: 0;
}

.node-desc {
  font-size: 10px;
  color: #8b949e;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-detail {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid #30363d;
}

.result-text {
  font-size: 10px;
  color: #8b949e;
  line-height: 1.4;
  word-break: break-word;
}

.error-text {
  font-size: 10px;
  color: #f85149;
  line-height: 1.4;
  word-break: break-word;
}

.node-actions {
  margin-top: 6px;
  display: flex;
  justify-content: flex-end;
}

.reexecute-btn {
  background: none;
  border: 1px solid #30363d;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  padding: 2px 6px;
  color: #8b949e;
  transition: all 0.2s;
}

.reexecute-btn:hover {
  background: #30363d;
  color: #e1e4e8;
}
</style>
