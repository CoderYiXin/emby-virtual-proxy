<template>
  <el-dialog
    :model-value="store.dialogVisible"
    :title="store.isEditing ? '编辑虚拟库' : '添加虚拟库'"
    width="600px"
    @close="store.dialogVisible = false"
    :close-on-click-modal="false"
  >
    <el-form :model="store.currentLibrary" label-width="120px" v-loading="store.saving">
      <el-form-item label="虚拟库名称" required>
        <el-input v-model="store.currentLibrary.name" placeholder="例如：豆瓣高分电影"></el-input>
      </el-form-item>
      
      <el-form-item label="资源类型" required>
        <el-select v-model="store.currentLibrary.resource_type" @change="store.currentLibrary.resource_id = ''">
          <el-option label="合集 (Collection)" value="collection"></el-option>
          <el-option label="标签 (Tag)" value="tag"></el-option>
          <el-option label="类型 (Genre)" value="genre"></el-option>
          <el-option label="工作室 (Studio)" value="studio"></el-option>
          <el-option label="人员 (Person)" value="person"></el-option>
        </el-select>
      </el-form-item>
      
      <el-form-item label="选择资源" required>
        <el-select 
          v-model="store.currentLibrary.resource_id"
          filterable
          remote
          :remote-method="searchResource"
          :loading="resourceLoading"
          placeholder="请输入关键词搜索"
          style="width: 100%;"
        >
          <el-option
            v-for="item in availableResources"
            :key="item.id"
            :label="item.name"
            :value="item.id"
          >
            <span v-if="store.currentLibrary.resource_type === 'person'">{{ store.personNameCache[item.id] || item.name }}</span>
            <span v-else>{{ item.name }}</span>
          </el-option>
        </el-select>
      </el-form-item>

      <!-- 【【【 核心修改在这里 】】】 -->
      <el-form-item label="高级筛选器">
        <el-select 
          v-model="store.currentLibrary.advanced_filter_id" 
          placeholder="可不选，留空表示不使用"
          style="width: 100%;"
          clearable  
        >
          <!-- 手动添加一个“无”选项，其值为 null -->
          <el-option label="无" :value="null" /> 
          <el-option
            v-for="filter in store.config.advanced_filters"
            :key="filter.id"
            :label="filter.name"
            :value="filter.id"
          />
        </el-select>
      </el-form-item>
      <!-- 【【【 修改结束 】】】 -->
      
      <el-form-item label="TMDB ID 合并">
        <el-switch v-model="store.currentLibrary.merge_by_tmdb_id"></el-switch>
        <el-tooltip content="开启后，同一TMDB ID的影视项目（无论在哪个资料库）将只显示一个版本，通常用于整合4K和1080p版本。注意：这可能会略微增加加载时间。" placement="top">
          <el-icon style="margin-left: 8px; color: #aaa;"><InfoFilled /></el-icon>
        </el-tooltip>
      </el-form-item>
      
      <el-divider>封面生成</el-divider>

      <el-form-item label="当前封面">
        <div class="cover-preview-wrapper">
          <img v-if="store.currentLibrary.image_tag" :src="coverImageUrl" class="cover-preview-image" />
          <div v-else class="cover-preview-placeholder">暂无封面</div>
        </div>
      </el-form-item>
      
      <el-form-item label="封面英文标题">
         <el-input v-model="coverTitleEn" placeholder="可选，用于封面上的英文装饰文字"></el-input>
      </el-form-item>

      <el-form-item label="封面样式">
        <el-select v-model="selectedStyle" placeholder="请选择样式">
          <el-option label="样式一 (多图)" value="style_multi_1"></el-option>
          <el-option label="样式二 (单图)" value="style_single_1"></el-option>
          <el-option label="样式三 (单图)" value="style_single_2"></el-option>
        </el-select>
      </el-form-item>

      <el-form-item>
         <el-button 
            type="primary" 
            @click="handleGenerateCover" 
            :loading="store.coverGenerating"
          >
            {{ store.currentLibrary.image_tag ? '重新生成封面' : '生成封面' }}
          </el-button>
          <div class="button-tips">
            <p class="tip">此功能将从该虚拟库中随机选取内容自动合成封面图。</p>
            <p class="tip tip-warning">注意：生成封面需要缓存数据。请先在客户端访问一次该虚拟库，然后再点此生成。</p>
          </div>
      </el-form-item>

    </el-form>
    <template #footer>
      <span class="dialog-footer">
        <el-button @click="store.dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="store.saveLibrary()" :loading="store.saving">
          {{ store.isEditing ? '保存' : '创建' }}
        </el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue';
