<script setup lang="ts">
import { onMounted } from 'vue'
import { useAgentsStore } from '../stores/agents'
import { useWorkflowsStore } from '../stores/workflows'
import AgentModal from './AgentModal.vue'
import ExecutionModals from './ExecutionModals.vue'

const agents = useAgentsStore()
const workflows = useWorkflowsStore()

onMounted(() => {
  agents.loadAgents()
  agents.loadGraphs()
  workflows.loadWorkflows()
})
</script>

<template>
  <div class="agents-tab">
    <div class="agents-layout">
      <div class="agents-sidebar">
        <div class="sidebar-header">
          <h3>Agent 列表</h3>
          <button class="new-btn" @click="agents.openNew()">+ 新建</button>
        </div>
        <div v-if="agents.loading" class="loading-state">加载中...</div>
        <div v-else class="agent-list">
          <div v-for="agent in agents.list" :key="agent.id"
               class="agent-item"
               :class="{ builtin: agent.is_builtin }">
            <div class="agent-info">
              <h4>{{ agent.name }}</h4>
              <p>{{ agent.description || '无描述' }}</p>
              <span class="agent-model">{{ agent.llm_model }}</span>
            </div>
            <div class="agent-actions">
              <button v-if="!agent.is_builtin" @click="agents.openEdit(agent)">编辑</button>
              <button v-if="!agent.is_builtin" class="delete-btn" @click="agents.deleteAgent(agent.id)">删除</button>
              <span v-if="agent.is_builtin" class="builtin-tag">内置</span>
            </div>
          </div>
        </div>
      </div>

      <div class="agents-main">
        <div class="execution-panel">
          <h3>执行 Agent Graph</h3>
          <div class="form-group">
            <label>选择 Graph</label>
            <select v-model="agents.selectedGraphId">
              <option value="">-- 选择 Graph --</option>
              <option v-for="g in agents.graphs" :key="g.id" :value="g.id">{{ g.name }}</option>
            </select>
          </div>
          <div class="form-group">
            <label>输入任务</label>
            <textarea v-model="agents.executionInput" placeholder="描述需要执行的任务..." rows="3" />
          </div>
          <button class="dispatch-btn" @click="agents.generatePlan()" :disabled="agents.executionLoading || !agents.selectedGraphId || !agents.executionInput.trim()">
            {{ agents.executionLoading ? '生成中...' : '生成执行计划' }}
          </button>
        </div>

        <div v-if="agents.executionPlan" class="plan-preview">
          <h4>执行计划预览</h4>
          <div class="plan-summary">
            <span>预估调用: {{ agents.executionPlan.total_llm_calls }} 次</span>
            <span>预估费用: ${{ agents.executionPlan.estimated_cost_usd }}</span>
          </div>
          <div v-if="agents.executionPlan.optimization_suggestions?.length" class="suggestions">
            <h5>💡 优化建议</h5>
            <div v-for="(s, i) in agents.executionPlan.optimization_suggestions" :key="i"
                 class="suggestion-item" :class="s.impact">
              <span class="type">{{ s.type }}</span>
              <span>{{ s.description }}</span>
            </div>
          </div>
          <div class="steps-preview">
            <h5>执行步骤</h5>
            <div v-for="step in agents.executionPlan.steps" :key="step.step_id" class="step-preview">
              <span class="step-num">{{ step.step_id }}</span>
              <span class="step-name">{{ step.agent_name }}</span>
              <span class="step-badge" v-if="step.is_parallel">并行</span>
            </div>
          </div>
          <button class="dispatch-btn" @click="agents.runWithApproval()">批准执行</button>
        </div>

        <div v-if="agents.currentExecution" class="execution-result">
          <h4>执行状态</h4>
          <div class="result-header">
            <span class="status-badge" :class="agents.currentExecution.status">
              {{ agents.currentExecution.status === 'running' ? '运行中' : agents.currentExecution.status === 'completed' ? '已完成' : '失败' }}
            </span>
            <span class="result-stats">
              调用: {{ agents.currentExecution.total_llm_calls }} 次
              费用: ${{ agents.currentExecution.total_cost_usd?.toFixed(4) }}
            </span>
          </div>

          <div class="steps-result">
            <h5>步骤详情</h5>
            <div v-for="step in agents.currentExecution.steps" :key="step.step_id"
                 class="step-result" :class="step.status">
              <span class="step-num">{{ step.step_id }}</span>
              <span class="step-name">{{ step.agent_name }}</span>
              <span class="step-status">{{ step.status === 'completed' ? '✓' : step.status === 'failed' ? '✗' : '⏳' }}</span>
              <span class="step-calls" v-if="step.llm_calls">{{ step.llm_calls }} LLM</span>
            </div>
          </div>

          <div v-if="agents.currentExecution.output" class="output-preview">
            <h5>输出</h5>
            <pre>{{ agents.currentExecution.output }}</pre>
          </div>
        </div>

        <div v-if="agents.executionReport" class="execution-report">
          <h4>📊 执行报告</h4>

          <div class="report-summary">
            <div class="summary-item">
              <span class="label">总调用</span>
              <span class="value">{{ agents.executionReport.summary.total_llm_calls }}</span>
            </div>
            <div class="summary-item">
              <span class="label">总费用</span>
              <span class="value">${{ agents.executionReport.summary.total_cost_usd }}</span>
            </div>
            <div class="summary-item">
              <span class="label">总耗时</span>
              <span class="value">{{ agents.executionReport.summary.total_duration_ms }}ms</span>
            </div>
          </div>

          <div v-if="agents.executionReport.optimization_insights?.suggestions?.length" class="report-suggestions">
            <h5>💡 改进建议</h5>
            <div v-for="(s, i) in agents.executionReport.optimization_insights.suggestions" :key="i"
                 class="report-suggestion" :class="s.priority">
              <span class="priority">{{ s.priority }}</span>
              <span>{{ s.description }}</span>
              <span class="action">{{ s.action }}</span>
            </div>
          </div>

          <div class="report-steps">
            <h5>步骤统计</h5>
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Agent</th>
                  <th>状态</th>
                  <th>LLM</th>
                  <th>费用</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="s in agents.executionReport.step_details" :key="s.step_id">
                  <td>{{ s.step_id }}</td>
                  <td>{{ s.agent_name }}</td>
                  <td :class="s.status">{{ s.status }}</td>
                  <td>{{ s.llm_calls }}</td>
                  <td>${{ s.cost_usd }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <AgentModal />
    <ExecutionModals />
  </div>
</template>

<style scoped>
.agents-tab {
  height: calc(100vh - 50px);
}

.agents-layout {
  display: flex;
  height: 100%;
}

.agents-sidebar {
  width: 320px;
  background: #0d1117;
  border-right: 1px solid #30363d;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #30363d;
}

.sidebar-header h3 {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
}

.new-btn {
  background: #238636;
  color: #fff;
  border: none;
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
}

.loading-state {
  text-align: center;
  color: #8b949e;
  padding: 40px;
}

.agent-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.agent-item {
  background: #161b22;
  border: 1px solid #21262d;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 8px;
}

.agent-item.builtin {
  border-left: 3px solid #58a6ff;
}

.agent-info h4 {
  font-size: 14px;
  color: #e1e4e8;
  margin-bottom: 4px;
}

.agent-info p {
  font-size: 12px;
  color: #8b949e;
  margin-bottom: 6px;
}

.agent-model {
  font-size: 11px;
  color: #6e7681;
  background: #21262d;
  padding: 2px 6px;
  border-radius: 4px;
}

.agent-actions {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}

.agent-actions button {
  background: #21262d;
  border: 1px solid #30363d;
  color: #c9d1d9;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
}

.agent-actions .delete-btn {
  color: #f85149;
}

.builtin-tag {
  font-size: 11px;
  color: #58a6ff;
  background: #1a3a5c;
  padding: 2px 6px;
  border-radius: 4px;
}

.agents-main {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.execution-panel {
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 10px;
  padding: 20px;
}

.execution-panel h3 {
  font-size: 16px;
  color: #e1e4e8;
  margin-bottom: 16px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  font-size: 12px;
  color: #8b949e;
  margin-bottom: 6px;
}

.form-group input,
.form-group textarea,
.form-group select {
  width: 100%;
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 6px;
  padding: 8px 12px;
  color: #e1e4e8;
  font-size: 14px;
  font-family: inherit;
}

.dispatch-btn {
  background: #238636;
  color: #fff;
  border: none;
  padding: 12px 20px;
  border-radius: 8px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
}

.dispatch-btn:disabled {
  background: #21262d;
  color: #6e7681;
  cursor: not-allowed;
}

.plan-preview {
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 10px;
  padding: 20px;
}

.plan-preview h4 {
  font-size: 14px;
  color: #58a6ff;
  margin-bottom: 12px;
}

.plan-summary {
  display: flex;
  gap: 20px;
  margin-bottom: 16px;
}

.plan-summary span {
  background: #21262d;
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 13px;
}

.suggestions {
  background: #161b22;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 16px;
}

.suggestions h5 {
  font-size: 13px;
  color: #e1e4e8;
  margin-bottom: 8px;
}

.suggestion-item {
  padding: 6px 10px;
  margin-bottom: 6px;
  border-radius: 4px;
  font-size: 12px;
}

.suggestion-item.high {
  background: #1a4a2a;
  border-left: 3px solid #3fb950;
}

.suggestion-item.medium {
  background: #1a3a5c;
  border-left: 3px solid #58a6ff;
}

.suggestion-item .type {
  font-weight: 600;
  text-transform: uppercase;
  font-size: 10px;
  margin-right: 8px;
}

.steps-preview {
  background: #161b22;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 16px;
}

.steps-preview h5 {
  font-size: 13px;
  color: #e1e4e8;
  margin-bottom: 8px;
}

.step-preview {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  background: #0d1117;
  border-radius: 6px;
  margin-bottom: 6px;
}

.step-preview .step-num {
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

.step-preview .step-name {
  flex: 1;
  font-size: 13px;
  color: #c9d1d9;
}

.step-preview .step-badge {
  background: #1f6feb;
  color: #fff;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
}

.execution-result {
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 10px;
  padding: 20px;
}

.execution-result h4 {
  font-size: 14px;
  color: #58a6ff;
  margin-bottom: 12px;
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.status-badge {
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.status-badge.running { background: #1f6feb; color: #fff; }
.status-badge.completed { background: #238636; color: #fff; }
.status-badge.failed { background: #da3633; color: #fff; }

.result-stats {
  font-size: 13px;
  color: #8b949e;
}

.steps-result {
  margin-bottom: 12px;
}

.steps-result h5 {
  font-size: 12px;
  color: #8b949e;
  margin-bottom: 8px;
}

.step-result {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  background: #161b22;
  border-radius: 6px;
  margin-bottom: 6px;
}

.step-result .step-num {
  width: 24px;
  height: 24px;
  background: #30363d;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}

.step-result .step-name {
  flex: 1;
  font-size: 13px;
}

.step-result .step-status {
  font-size: 14px;
}

.step-result.completed .step-status { color: #3fb950; }
.step-result.failed .step-status { color: #f85149; }
.step-result.running .step-status { color: #58a6ff; }

.step-calls {
  font-size: 11px;
  color: #6e7681;
}

.output-preview {
  background: #161b22;
  border-radius: 6px;
  padding: 12px;
}

.output-preview h5 {
  font-size: 12px;
  color: #8b949e;
  margin-bottom: 8px;
}

.output-preview pre {
  font-size: 11px;
  color: #c9d1d9;
  white-space: pre-wrap;
  max-height: 200px;
  overflow-y: auto;
}

.execution-report {
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 10px;
  padding: 20px;
}

.execution-report h4 {
  font-size: 14px;
  color: #58a6ff;
  margin-bottom: 16px;
}

.report-summary {
  display: flex;
  gap: 20px;
  margin-bottom: 16px;
}

.report-summary .summary-item {
  background: #161b22;
  padding: 10px 16px;
  border-radius: 6px;
}

.report-summary .label {
  font-size: 11px;
  color: #8b949e;
  display: block;
}

.report-summary .value {
  font-size: 16px;
  font-weight: 600;
  color: #e1e4e8;
}

.report-suggestions {
  background: #161b22;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 16px;
}

.report-suggestions h5 {
  font-size: 12px;
  color: #e1e4e8;
  margin-bottom: 8px;
}

.report-suggestion {
  padding: 8px 12px;
  margin-bottom: 6px;
  border-radius: 4px;
  font-size: 12px;
}

.report-suggestion.high {
  background: #1a4a2a;
  border-left: 3px solid #3fb950;
}

.report-suggestion.medium {
  background: #1a3a5c;
  border-left: 3px solid #58a6ff;
}

.report-suggestion .priority {
  font-weight: 600;
  text-transform: uppercase;
  font-size: 10px;
  margin-right: 8px;
}

.report-suggestion .action {
  display: block;
  color: #8b949e;
  font-size: 11px;
  margin-top: 4px;
}

.report-steps {
  background: #161b22;
  border-radius: 8px;
  padding: 12px;
}

.report-steps h5 {
  font-size: 12px;
  color: #e1e4e8;
  margin-bottom: 8px;
}

.report-steps table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.report-steps th {
  text-align: left;
  color: #8b949e;
  padding: 8px;
  border-bottom: 1px solid #30363d;
}

.report-steps td {
  padding: 8px;
  border-bottom: 1px solid #21262d;
}

.report-steps .completed { color: #3fb950; }
.report-steps .failed { color: #f85149; }
</style>
