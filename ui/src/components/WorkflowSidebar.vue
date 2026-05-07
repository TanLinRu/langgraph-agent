<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { useOrchestratorStore } from '../stores/orchestrator'
import { nodeTypes } from './nodes'
import type { OrchestratorStep } from '../types'

const orchestrator = useOrchestratorStore()
const { fitView } = useVueFlow({ id: 'orchestrator-flow' })

const statusColors: Record<string, string> = {
  planning: '#58a6ff',
  running: '#58a6ff',
  completed: '#3fb950',
  failed: '#f85149',
  rolled_back: '#d29922',
}

// Auto-fit view when nodes change
watch(
  () => orchestrator.flowNodes.length,
  async () => {
    await nextTick()
    setTimeout(() => fitView({ padding: 0.2 }), 100)
  }
)

function handleNodeClick(stepId: string) {
  orchestrator.selectStep(stepId)
}

function handleRollback(stepId: string) {
  if (!orchestrator.currentState) return
  orchestrator.rollback(orchestrator.currentState.orchestration_id, stepId)
}

function handleApproveReplan() {
  if (!orchestrator.currentState) return
  orchestrator.approveReplan(orchestrator.currentState.orchestration_id, true)
}

function handleRejectReplan() {
  if (!orchestrator.currentState) return
  orchestrator.approveReplan(orchestrator.currentState.orchestration_id, false)
  orchestrator.replanProposal = null
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}
</script>

<template>
  <div :class="['workflow-sidebar', { open: orchestrator.isOpen }]">
    <div
      class="sidebar-toggle"
      @click="orchestrator.toggleSidebar"
      :title="orchestrator.isOpen ? '收起工作流' : '展开工作流'"
    >
      <span class="toggle-icon">{{ orchestrator.isOpen ? '▶' : '◀' }}</span>
      <span v-if="!orchestrator.isOpen" class="toggle-label">工作流</span>
      <span
        v-if="orchestrator.currentState"
        class="status-dot"
        :style="{ background: statusColors[orchestrator.currentState.status] || '#6e7681' }"
      ></span>
    </div>

    <div v-if="orchestrator.isOpen" class="sidebar-content">
      <!-- Header -->
      <div class="sidebar-header">
        <h3>工作流</h3>
        <span
          v-if="orchestrator.currentState"
          class="status-badge"
          :style="{ color: statusColors[orchestrator.currentState.status] || '#8b949e' }"
        >
          {{ orchestrator.statusLabel }}
        </span>
      </div>

      <!-- Replan notification -->
      <div v-if="orchestrator.replanProposal" class="replan-banner">
        <div class="replan-reason">{{ orchestrator.replanProposal.reason }}</div>
        <div class="replan-actions">
          <button class="btn-approve" @click="handleApproveReplan">批准</button>
          <button class="btn-reject" @click="handleRejectReplan">拒绝</button>
        </div>
      </div>

      <!-- Plan summary -->
      <div v-if="orchestrator.currentState?.plan_summary" class="plan-summary">
        {{ orchestrator.currentState.plan_summary }}
      </div>

      <!-- Graph area -->
      <div class="graph-area">
        <VueFlow
          v-if="orchestrator.flowNodes.length"
          id="orchestrator-flow"
          :nodes="orchestrator.flowNodes"
          :edges="orchestrator.flowEdges"
          :node-types="nodeTypes"
          :default-edge-options="{ type: 'smoothstep' }"
          :nodes-draggable="true"
          :nodes-connectable="false"
          :edges-updatable="false"
          fit-view-on-init
        >
          <Background />
          <Controls />
          <template #node-orchestrator="nodeProps">
            <nodeTypes.orchestrator
              v-bind="nodeProps"
              @select="handleNodeClick"
              @rollback="handleRollback"
            />
          </template>
        </VueFlow>
        <div v-else class="empty-graph">
          <span>发送任务后，工作流将在此展示</span>
        </div>
      </div>

      <!-- Step detail panel -->
      <div v-if="orchestrator.selectedStep" class="step-detail">
        <div class="detail-header">
          <span class="detail-agent">{{ orchestrator.selectedStep.agent_name }}</span>
          <span class="detail-status" :class="orchestrator.selectedStep.status">
            {{ orchestrator.selectedStep.status }}
          </span>
          <button class="detail-close" @click="orchestrator.selectStep(null)">×</button>
        </div>
        <div class="detail-desc">{{ orchestrator.selectedStep.description }}</div>
        <div v-if="orchestrator.selectedStep.duration_ms" class="detail-meta">
          耗时: {{ formatDuration(orchestrator.selectedStep.duration_ms) }}
        </div>
        <div v-if="orchestrator.selectedStep.result" class="detail-section">
          <div class="section-label">执行结果</div>
          <div class="result-content">{{ orchestrator.selectedStep.result }}</div>
        </div>
        <div v-if="orchestrator.selectedStep.error" class="detail-section">
          <div class="section-label error">错误</div>
          <div class="error-content">{{ orchestrator.selectedStep.error }}</div>
        </div>
        <div
          v-if="orchestrator.selectedStep.status === 'completed' || orchestrator.selectedStep.status === 'failed'"
          class="detail-actions"
        >
          <button
            class="btn-rollback"
            @click="handleRollback(orchestrator.selectedStep.step_id)"
          >
            🔁 从此步骤重新执行
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.workflow-sidebar {
  display: flex;
  flex-shrink: 0;
  width: 36px;
  overflow: hidden;
  transition: width 0.3s ease;
  background: #0d1117;
  border-left: 1px solid #30363d;
}

