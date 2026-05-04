<script setup lang="ts">
import { useAgentsStore } from '../stores/agents'

const agents = useAgentsStore()
</script>

<template>
  <!-- Execution Plan Preview Modal -->
  <transition name="fade">
    <div v-if="agents.showPlanApproval && agents.executionPlan" class="modal-overlay" @click.self="agents.showPlanApproval = false">
      <div class="modal modal-wide">
        <div class="modal-header">
          <h3>📋 执行计划预览</h3>
          <button class="close-btn" @click="agents.showPlanApproval = false">×</button>
        </div>
        <div class="modal-body">
          <div class="plan-summary">
            <h4>执行步骤 ({{ agents.executionPlan.steps?.length || 0 }} 步)</h4>
            <div class="plan-steps">
              <div v-for="(step, idx) in agents.executionPlan.steps" :key="idx" class="plan-step">
                <span class="step-num">{{ idx + 1 }}</span>
                <span class="step-agent">{{ step.agent }}</span>
                <span class="step-action">{{ step.action }}</span>
                <span v-if="step.parallel" class="step-parallel">⚡ 并行</span>
              </div>
            </div>
          </div>
          <div v-if="agents.executionPlan.optimization_suggestions?.length" class="plan-optimizations">
            <h4>💡 优化建议</h4>
            <div v-for="(opt, idx) in agents.executionPlan.optimization_suggestions" :key="idx" class="optimization-item">
              <div class="opt-type">{{ opt.type }}</div>
              <div class="opt-message">{{ opt.message }}</div>
              <div v-if="opt.savings" class="opt-savings">预计节省: {{ opt.savings }}</div>
            </div>
          </div>
          <div v-if="agents.executionPlan.estimated_cost" class="plan-cost">
            <h4>💰 预估成本</h4>
            <div class="cost-detail">
              <span>输入: {{ agents.executionPlan.estimated_cost.input_tokens }} tokens</span>
              <span>输出: {{ agents.executionPlan.estimated_cost.output_tokens }} tokens</span>
              <span>预估: ${{ agents.executionPlan.estimated_cost.estimated_cost }}</span>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="agents.showPlanApproval = false">取消</button>
          <button class="btn-primary" @click="agents.approveExecution()">确认执行</button>
        </div>
      </div>
    </div>
  </transition>

  <!-- Execution Detail Modal -->
  <transition name="fade">
    <div v-if="agents.showExecutionDetail && agents.currentExecution" class="modal-overlay" @click.self="agents.showExecutionDetail = false">
      <div class="modal modal-wide">
        <div class="modal-header">
          <h3>🚀 执行状态: {{ agents.currentExecution.status }}</h3>
          <button class="close-btn" @click="agents.showExecutionDetail = false">×</button>
        </div>
        <div class="modal-body">
          <div class="execution-status">
            <div v-if="agents.currentExecution.status === 'running'" class="status-running">
              <div class="spinner"></div>
              <span>执行中...</span>
            </div>
            <div v-if="agents.currentExecution.status === 'completed'" class="status-completed">✅ 完成</div>
            <div v-if="agents.currentExecution.status === 'failed'" class="status-failed">❌ 失败</div>
          </div>
          <div v-if="agents.currentExecution.results" class="execution-results">
            <h4>执行结果</h4>
            <div v-for="(result, idx) in agents.currentExecution.results" :key="idx" class="result-item">
              <div class="result-agent">{{ result.agent }}</div>
              <div class="result-output">{{ result.output?.substring(0, 200) }}...</div>
              <div v-if="result.error" class="result-error">{{ result.error }}</div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="agents.showExecutionDetail = false">关闭</button>
        </div>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.modal {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 12px;
  width: 400px;
  max-width: 90%;
}

.modal-wide {
  width: 600px;
  max-height: 80vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #30363d;
}

.modal-body {
  padding: 20px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 16px 20px;
  border-top: 1px solid #30363d;
}

.close-btn {
  background: none;
  border: none;
  color: #8b949e;
  font-size: 24px;
  cursor: pointer;
  line-height: 1;
}

.btn-secondary {
  background: #21262d;
  border: 1px solid #30363d;
  color: #c9d1d9;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
}

.btn-primary {
  background: #238636;
  border: none;
  color: #fff;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
}

.plan-summary h4 {
  font-size: 14px;
  color: #58a6ff;
  margin-bottom: 12px;
}

.plan-steps {
  margin-bottom: 16px;
}

.plan-step {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  background: #0d1117;
  border-radius: 6px;
  margin-bottom: 6px;
}

.step-num {
  background: #30363d;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
}

.step-agent {
  font-size: 13px;
  color: #c9d1d9;
  flex: 1;
}

.step-action {
  font-size: 12px;
  color: #8b949e;
}

.step-parallel {
  font-size: 10px;
  background: #1f6feb;
  color: #fff;
  padding: 2px 6px;
  border-radius: 4px;
}

.plan-optimizations {
  margin-bottom: 16px;
}

.plan-optimizations h4 {
  font-size: 14px;
  color: #e1e4e8;
  margin-bottom: 8px;
}

.optimization-item {
  background: #0d1117;
  padding: 10px;
  border-radius: 6px;
  margin-bottom: 6px;
}

.opt-type {
  font-size: 11px;
  font-weight: 600;
  color: #58a6ff;
  text-transform: uppercase;
  margin-bottom: 4px;
}

.opt-message {
  font-size: 13px;
  color: #c9d1d9;
}

.opt-savings {
  font-size: 12px;
  color: #3fb950;
  margin-top: 4px;
}

.plan-cost h4 {
  font-size: 14px;
  color: #e1e4e8;
  margin-bottom: 8px;
}

.cost-detail {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: #8b949e;
}

.execution-status {
  text-align: center;
  margin-bottom: 20px;
}

.status-running {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #f0883e;
}

.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid #30363d;
  border-top-color: #f0883e;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.status-completed {
  color: #3fb950;
  font-size: 16px;
}

.status-failed {
  color: #f85149;
  font-size: 16px;
}

.execution-results h4 {
  font-size: 14px;
  color: #e1e4e8;
  margin-bottom: 12px;
}

.result-item {
  background: #0d1117;
  border: 1px solid #21262d;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 8px;
}

.result-agent {
  font-size: 13px;
  font-weight: 600;
  color: #58a6ff;
  margin-bottom: 4px;
}

.result-output {
  font-size: 12px;
  color: #8b949e;
}

.result-error {
  font-size: 12px;
  color: #f85149;
  margin-top: 4px;
}

.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
