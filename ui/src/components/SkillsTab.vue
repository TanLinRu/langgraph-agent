<script setup lang="ts">
import { onMounted } from 'vue'
import { useSkillsStore } from '../stores/skills'

const skills = useSkillsStore()

onMounted(() => {
  skills.loadSkills()
})
</script>

<template>
  <div class="skills-tab">
    <div v-if="skills.loading" class="loading-state">加载 Skills...</div>
    <div v-else class="skills-container">
      <div class="skills-header">
        <h2>可用 Skills ({{ skills.skills.length }})</h2>
      </div>

      <div v-if="skills.selectedSkill" class="skill-detail">
        <div class="skill-detail-header">
          <h3>{{ skills.selectedSkill.name }}</h3>
          <button class="close-btn" @click="skills.clearSelection()">×</button>
        </div>
        <p class="skill-detail-desc">{{ skills.selectedSkill.description }}</p>
        <div class="tag-list" v-if="skills.selectedSkill.use_when?.length">
          <h4>适用场景</h4>
          <span v-for="kw in skills.selectedSkill.use_when" :key="kw" class="tag green">{{ kw }}</span>
        </div>
      </div>

      <div class="skills-grid">
        <div v-for="skill in skills.skills" :key="skill.name" class="skill-card" @click="skills.loadSkillDetail(skill.name)">
          <div class="skill-card-icon">🔧</div>
          <h3 class="skill-card-name">{{ skill.name }}</h3>
          <p class="skill-card-desc">{{ skill.description }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.skills-tab {
  overflow-y: auto;
  padding: 20px;
}

.loading-state {
  text-align: center;
  color: #8b949e;
  padding: 40px;
}

.skills-container {
  max-width: 1200px;
  margin: 0 auto;
}

.skills-header h2 {
  font-size: 20px;
  color: #e1e4e8;
  margin-bottom: 4px;
}

.skill-detail {
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 24px;
}

.skill-detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.skill-detail-header h3 {
  font-size: 18px;
  color: #58a6ff;
}

.close-btn {
  background: none;
  border: none;
  color: #8b949e;
  font-size: 24px;
  cursor: pointer;
  line-height: 1;
}

.skill-detail-desc {
  font-size: 14px;
  color: #c9d1d9;
  margin-bottom: 12px;
}

.tag-list h4 {
  font-size: 13px;
  color: #8b949e;
  margin-bottom: 8px;
}

.tag {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
  margin-right: 6px;
  margin-bottom: 4px;
}

.tag.green {
  background: #1a4a2a;
  color: #3fb950;
}

.skills-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.skill-card {
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 10px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s;
}

.skill-card:hover {
  border-color: #58a6ff;
  box-shadow: 0 2px 12px rgba(88, 166, 255, 0.1);
}

.skill-card-icon {
  font-size: 32px;
  margin-bottom: 10px;
}

.skill-card-name {
  font-size: 16px;
  color: #e1e4e8;
  margin-bottom: 6px;
}

.skill-card-desc {
  font-size: 13px;
  color: #8b949e;
}
</style>
