<script setup lang="ts">
import { computed } from 'vue'
import type { ToolInvocation } from '../types'

const props = defineProps<{
  invocation: ToolInvocation
}>()

const emit = defineEmits<{
  (e: 'retry'): void
}>()

const statusIcon = computed(() => {
  switch (props.invocation.status) {
    case 'pending': return '⏳'
    case 'running': return '🔄'
    case 'success': return '✓'
    case 'error': return '✗'
    default: return '?'
  }
})

const toolIcon = computed(() => {
  const name = props.invocation.name.toLowerCase()
  if (name.includes('code') || name.includes('execute')) return '💻'
  if (name.includes('file') || name.includes('read') || name.includes('write')) return '📁'
  if (name.includes('search') || name.includes('grep')) return '🔍'
  if (name.includes('cli') || name.includes('dispatch')) return '🚀'
  if (name.includes('data')) return '📊'
  return '⚙️'
})

const formattedDuration = computed(() => {
  if (!props.invocation.duration) return ''
  if (props.invocation.duration < 1000) return `${props.invocation.duration}ms`
  return `${(props.invocation.duration / 1000).toFixed(2)}s`
})

const hasArgs = computed(() => {
  return props.invocation.arguments && Object.keys(props.invocation.arguments).length > 0
})

const argsString = computed(() => {
  try {
    return JSON.stringify(props.invocation.arguments, null, 2)
  } catch {
    return String(props.invocation.arguments)
  }
})
</script>

<template>
  <div :class="['tool-card', `status-${invocation.status}`]">
    <div class="tool-header">
      <span class="tool-icon">{{ toolIcon }}</span>
      <span class="tool-name">{{ invocation.name }}</span>
      <span class="tool-status" :class="invocation.status">
        {{ statusIcon }} {{ invocation.status }}
      </span>
      <span v-if="formattedDuration" class="tool-duration">{{ formattedDuration }}</span>
    </div>

    <div v-if="hasArgs" class="tool-args">
      <div class="section-header">
        <span>参数</span>
      </div>
      <pre class="code-block">{{ argsString }}</pre>
    </div>

    <div v-if="invocation.result || invocation.error" class="tool-result">
      <div class="section-header">
        <span>{{ invocation.error ? '错误' : '结果' }}</span>
      </div>
      <pre :class="['code-block', { 'error': invocation.error }]">{{ invocation.error || invocation.result }}</pre>
    </div>

    <div v-if="invocation.status === 'error'" class="tool-actions">
      <button class="retry-btn" @click="emit('retry')">
        🔄 重试
      </button>
    </div>
  </div>
</template>

<style scoped>
.tool-card {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 8px;
  border-left: 3px solid #6e7681;
}

.tool-card.status-pending {
  border-left-color: #6e7681;
}

.tool-card.status-running {
  border-left-color: #58a6ff;
}

.tool-card.status-success {
  border-left-color: #3fb950;
}

.tool-card.status-error {
  border-left-color: #f85149;
}

.tool-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.tool-icon {
  font-size: 14px;
}

.tool-name {
  font-weight: 600;
  color: #c9d1d9;
  font-size: 13px;
}

.tool-status {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
  font-weight: 600;
}

.tool-status.pending {
  background: #21262d;
  color: #6e7681;
}

.tool-status.running {
  background: #1a3a5c;
  color: #58a6ff;
}

.tool-status.success {
  background: #1a4a2a;
  color: #3fb950;
}

.tool-status.error {
  background: #4a1a1a;
  color: #f85149;
}

.tool-duration {
  font-size: 11px;
  color: #8b949e;
  margin-left: auto;
}

.section-header {
  font-size: 11px;
  color: #8b949e;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-top: 10px;
  margin-bottom: 6px;
}

.tool-args,
.tool-result {
  margin-top: 8px;
}

.code-block {
  background: #0d1117;
  border: 1px solid #21262d;
  border-radius: 4px;
  padding: 8px;
  font-size: 11px;
  color: #c9d1d9;
  font-family: 'SF Mono', monospace;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow-y: auto;
  margin: 0;
}

.code-block.error {
  color: #f85149;
  border-color: #4a1a1a;
}

.tool-actions {
  margin-top: 10px;
  display: flex;
  justify-content: flex-end;
}

.retry-btn {
  background: #21262d;
  border: 1px solid #30363d;
  border-radius: 4px;
  padding: 4px 12px;
  font-size: 12px;
  color: #8b949e;
  cursor: pointer;
  transition: all 0.2s;
}

.retry-btn:hover {
  background: #30363d;
  color: #c9d1d9;
}
</style>