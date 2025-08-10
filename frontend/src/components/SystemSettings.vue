<template>
  <el-card class="box-card" shadow="never">
    <template #header>
      <div class="card-header">
        <span>系统设置</span>
        <el-button type="primary" @click="store.saveConfig()" :loading="store.saving">
          保存所有设置
        </el-button>
      </div>
    </template>
    <el-form label-position="top" label-width="100px" v-if="store.config">
      
      <!-- 【【【 在这里恢复了 Emby 服务器地址和 API 密钥的设置 】】】 -->
      <el-form-item label="Emby 服务器地址">
        <el-input 
          v-model="store.config.emby_url"
          placeholder="例如: http://192.168.1.10:8096"
        />
        <div class="form-item-description">
          您的 Emby 或 Jellyfin 服务器的完整访问地址。
        </div>
      </el-form-item>
      
      <el-form-item label="Emby API 密钥">
        <el-input 
          v-model="store.config.emby_api_key" 
          type="password"
          show-password
          placeholder="请输入您的 API Key"
        />
        <div class="form-item-description">
          请在 Emby 后台 -> API 密钥 中生成一个新的 API Key。
        </div>
      </el-form-item>

      <el-divider />

      <!-- 【【【 新增：缓存开关 】】】 -->
      <el-form-item label="启用内存缓存">
        <el-switch v-model="store.config.enable_cache" />
        <div class="form-item-description">
          开启后，代理服务器会缓存 Emby API 的响应以提高性能。关闭后，所有请求都将直接发往 Emby。
        </div>
      </el-form-item>

      <el-divider />

      <el-form-item label="自动生成封面默认样式">
        <el-select v-model="store.config.default_cover_style" placeholder="请选择默认样式" style="width: 100%;">
          <el-option label="样式一 (多图)" value="style_multi_1"></el-option>
          <el-option label="样式二 (单图)" value="style_single_1"></el-option>
          <el-option label="样式三 (单图)" value="style_single_2"></el-option>
        </el-select>
        <div class="form-item-description">
          此处选择的样式，将作为触发封面“自动生成”时的默认样式。您仍然可以在编辑虚拟库时手动选择其他样式生成。
        </div>
      </el-form-item>

      <el-divider />

      <el-form-item label="危险区域">
        <el-popconfirm
            title="确定要清空所有本地生成的封面吗？"
            width="280"
            confirm-button-text="确定清空"
            cancel-button-text="取消"
            @confirm="store.clearAllCovers()"
        >
            <template #reference>
                <el-button type="danger" :loading="store.saving">清空所有本地封面</el-button>
            </template>
        </el-popconfirm>
        <div class="form-item-description">
          此操作将删除 `config/images` 目录下的所有图片和临时文件，并重置所有虚拟库的封面状态。此操作不可逆。
        </div>
      </el-form-item>

      <el-divider />

      <el-form-item label="全局隐藏类型">
        <el-select
          v-model="store.config.hide"
          multiple
          filterable
          allow-create
          default-first-option
          placeholder="选择或输入类型 (如 'music') 将被全局隐藏"
          style="width: 100%;"
        >
          <el-option
            v-for="item in collectionTypes"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
        <div class="form-item-description">
          在这里选择或输入的类型将被默认隐藏。您可以在“调整主页布局”中覆盖此设置。
        </div>
      </el-form-item>

    </el-form>
  </el-card>
</template>

<script setup>
import { ref } from 'vue';
import { useMainStore } from '@/stores/main';

const store = useMainStore();

const collectionTypes = ref([
  { value: 'movies', label: '电影 (movies)' },
  { value: 'tvshows', label: '电视剧 (tvshows)' },
  { value: 'music', label: '音乐 (music)' },
  { value: 'playlists', label: '播放列表 (playlists)' },
  { value: 'musicvideos', label: '音乐视频 (musicvideos)' },
  { value: 'livetv', label: '电视直播 (livetv)' },
  { value: 'boxsets', label: '合集 (boxsets)' },
  { value: 'photos', label: '照片 (photos)' },
  { value: 'homevideos', label: '家庭视频 (homevideos)' },
  { value: 'books', label: '书籍 (books)' },
]);
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.form-item-description {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
  margin-top: 4px;
}
.el-divider {
  margin: 24px 0;
}
</style>
