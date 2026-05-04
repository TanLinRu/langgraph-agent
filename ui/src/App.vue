<script setup lang="ts">
import { useAppStore } from './stores/app'
import ChatTab from './components/ChatTab.vue'
import AgentsTab from './components/AgentsTab.vue'
import SkillsTab from './components/SkillsTab.vue'
import WorkflowsTab from './components/WorkflowsTab.vue'
import CliTab from './components/CliTab.vue'
import SopTab from './components/SopTab.vue'

const app = useAppStore()
</script>

<template>
  <div class="app">
    <header class="header">
      <h1>LangGraph Agent</h1>
      <nav class="tabs">
        <button
          v-for="tab in app.tabs"
          :key="tab.id"
          :class="['tab-btn', { active: app.activeTab === tab.id }]"
          @click="app.setActiveTab(tab.id)"
        >
          <span class="tab-icon">{{ tab.icon }}</span>
          {{ tab.label }}
        </button>
      </nav>
    </header>

    <ChatTab v-show="app.activeTab === 'chat'" />
    <AgentsTab v-show="app.activeTab === 'agents'" />
    <SkillsTab v-show="app.activeTab === 'skills'" />
    <WorkflowsTab v-show="app.activeTab === 'workflows'" />
    <CliTab v-show="app.activeTab === 'cli'" />
    <SopTab v-show="app.activeTab === 'sop'" />
  </div>
</template>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f1117; color: #e1e4e8; }
.app { display: flex; flex-direction: column; height: 100vh; background: #161b22; }
.header { background: #0d1117; border-bottom: 1px solid #30363d; padding: 12px 20px; display: flex; align-items: center; gap: 20px; }
.header h1 { font-size: 16px; font-weight: 600; color: #58a6ff; }
.tabs { display: flex; gap: 4px; background: #21262d; padding: 4px; border-radius: 8px; }
.tab-btn { background: transparent; border: none; padding: 6px 16px; font-size: 13px; color: #8b949e; cursor: pointer; border-radius: 6px; display: flex; align-items: center; gap: 6px; }
.tab-btn:hover { color: #c9d1d9; background: #30363d; }
.tab-btn.active { background: #1f6feb; color: #fff; }
.tab-icon { font-size: 14px; }
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }
</style>