.workflow-sidebar.open {
  width: 400px;
}

.sidebar-toggle {
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

.sidebar-toggle:hover {
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

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.sidebar-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid #30363d;
}

.sidebar-header h3 {
  margin: 0;
  font-size: 14px;
  color: #e6edf3;
}

.status-badge {
  font-size: 11px;
  font-weight: 600;
}

/* Replan banner */
.replan-banner {
  background: #1c1206;
  border: 1px solid #d29922;
  border-radius: 6px;
  margin: 8px;
  padding: 10px;
}

.replan-reason {
  font-size: 12px;
  color: #d29922;
  margin-bottom: 8px;
  line-height: 1.4;
}

.replan-actions {
  display: flex;
  gap: 8px;
}

.btn-approve,
.btn-reject {
  flex: 1;
  padding: 4px 12px;
  border-radius: 4px;
  border: none;
  font-size: 12px;
  cursor: pointer;
}

.btn-approve {
  background: #238636;
  color: #fff;
}

.btn-approve:hover {
  background: #2ea043;
}

.btn-reject {
  background: #30363d;
  color: #e6edf3;
}

.btn-reject:hover {
  background: #3d444d;
}

/* Plan summary */
.plan-summary {
  padding: 8px 16px;
  font-size: 12px;
  color: #8b949e;
  line-height: 1.5;
  border-bottom: 1px solid #21262d;
}

/* Graph area */
.graph-area {
  flex: 1;
  min-height: 200px;
  position: relative;
}

.empty-graph {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #6e7681;
  font-size: 13px;
}

/* Step detail panel */
.step-detail {
  border-top: 1px solid #30363d;
  padding: 12px;
  max-height: 45%;
  overflow-y: auto;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.detail-agent {
  font-size: 13px;
  font-weight: 600;
  color: #e6edf3;
  flex: 1;
}

.detail-status {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  background: #30363d;
  color: #8b949e;
}

.detail-status.completed { background: #238636; color: #fff; }
.detail-status.failed { background: #da3633; color: #fff; }
.detail-status.running { background: #1f6feb; color: #fff; }

.detail-close {
  background: none;
  border: none;
  color: #8b949e;
  font-size: 16px;
  cursor: pointer;
  padding: 0 4px;
}

.detail-close:hover {
  color: #e6edf3;
}

.detail-desc {
  font-size: 12px;
  color: #8b949e;
  line-height: 1.5;
  margin-bottom: 8px;
}

.detail-meta {
  font-size: 11px;
  color: #6e7681;
  margin-bottom: 8px;
}

.detail-section {
  margin-bottom: 10px;
}

.section-label {
  font-size: 11px;
  font-weight: 600;
  color: #8b949e;
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.section-label.error {
  color: #f85149;
}

.result-content,
.error-content {
  font-size: 12px;
  color: #e6edf3;
  line-height: 1.5;
  padding: 8px;
  background: #161b22;
  border-radius: 6px;
  max-height: 200px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.error-content {
  color: #f85149;
}

.detail-actions {
  margin-top: 8px;
}

.btn-rollback {
  width: 100%;
  padding: 6px 12px;
  background: #1f6feb;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
}

.btn-rollback:hover {
  background: #388bfd;
}

/* Vue Flow overrides */
:deep(.vue-flow) {
  background: #0d1117;
}

:deep(.vue-flow__controls) {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 6px;
}

:deep(.vue-flow__controls button) {
  background: #161b22;
  color: #8b949e;
  border-bottom: 1px solid #30363d;
}

:deep(.vue-flow__controls button:hover) {
  background: #1c2129;
}

.step-detail::-webkit-scrollbar,
.result-content::-webkit-scrollbar,
.error-content::-webkit-scrollbar {
  width: 6px;
}

.step-detail::-webkit-scrollbar-thumb,
.result-content::-webkit-scrollbar-thumb,
.error-content::-webkit-scrollbar-thumb {
  background: #30363d;
  border-radius: 3px;
}
</style>
