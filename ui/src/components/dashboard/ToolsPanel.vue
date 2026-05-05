<script setup lang="ts">
import { ref, onMounted } from 'vue'

interface Tool {
  name: string
  description: string
  category: string
}

interface RegistryData {
  tools: Tool[]
  skills: Tool[]
  agents: Tool[]
  total: number
}

const registry = ref<RegistryData | null>(null)
const loading = ref(false)
const error = ref('')
const activeTab = ref<'tools' | 'skills' | 'agents'>('tools')

async function loadRegistry() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetch('/api/registry/tools')
    registry.value = await res.json()
  } catch (e) {
    error.value = String(e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadRegistry()
})
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <span class="panel-icon">🔧</span>
      <span class="panel-title">可用工具</span>
      <button class="refresh-btn" @click="loadRegistry" :disabled="loading">刷新</button>
    </div>

    <div class="tabs">
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'tools' }"
        @click="activeTab = 'tools'"
      >
        工具 ({{ registry?.tools?.length || 0 }})
      </button>
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'skills' }"
        @click="activeTab = 'skills'"
      >
        技能 ({{ registry?.skills?.length || 0 }})
      </button>
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'agents' }"
        @click="activeTab = 'agents'"
      >
        Agent ({{ registry?.agents?.length || 0 }})
      </button>
    </div>

    <div class="panel-body" v-if="registry">
      <div v-if="activeTab === 'tools'" class="items-list">
        <div v-for="item in registry.tools" :key="item.name" class="item">
          <span class="item-name">{{ item.name }}</span>
          <span class="item-desc">{{ item.description }}</span>
        </div>
      </div>

      <div v-else-if="activeTab === 'skills'" class="items-list">
        <div v-for="item in registry.skills" :key="item.name" class="item">
          <span class="item-name">{{ item.name }}</span>
          <span class="item-desc">{{ item.description }}</span>
        </div>
      </div>

      <div v-else-if="activeTab === 'agents'" class="items-list">
        <div v-for="item in registry.agents" :key="item.name" class="item">
          <span class="item-name">{{ item.name }}</span>
          <span class="item-desc">{{ item.description }}</span>
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

.tabs {
  display: flex;
  border-bottom: 1px solid #21262d;
}

.tab-btn {
  flex: 1;
  background: transparent;
  border: none;
  color: #8b949e;
  padding: 6px 8px;
  font-size: 11px;
  cursor: pointer;
  border-bottom: 2px solid transparent;
}

.tab-btn:hover {
  color: #e6edf3;
}

.tab-btn.active {
  color: #58a6ff;
  border-bottom-color: #58a6ff;
}

.panel-body {
  padding: 8px;
  max-height: 200px;
  overflow-y: auto;
}

.panel-body.error {
  color: #f85149;
}

.panel-body.loading {
  color: #8b949e;
  text-align: center;
}

.items-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.item {
  display: flex;
  flex-direction: column;
  padding: 6px 8px;
  background: #21262d;
  border-radius: 4px;
}

.item-name {
  font-size: 12px;
  font-weight: 600;
  color: #e6edf3;
}

.item-desc {
  font-size: 11px;
  color: #8b949e;
  margin-top: 2px;
}
</style>