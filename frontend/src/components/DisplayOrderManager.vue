<template>
  <el-dialog
    v-model="store.layoutManagerVisible"
    title="调整主页布局"
    width="800px"
    @close="onDialogClose"
  >
    <div class="layout-manager-container">
      <!-- 已显示区域 -->
      <div class="sortable-list-container">
        <h3 class="list-title">已显示 (按顺序)</h3>
        <div class="list-wrapper">
          <draggable
            v-model="displayedLibs"
            group="libs"
            item-key="id"
            class="sortable-list"
          >
            <template #item="{ element }">
              <div class="sortable-item">
                <el-tag :type="element.type === 'real' ? 'primary' : 'success'" size="small" effect="light">
                  {{ element.type === 'real' ? '真实库' : '虚拟库' }}
                </el-tag>
                <span class="lib-name">{{ element.name }}</span>
              </div>
            </template>
          </draggable>
        </div>
      </div>

      <!-- 未显示区域 -->
      <div class="sortable-list-container">
        <h3 class="list-title">未显示</h3>
         <div class="list-wrapper">
          <draggable
            v-model="hiddenLibs"
            group="libs"
            item-key="id"
            class="sortable-list"
          >
            <template #item="{ element }">
              <div class="sortable-item">
                <el-tag :type="element.type === 'real' ? 'primary' : 'success'" size="small" effect="light">
                  {{ element.type === 'real' ? '真实库' : '虚拟库' }}
                </el-tag>
                <span class="lib-name">{{ element.name }}</span>
              </div>
            </template>
          </draggable>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="onDialogClose">取消</el-button>
        <el-button type="primary" @click="saveLayout" :loading="store.saving">
          保存布局
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue';
import draggable from 'vuedraggable'; // 确保你已安装 vuedraggable
import { useMainStore } from '@/stores/main';

const store = useMainStore();

const displayedLibs = ref([]);
const hiddenLibs = ref([]);

const syncLists = () => {
  if (store.layoutManagerVisible) {
    const allLibsMap = new Map(store.allLibrariesForSorting.map(lib => [lib.id, lib]));
    const displayedIds = new Set(store.config.display_order || []);
    
    const newDisplayed = [];
    (store.config.display_order || []).forEach(id => {
      if (allLibsMap.has(id)) {
        newDisplayed.push(allLibsMap.get(id));
      }
    });
    displayedLibs.value = newDisplayed;

    hiddenLibs.value = store.allLibrariesForSorting.filter(lib => !displayedIds.has(lib.id));
  }
};

watch(() => store.layoutManagerVisible, (newValue) => {
  if (newValue) {
    syncLists();
  }
}, { immediate: true });

const onDialogClose = () => {
  store.layoutManagerVisible = false;
};

const saveLayout = async () => {
  const orderedIds = displayedLibs.value.map(lib => lib.id);
  await store.saveDisplayOrder(orderedIds);
  onDialogClose();
};

onMounted(() => {
    // 确保 vuedraggable 已安装
    if (typeof draggable === 'undefined') {
        console.error("vuedraggable is not installed or imported correctly. Please run 'npm install vuedraggable@next'");
    }
});
</script>

<style scoped>
.layout-manager-container {
  display: flex;
  gap: 20px;
  min-height: 400px;
}
.sortable-list-container {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.list-title {
  margin-top: 0;
  margin-bottom: 10px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.list-wrapper {
  flex-grow: 1;
  border: 1px solid var(--el-border-color-light);
  border-radius: 4px;
  padding: 10px;
  background-color: var(--el-fill-color-light);
  overflow-y: auto;
}
.sortable-list {
  min-height: 350px;
}
.sortable-item {
  padding: 8px 12px;
  margin-bottom: 8px;
  background-color: var(--el-bg-color);
  border-radius: 4px;
  cursor: grab;
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--el-border-color);
}
.sortable-item:last-child {
  margin-bottom: 0;
}
.lib-name {
  color: var(--el-text-color-regular);
}
</style>