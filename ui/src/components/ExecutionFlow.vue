<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { VueFlow, useVueFlow, Position } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import type { ExecutionGraphData, FlowNode, FlowEdge } from '../types'

const props = defineProps<{
  graphData: ExecutionGraphData | null | undefined
}>()

const emit = defineEmits<{
  (e: 'node-click', nodeId: string): void
}>()

const { fitView, onNodeClick } = useVueFlow()

const nodes = computed(() => {
  if (!props.graphData?.nodes) return []

  return props.graphData.nodes.map((node: FlowNode) => ({
    id: node.id,
    type: node.type || 'default',
    position: node.position,
    label: node.data?.label || node.id,
    style: node.style || getDefaultStyle(node.data?.status || 'pending'),
    data: {
      ...node.data,
      status: node.data?.status || 'pending',
    },
  }))
})

const edges = computed(() => {
  if (!props.graphData?.edges) return []

  return props.graphData.edges.map((edge: FlowEdge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    type: 'smoothstep',
    animated: edge.animated,
    style: edge.style || { stroke: '#6e7681' },
  }))
})

function getDefaultStyle(status: string) {
  const baseStyle = { width: '140px', height: '50px', borderRadius: '8px' }

  switch (status) {
    case 'completed':
      return { ...baseStyle, background: '#1a4a2a', border: '2px solid #3fb950' }
    case 'failed':
      return { ...baseStyle, background: '#4a1a1a', border: '2px solid #f85149' }
    case 'running':
      return { ...baseStyle, background: '#1a3a5c', border: '2px solid #58a6ff' }
    default:
      return { ...baseStyle, background: '#1f2937', border: '2px solid #6e7681' }
  }
}

function handleNodeClick(event: { node: { id: string } }) {
  emit('node-click', event.node.id)
}

onMounted(() => {
  onNodeClick(handleNodeClick)
  setTimeout(() => fitView({ padding: 0.2 }), 100)
})

watch(() => props.graphData, () => {
  setTimeout(() => fitView({ padding: 0.2 }), 100)
})
</script>

<template>
  <div class="execution-flow">
    <div class="flow-header">
      <span class="flow-title">执行流程</span>
      <span v-if="graphData" class="flow-status" :class="graphData.status">
        {{ graphData.status }}
      </span>
    </div>

    <div class="flow-container" v-if="nodes.length > 0">
      <VueFlow
        :nodes="nodes"
        :edges="edges"
        :default-viewport="{ zoom: 0.8 }"
        :min-zoom="0.3"
        :max-zoom="2"
        fit-view-on-init
        class="vue-flow-dark"
      >
        <Background pattern-color="#30363d" gap="16" />
        <Controls position="bottom-right" />
        <MiniMap
          node-color="#30363d"
          mask-color="rgba(13, 17, 23, 0.8)"
          position="top-right"
        />
      </VueFlow>
    </div>

    <div v-else class="empty-flow">
      <span>等待执行图数据...</span>
    </div>
  </div>
</template>

<style>
@import '@vue-flow/core/dist/style.css';
@import '@vue-flow/core/dist/theme-default.css';
@import '@vue-flow/controls/dist/style.css';
@import '@vue-flow/minimap/dist/style.css';

.execution-flow {
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 8px;
  overflow: hidden;
  margin-top: 12px;
}

.flow-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: #161b22;
  border-bottom: 1px solid #30363d;
}

.flow-title {
  font-size: 13px;
  font-weight: 600;
  color: #c9d1d9;
}

.flow-status {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
  font-weight: 600;
}

.flow-status.pending {
  background: #21262d;
  color: #6e7681;
}

.flow-status.running {
  background: #1a3a5c;
  color: #58a6ff;
}

.flow-status.completed {
  background: #1a4a2a;
  color: #3fb950;
}

.flow-status.failed {
  background: #4a1a1a;
  color: #f85149;
}

.flow-container {
  height: 200px;
}

.vue-flow-dark {
  background: #0d1117;
}

.vue-flow-dark .vue-flow__node {
  color: #c9d1d9;
  font-size: 12px;
}

.vue-flow-dark .vue-flow__node-label {
  color: #c9d1d9;
}

.empty-flow {
  height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #6e7681;
  font-size: 13px;
}

.vue-flow-dark .vue-flow__controls {
  background: #161b22;
  border: 1px solid #30363d;
}

.vue-flow-dark .vue-flow__controls-button {
  background: #21262d;
  border-color: #30363d;
  fill: #8b949e;
}

.vue-flow-dark .vue-flow__controls-button:hover {
  background: #30363d;
}

.vue-flow-dark .vue-flow__minimap {
  background: #161b22;
}
</style>