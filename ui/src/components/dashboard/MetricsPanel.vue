<script setup lang="ts">
import { ref, onMounted } from 'vue'

interface TurnMetric {
  turn: number
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cost_usd: number
  elapsed_sec: number
}

interface Metrics {
  total_requests: number
  total_tokens: number
  total_cost_usd: number
  total_latency_sec: number
  avg_latency_sec: number
  tool_calls: number
  compressions: number
  turns: TurnMetric[]
}

const metrics = ref<Metrics | null>(null)
const loading = ref(false)
const error = ref('')

async function loadMetrics() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetch('/metrics')
    metrics.value = await res.json()
  } catch (e) {
    error.value = String(e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadMetrics()
  setInterval(loadMetrics, 10000)
})
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <span class="panel-icon">📊</span>
      <span class="panel-title">指标概览</span>
      <button class="refresh-btn" @click="loadMetrics" :disabled="loading">刷新</button>
    </div>
    <div class="panel-body" v-if="metrics">
      <div class="metrics-grid">
        <div class="metric-item">
          <span class="metric-label">Token 消耗</span>
          <span class="metric-value">{{ metrics.total_tokens.toLocaleString() }}</span>
        </div>
        <div class="metric-item">
          <span class="metric-label">费用</span>
          <span class="metric-value">${{ metrics.total_cost_usd.toFixed(4) }}</span>
        </div>
        <div class="metric-item">
          <span class="metric-label">耗时</span>
          <span class="metric-value">{{ metrics.total_latency_sec.toFixed(1) }}s</span>
        </div>
        <div class="metric-item">
          <span class="metric-label">LLM 调用</span>
          <span class="metric-value">{{ metrics.total_requests }}</span>
        </div>
        <div class="metric-item">
          <span class="metric-label">Tool 调用</span>
          <span class="metric-value">{{ metrics.tool_calls }}</span>
        </div>
        <div class="metric-item">
          <span class="metric-label">压缩次数</span>
          <span class="metric-value">{{ metrics.compressions }}</span>
        </div>
      </div>

      <div v-if="metrics.turns && metrics.turns.length > 0" class="turns-section">
        <div class="turns-header">Turn 详情</div>
        <div class="turns-list">
          <div v-for="turn in metrics.turns" :key="turn.turn" class="turn-item">
            <span class="turn-num">#{{ turn.turn }}</span>
            <span class="turn-tokens">{{ turn.total_tokens }}</span>
            <span class="turn-cost">${{ turn.cost_usd.toFixed(4) }}</span>
            <span class="turn-time">{{ turn.elapsed_sec.toFixed(1) }}s</span>
          </div>
        </div>
      </div>
    </div>
    <div v-else-if="error" class="panel-body error">
      {{ error }}
    </div>
    <div v-else class="panel-body loading">
      加载中...
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

.refresh-btn {
  background: #21262d;
  border: 1px solid #30363d;
  color: #8b949e;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  cursor: pointer;
}

.refresh-btn:hover:not(:disabled) {
  background: #30363d;
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.panel-body {
  padding: 8px;
}

.panel-body.error {
  color: #f85149;
}

.panel-body.loading {
  color: #8b949e;
  text-align: center;
  padding: 16px;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.metric-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 4px;
  background: #21262d;
  border-radius: 4px;
}

.metric-label {
  font-size: 10px;
  color: #8b949e;
  margin-bottom: 2px;
}

.metric-value {
  font-size: 13px;
  font-weight: 600;
  color: #e6edf3;
}

.turns-section {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #21262d;
}

.turns-header {
  font-size: 11px;
  color: #8b949e;
  margin-bottom: 4px;
}

.turns-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.turn-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  background: #21262d;
  border-radius: 4px;
  font-size: 11px;
}

.turn-num {
  color: #f0883e;
  font-weight: 600;
  min-width: 32px;
}

.turn-tokens {
  color: #8b949e;
  flex: 1;
}

.turn-cost {
  color: #3fb950;
}

.turn-time {
  color: #58a6ff;
}
</style>