<script setup lang="ts">
import { onMounted } from 'vue'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import { useWorkflowsStore } from '../stores/workflows'
import { useAgentsStore } from '../stores/agents'
import { useSkillsStore } from '../stores/skills'
import WorkflowModal from './WorkflowModal.vue'
import { nodeTypes } from './nodes'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

const workflows = useWorkflowsStore()
const agents = useAgentsStore()
const skills = useSkillsStore()

const { onConnect, addEdges } = useVueFlow()

onConnect((params) => {
  workflows.addEdge(params)
})

onMounted(() => {
  workflows.loadWorkflows()
  agents.loadAgents()
  agents.loadGraphs()
  skills.loadSkills()
})
</script>

<template>
  <div class="workflows-tab">
    <div class="workflows-layout">
      <div class="workflows-sidebar">
        <div class="mode-tabs">
          <button :class="{ active: workflows.graphMode === 'workflows' }" @click="workflows.switchMode('workflows')">工作流</button>
          <button :class="{ active: workflows.graphMode === 'agents' }" @click="workflows.switchMode('agents')">Agent 图</button>
        </div>

        <div class="sidebar-header">
          <h3>{{ workflows.graphMode === 'workflows' ? '工作流列表' : 'Agent 图列表' }}</h3>
          <button class="new-btn" @click="workflows.graphMode === 'workflows' ? workflows.openNew() : workflows.openNewAgentGraph()">
            + 新建
          </button>
        </div>

        <div v-if="workflows.loading || agents.loading" class="loading-state">加载中...</div>

        <div v-else-if="workflows.graphMode === 'workflows'" class="workflow-list">
          <div v-for="w in workflows.list" :key="w.id" class="workflow-item" @click="workflows.openEdit(w)">
            <h4>{{ w.name }}</h4>
            <p>{{ w.description || '无描述' }}</p>
            <button class="delete-btn" @click.stop="workflows.remove(w.id)">删除</button>
          </div>
        </div>

        <div v-else-if="workflows.graphMode === 'agents'" class="agent-graphs-list">
          <div v-for="g in agents.graphs" :key="g.id" class="workflow-item" @click="workflows.openEditAgentGraph(g)">
            <h4>{{ g.name }}</h4>
            <p>{{ g.description || '无描述' }}</p>
            <button class="delete-btn" @click.stop="agents.deleteGraph(g.id)">删除</button>
          </div>
          <div v-if="agents.graphs.length === 0" class="empty-state">暂无 Agent 图</div>
        </div>

        <div v-if="workflows.graphMode === 'agents'" class="sidebar-section">
          <h4>可用 Agents</h4>
          <div class="agent-node-list">
            <div v-for="a in agents.list" :key="a.id" class="agent-node-item" @click="workflows.addAgentNode(a)">
              <span class="agent-name">{{ a.name }}</span>
              <span v-if="a.is_builtin" class="builtin-badge">内置</span>
            </div>
          </div>
        </div>

        <div v-if="workflows.graphMode === 'workflows' && skills.skills.length > 0 && !workflows.showModal" class="sidebar-section">
          <h4>可用技能</h4>
          <div class="skill-node-list">
            <div v-for="s in skills.skills" :key="s.name" class="skill-node-item" @click="workflows.addSkillNode(s)">
              {{ s.name }}
            </div>
          </div>
        </div>

        <div v-if="!workflows.showModal" class="sidebar-section canvas-tools">
          <h4>画布工具</h4>
          <div class="tool-buttons">
            <button @click="workflows.addTriggerNode()">触发器</button>
            <button @click="workflows.addConditionNode()">条件</button>
            <button @click="workflows.addLoopNode()">循环</button>
            <button @click="workflows.addOutputNode()">输出</button>
          </div>
        </div>
      </div>

      <div class="workflows-canvas">
        <VueFlow
          :nodes="workflows.nodes"
          :edges="workflows.edges"
          :node-types="nodeTypes"
          :default-viewport="{ x: 50, y: 50, zoom: 1 }"
          fit-view-on-init>
          <Background />
          <Controls />
          <MiniMap />
        </VueFlow>
      </div>
    </div>

    <WorkflowModal />
  </div>
</template>

<style scoped>
.workflows-tab {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 50px);
}

.workflows-layout {
  display: flex;
  height: 100%;
}

.workflows-sidebar {
  width: 280px;
  background: #0d1117;
  border-right: 1px solid #30363d;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.mode-tabs {
  display: flex;
  border-bottom: 1px solid #30363d;
}

.mode-tabs button {
  flex: 1;
  background: none;
  border: none;
  color: #8b949e;
  padding: 12px;
  cursor: pointer;
  font-size: 13px;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
}

.mode-tabs button:hover {
  color: #e1e4e8;
}

.mode-tabs button.active {
  color: #58a6ff;
  border-bottom-color: #58a6ff;
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

.workflow-list,
.agent-graphs-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.workflow-item {
  background: #161b22;
  border: 1px solid #21262d;
  border-radius: 6px;
  padding: 10px;
  margin-bottom: 6px;
  cursor: pointer;
}

.workflow-item:hover {
  border-color: #58a6ff;
}

.workflow-item h4 {
  font-size: 13px;
  color: #e1e4e8;
  margin-bottom: 4px;
}

.delete-btn {
  background: none;
  border: none;
  color: #f85149;
  font-size: 11px;
  cursor: pointer;
}

.empty-state {
  color: #8b949e;
  font-size: 12px;
  text-align: center;
  padding: 20px;
}

.sidebar-section {
  padding: 12px;
  border-top: 1px solid #21262d;
}

.sidebar-section h4 {
  font-size: 12px;
  color: #8b949e;
  margin-bottom: 8px;
}

.agent-node-list,
.skill-node-list {
  max-height: 150px;
  overflow-y: auto;
}

.agent-node-item,
.skill-node-item {
  background: #161b22;
  border: 1px solid #21262d;
  border-radius: 4px;
  padding: 6px 8px;
  margin-bottom: 4px;
  cursor: pointer;
  font-size: 12px;
  color: #c9d1d9;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.agent-node-item:hover,
.skill-node-item:hover {
  border-color: #58a6ff;
  background: #1f2428;
}

.agent-name {
  flex: 1;
}

.builtin-badge {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  background: #1f3a5f;
  color: #58a6ff;
}

.canvas-tools .tool-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.canvas-tools .tool-buttons button {
  background: #21262d;
  border: 1px solid #30363d;
  color: #c9d1d9;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 11px;
  cursor: pointer;
}

.canvas-tools .tool-buttons button:hover {
  background: #30363d;
  border-color: #58a6ff;
}

.workflows-canvas {
  flex: 1;
  background: #161b22;
}

:deep(.vue-flow) {
  background: #161b22;
}
</style>
