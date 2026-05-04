import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { TabId, TabDef } from '../types'

export const useAppStore = defineStore('app', () => {
  const activeTab = ref<TabId>('chat')

  const tabs: TabDef[] = [
    { id: 'chat', label: '对话', icon: '💬' },
    { id: 'agents', label: 'Agents', icon: '🤖' },
    { id: 'skills', label: 'Skills', icon: '🔧' },
    { id: 'workflows', label: '工作流编排', icon: '📐' },
    { id: 'cli', label: 'CLI 调度', icon: '🖥️' },
    { id: 'sop', label: 'SOP 状态', icon: '📋' },
  ]

  function setActiveTab(tab: TabId) {
    activeTab.value = tab
  }

  return { activeTab, tabs, setActiveTab }
})