import { useMainStore } from '@/stores/main';
import { InfoFilled } from '@element-plus/icons-vue';
import api from '@/api';

const store = useMainStore();
const resourceLoading = ref(false);
const availableResources = ref([]);
const coverTitleEn = ref('');
const selectedStyle = ref('style_multi_1'); // 新增：用于存储所选样式

const coverImageUrl = computed(() => {
  if (store.currentLibrary?.image_tag) {
    // 添加时间戳来强制刷新缓存
    return `/covers/${store.currentLibrary.id}.jpg?t=${store.currentLibrary.image_tag}`;
  }
  return '';
});

// 远程搜索资源的逻辑
const searchResource = async (query) => {
  if (!store.currentLibrary.resource_type) return;
  resourceLoading.value = true;
  try {
    let response;
    if (store.currentLibrary.resource_type === 'person') {
      response = await api.searchPersons(query);
    } else {
      // 对于其他类型，我们从已加载的分类数据中筛选
      const resourceKeyMap = {
        collection: 'collections',
        tag: 'tags',
        genre: 'genres',
        studio: 'studios',
      };
      const key = resourceKeyMap[store.currentLibrary.resource_type];
      if (store.classifications[key]) {
        if (query) {
          availableResources.value = store.classifications[key].filter(item =>
            item.name.toLowerCase().includes(query.toLowerCase())
          );
        } else {
          availableResources.value = store.classifications[key].slice(0, 100); // 默认显示前100个
        }
        return; // 从本地筛选后直接返回
      }
    }
    // 处理人员搜索的API返回
    if (response && response.data) {
        availableResources.value = response.data;
        response.data.forEach(person => {
            if (person.id && !store.personNameCache[person.id]) {
                store.personNameCache[person.id] = person.name;
            }
        });
    }
  } catch (error) {
    console.error("搜索资源失败:", error);
  } finally {
    resourceLoading.value = false;
  }
};

const handleGenerateCover = async () => {
    // 将所选样式传递给 store action
    const success = await store.generateLibraryCover(store.currentLibrary.id, store.currentLibrary.name, coverTitleEn.value, selectedStyle.value);
    // 成功后，store.currentLibrary.image_tag 会被更新，computed 属性 coverImageUrl 会自动重新计算
}

// 监听对话框打开，并预加载资源
watch(() => store.dialogVisible, (newVal) => {
  if (newVal) {
    coverTitleEn.value = ''; // 重置英文标题输入
    selectedStyle.value = 'style_multi_1'; // 重置样式选择
    const resourceType = store.currentLibrary.resource_type;
    const resourceId = store.currentLibrary.resource_id;

    if (resourceType && resourceType !== 'person') {
      searchResource(''); // 为非人员类型预加载数据
    }
    
    // 如果是编辑模式且有资源ID，尝试解析并显示它
    if (store.isEditing && resourceId) {
        if (resourceType === 'person') {
            if(store.personNameCache[resourceId]){
                 availableResources.value = [{id: resourceId, name: store.personNameCache[resourceId]}];
            } else {
                 api.resolveItem(resourceId).then(res => {
                     availableResources.value = [res.data];
                     store.personNameCache[res.data.id] = res.data.name;
                 });
            }
        } else {
             const resourceKeyMap = {
                collection: 'collections', tag: 'tags', genre: 'genres', studio: 'studios',
             };
             const key = resourceKeyMap[resourceType];
             const found = store.classifications[key]?.find(item => item.id === resourceId);
             if(found) availableResources.value = [found];
        }
    } else {
        availableResources.value = [];
    }
  }
});

</script>

<style scoped>
.button-tips {
  margin-left: 10px;
  line-height: 1.4;
  align-self: center;
}
.tip {
  font-size: 12px;
  color: #999;
  margin: 0;
  padding: 0;
}
.tip-warning {
    color: #E6A23C; /* Element Plus warning color */
}
.cover-preview-wrapper {
  width: 200px;
  height: 112.5px; /* 16:9 ratio */
  background-color: #2c2c2c;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.cover-preview-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.cover-preview-placeholder {
  color: #666;
  font-size: 14px;
}
</style>
