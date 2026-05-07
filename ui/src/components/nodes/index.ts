import { markRaw } from 'vue'
import AgentNode from './AgentNode.vue'
import TriggerNode from './TriggerNode.vue'
import ConditionNode from './ConditionNode.vue'
import LoopNode from './LoopNode.vue'
import OutputNode from './OutputNode.vue'
import OrchestratorNode from './OrchestratorNode.vue'

export const nodeTypes = markRaw({
  agent: AgentNode,
  trigger: TriggerNode,
  condition: ConditionNode,
  loop: LoopNode,
  output: OutputNode,
  orchestrator: OrchestratorNode,
})
