<template>
  <el-container class="main-container">
    <el-header class="main-header">
      <div class="title-area">
        <h1 class="title">Emby Virtual Proxy 配置面板</h1>
      </div>

      <div class="controls-area">
        <el-switch
          v-model="isDarkMode"
          class="theme-switch"
          inline-prompt
          :active-icon="Moon"
          :inactive-icon="Sunny"
          @change="toggleDark"
        />
        
        <div class="status-area" v-if="store.dataStatus">
          <el-tag :type="store.dataStatus.type === 'error' ? 'danger' : 'success'" effect="plain">
            {{ store.dataStatus.text }}
          </el-tag>
        </div>
      </div>
    </el-header>

    <el-main class="main-content">
      <el-tabs v-model="activeTab" class="main-tabs">
        <el-tab-pane label="核心设置" name="core">
          <div class="settings-grid">
            <SystemSettings />
            <VirtualLibraries />
          </div>
        </el-tab-pane>
        <el-tab-pane label="高级筛选器" name="filters">
          <AdvancedFilterManager />
        </el-tab-pane>
      </el-tabs>
    </el-main>
  </el-container>

  <!-- 所有的弹窗都放在这里，确保它们在顶层，不会被遮挡 -->
  <LibraryEditDialog />
  <DisplayOrderManager />
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { useMainStore } from '@/stores/main';
import { Sunny, Moon } from '@element-plus/icons-vue';
import SystemSettings from '@/components/SystemSettings.vue';
import VirtualLibraries from '@/components/VirtualLibraries.vue';
import AdvancedFilterManager from '@/components/AdvancedFilterManager.vue'; // <-- 导入新组件
import LibraryEditDialog from '@/components/LibraryEditDialog.vue';
import DisplayOrderManager from '@/components/DisplayOrderManager.vue';

const store = useMainStore();
const isDarkMode = ref(false);
const activeTab = ref('core'); // <-- 控制标签页

const toggleDark = (value) => {
  const html = document.documentElement;
  if (value) {
    html.classList.add('dark');
    localStorage.setItem('theme', 'dark');
  } else {
    html.classList.remove('dark');
    localStorage.setItem('theme', 'light');
  }
  isDarkMode.value = value;
};

onMounted(() => {
  store.fetchAllInitialData();
  const savedTheme = localStorage.getItem('theme');
  const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  if (savedTheme === 'dark' || (!savedTheme && prefersDark)) {
    toggleDark(true);
  } else {
    toggleDark(false);
  }
});
</script>

<style>
/* 将部分样式提升为全局，以确保主题切换生效 */
.el-button.is-text {
  /* 确保文字按钮在深色模式下颜色正确 */
  color: var(--el-button-text-color);
}
</style>

<style scoped>
.main-container {
  max-width: 1280px;
  margin: 0 auto;
  padding: 2rem;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}
.main-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
  border-bottom: 1px solid var(--el-border-color-light);
  padding-bottom: 1rem;
}
.title-area {
  display: flex;
  align-items: center;
}
.title {
  font-size: 1.5rem;
  font-weight: 600;
  margin: 0;
  color: var(--el-text-color-primary);
}
.controls-area {
  display: flex;
  align-items: center;
  gap: 16px;
}
.status-area .el-tag {
  font-size: 14px;
}
.settings-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 2rem;
}

/* 修复夜间模式开关图标颜色 */
.theme-switch {
  --el-switch-on-color: #2c2c2c;
  --el-switch-off-color: #dcdfe6; /* 亮色模式背景，使用Element Plus的边框颜色，更清晰 */
  --el-switch-border-color: var(--el-border-color);
}
.theme-switch .el-switch__core .el-icon {
  color: #303133; /* 亮色模式下图标颜色，使用主要文字颜色 */
}
.dark .theme-switch .el-switch__core .el-icon {
  color: #999; /* 暗色模式下图标颜色，调亮一点更清晰 */
}
.theme-switch .is-active .el-icon {
  color: #fff; /* 激活时（无论日夜）图标颜色 */
}
</style>
