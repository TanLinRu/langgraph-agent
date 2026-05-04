import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Workflow, AgentGraph, AgentDef, Skill } from '../types'

export const useWorkflowsStore = defineStore('workflows', () => {
  const workflows = ref<Workflow[]>([])
  const workflowNodes = ref<any[]>([])
  const workflowEdges = ref<any[]>([])
  const workflowName = ref('')
  const workflowDescription = ref('')
  const editingWorkflowId = ref('')
  const showWorkflowModal = ref(false)
  const loading = ref(false)
  const graphMode = ref<'workflows' | 'agents'>('workflows')
  const editingGraphId = ref('')

  async function loadWorkflows() {
    loading.value = true
    try {
      const res = await fetch('/api/workflows')
      const data = await res.json()
      workflows.value = data.workflows || []
    } catch (e) {
      console.error('Failed to load workflows:', e)
    } finally {
      loading.value = false
    }
  }

  function openNewWorkflow() {
    editingWorkflowId.value = ''
    editingGraphId.value = ''
    workflowName.value = ''
    workflowDescription.value = ''
    workflowNodes.value = []
    workflowEdges.value = []
    showWorkflowModal.value = true
  }

  function openEditWorkflow(w: Workflow) {
    editingWorkflowId.value = w.id
    workflowName.value = w.name
    workflowDescription.value = w.description
    workflowNodes.value = (w.nodes || []).map((n: any, i: number) => ({
      ...n,
      position: n.position || { x: 100 + i * 200, y: 100 },
    }))
    workflowEdges.value = w.edges || []
    showWorkflowModal.value = true
  }

  function openEditAgentGraph(g: AgentGraph) {
    editingGraphId.value = g.id
    editingWorkflowId.value = ''
    workflowName.value = g.name
    workflowDescription.value = g.description || ''
    workflowNodes.value = (g.nodes || []).map((n: any, i: number) => ({
      ...n,
      position: n.position || { x: 100 + i * 200, y: 100 },
    }))
    workflowEdges.value = g.edges || []
    showWorkflowModal.value = true
  }

  async function deleteWorkflow(id: string) {
    if (!confirm('确定删除此工作流?')) return
    try {
      await fetch(`/api/workflows/${id}`, { method: 'DELETE' })
      await loadWorkflows()
    } catch (e) {
      console.error('Failed to delete workflow:', e)
    }
  }

  async function saveWorkflow() {
    if (!workflowName.value.trim()) {
      alert('请输入工作流名称')
      return
    }
    try {
      const body = {
        name: workflowName.value,
        description: workflowDescription.value,
        nodes: workflowNodes.value,
        edges: workflowEdges.value,
      }
      const url = editingWorkflowId.value
        ? `/api/workflows/${editingWorkflowId.value}`
        : '/api/workflows'
      const method = editingWorkflowId.value ? 'PUT' : 'POST'
      await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      showWorkflowModal.value = false
      await loadWorkflows()
    } catch (e) {
      console.error('Failed to save workflow:', e)
    }
  }

  async function saveAgentGraph() {
    if (!workflowName.value.trim()) {
      alert('请输入名称')
      return
    }
    try {
      const body = {
        name: workflowName.value,
        description: workflowDescription.value,
        nodes: workflowNodes.value,
        edges: workflowEdges.value,
      }
      const url = editingGraphId.value
        ? `/api/agent-graphs/${editingGraphId.value}`
        : '/api/agent-graphs'
      const method = editingGraphId.value ? 'PUT' : 'POST'
      await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      showWorkflowModal.value = false
    } catch (e) {
      console.error('Failed to save agent graph:', e)
    }
  }

  function addSkillToWorkflow(skill: Skill) {
    const id = `skill-${skill.name}-${Date.now()}`
    const existingCount = workflowNodes.value.filter(n => n.type === 'skill').length
    workflowNodes.value.push({
      id,
      type: 'skill',
      position: { x: 100 + existingCount * 200, y: 100 },
      data: { label: skill.name, description: skill.description, skillName: skill.name },
    })
  }

  function addAgentNode(agent: AgentDef) {
    const id = `agent-${agent.id}-${Date.now()}`
    const existingCount = workflowNodes.value.filter(n => n.type === 'agent' && n.data?.agent_id === agent.id).length
    workflowNodes.value.push({
      id,
      type: 'agent',
      position: { x: 100 + existingCount * 200, y: 100 },
      data: { label: agent.name, description: agent.description, agent_id: agent.id, isBuiltin: agent.is_builtin },
    })
  }

  function addTriggerNode() {
    workflowNodes.value.push({
      id: `trigger-${Date.now()}`,
      type: 'trigger',
      position: { x: 50, y: 100 },
      data: { label: '触发器', triggerType: 'manual' },
    })
  }

  function addConditionNode() {
    workflowNodes.value.push({
      id: `condition-${Date.now()}`,
      type: 'condition',
      position: { x: 300, y: 250 },
      data: { label: '条件分支', condition: '' },
    })
  }

  function addLoopNode() {
    workflowNodes.value.push({
      id: `loop-${Date.now()}`,
      type: 'loop',
      position: { x: 500, y: 100 },
      data: { label: '循环', maxIterations: 5 },
    })
  }

  function addOutputNode() {
    workflowNodes.value.push({
      id: `output-${Date.now()}`,
      type: 'output',
      position: { x: 700, y: 100 },
      data: { label: '输出', outputFormat: 'text' },
    })
  }

  function switchGraphMode(mode: 'workflows' | 'agents') {
    graphMode.value = mode
    workflowName.value = ''
    workflowDescription.value = ''
    workflowNodes.value = []
    workflowEdges.value = []
    editingWorkflowId.value = ''
    editingGraphId.value = ''
  }

  function updateEdges(edges: any[]) {
    workflowEdges.value = edges
  }

  // Aliases for component compatibility
  const list = workflows
  const nodes = workflowNodes
  const edges = workflowEdges
  const formName = workflowName
  const formDescription = workflowDescription
  const showModal = showWorkflowModal
  const editingId = editingWorkflowId

  function openNew() {
    openNewWorkflow()
  }

  function openEdit(w: Workflow) {
    openEditWorkflow(w)
  }

  function remove(id: string) {
    deleteWorkflow(id)
  }

  function save() {
    saveWorkflow()
  }

  function switchMode(mode: 'workflows' | 'agents') {
    switchGraphMode(mode)
  }

  function openNewAgentGraph() {
    editingGraphId.value = ''
    workflowName.value = ''
    workflowDescription.value = ''
    workflowNodes.value = []
    workflowEdges.value = []
    showWorkflowModal.value = true
  }

  function addSkillNode(skill: Skill) {
    addSkillToWorkflow(skill)
  }

  function addEdge(params: any) {
    workflowEdges.value = [...workflowEdges.value, params]
  }

  return {
    workflows, workflowNodes, workflowEdges,
    workflowName, workflowDescription,
    editingWorkflowId, showWorkflowModal, loading,
    graphMode, editingGraphId,
    loadWorkflows, openNewWorkflow, openEditWorkflow,
    openEditAgentGraph, deleteWorkflow,
    saveWorkflow, saveAgentGraph,
    addSkillToWorkflow, addAgentNode,
    addTriggerNode, addConditionNode, addLoopNode, addOutputNode,
    switchGraphMode, updateEdges,
    // Aliases
    list, nodes, edges, formName, formDescription, showModal, editingId,
    openNew, openEdit, remove, save, switchMode,
    openNewAgentGraph, addSkillNode, addEdge,
  }
})
