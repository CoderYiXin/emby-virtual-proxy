// frontend/src/stores/main.js (最终修复版)

import { defineStore } from 'pinia';
import { ElMessage } from 'element-plus';
import api from '../api';

export const useMainStore = defineStore('main', {
  state: () => ({
    config: { 
        emby_url: '', 
        emby_api_key: '', 
        hide: [], 
        display_order: [], 
        advanced_filters: [],
        library: [] // 确保 config 对象中有 library 数组
    },
    originalConfigForComparison: null,
    // 【核心修复】: 删除独立的 virtualLibraries 状态，它应该始终是 config 的一部分
    // virtualLibraries: [], 
    classifications: {},
    saving: false,
    dataLoading: false,
    dataStatus: null,
    dialogVisible: false,
    isEditing: false,
    currentLibrary: {},
    allLibrariesForSorting: [],
    layoutManagerVisible: false,
    coverGenerating: false,
    personNameCache: {},
  }),

  getters: {
    // 【核心修复】: 直接从 config.library 读取数据
    virtualLibraries: (state) => state.config.library || [],

    sortedLibsInDisplayOrder: (state) => {
        if (!state.config.display_order || !state.allLibrariesForSorting.length) {
            return [];
        }
        const libMap = new Map(state.allLibrariesForSorting.map(lib => [lib.id, lib]));
        return state.config.display_order
            .map(id => libMap.get(id))
            .filter(Boolean);
    },
    unsortedLibs: (state) => {
        if (!state.allLibrariesForSorting.length) return [];
        const sortedIds = new Set(state.config.display_order || []);
        return state.allLibrariesForSorting.filter(lib => !sortedIds.has(lib.id));
    },
    availableResources: (state) => {
      const type = state.currentLibrary?.resource_type;
      if (!type || !state.classifications) return [];
      const pluralTypeMap = {
        collection: 'collections',
        tag: 'tags',
        genre: 'genres',
        studio: 'studios',
        person: 'persons'
      };
      return state.classifications[pluralTypeMap[type]] || [];
    },
  },

  actions: {
    async fetchAllInitialData() {
      this.dataLoading = true;
      this.dataStatus = null;
      try {
        const [configRes, classificationsRes, allLibsRes] = await Promise.all([
          api.getConfig(),
          api.getClassifications(),
          api.getAllLibraries(),
        ]);
        
        // 直接将获取到的配置赋值给 state.config
        this.config = configRes.data;
        if (!this.config.advanced_filters) this.config.advanced_filters = [];
        if (!this.config.library) this.config.library = []; // 确保 library 数组存在

        this.originalConfigForComparison = JSON.parse(JSON.stringify(configRes.data));
        this.classifications = classificationsRes.data;
        this.allLibrariesForSorting = allLibsRes.data;

        if (!this.config.display_order || this.config.display_order.length === 0) {
            if (this.allLibrariesForSorting.length > 0) {
                this.config.display_order = this.allLibrariesForSorting.map(l => l.id);
            }
        }
        this.resolveVisiblePersonNames();
        this.dataStatus = { type: 'success', text: 'Emby数据已加载' };
      } catch (error) {
        this._handleApiError(error, '加载初始数据失败');
        this.dataStatus = { type: 'error', text: 'Emby数据加载失败' };
      } finally {
        this.dataLoading = false;
      }
    },

    async _reloadConfigAndAllLibs() {
        try {
            const [configRes, allLibsRes] = await Promise.all([
                api.getConfig(),
                api.getAllLibraries()
            ]);
            this.config = configRes.data;
            if (!this.config.advanced_filters) this.config.advanced_filters = [];
            if (!this.config.library) this.config.library = [];

            this.originalConfigForComparison = JSON.parse(JSON.stringify(configRes.data));
            this.allLibrariesForSorting = allLibsRes.data;
            this.resolveVisiblePersonNames();
        } catch (error) {
            this._handleApiError(error, "刷新配置列表失败");
        }
    },

    // --- 所有其他 actions 保持和上一版一样 ---
    // 为了确保万无一失，我将它们全部粘贴在这里

    async saveAdvancedFilters(filters) {
        this.saving = true;
        try {
            await api.saveAdvancedFilters(filters);
            this.config.advanced_filters = filters;
        } catch (error) {
            this._handleApiError(error, "保存高级筛选器失败");
            throw error;
        } finally {
            this.saving = false;
        }
    },
    
    async generateLibraryCover(libraryId, libraryName, titleEn, styleName) {
        this.coverGenerating = true;
        try {
            const response = await api.generateCover(libraryId, libraryName, titleEn, styleName);
            if (response.data && response.data.success) {
                ElMessage.success("封面已在后台生成！请点击保存。");
                const newImageTag = response.data.image_tag;
                if (this.currentLibrary && this.currentLibrary.id === libraryId) {
                    this.currentLibrary.image_tag = newImageTag;
                }
                return true;
            }
            return false;
        } catch (error) {
            this._handleApiError(error, "封面生成失败");
            return false;
        } finally {
            this.coverGenerating = false;
        }
    },

    async saveLibrary() {
      const libraryToSave = this.currentLibrary;
      if (!libraryToSave.name || (libraryToSave.resource_type !== 'all' && !libraryToSave.resource_id)) {
        ElMessage.warning('请填写所有必填字段');
        return;
      }
      this.saving = true;
      const action = this.isEditing ? api.updateLibrary(libraryToSave.id, libraryToSave) : api.addLibrary(libraryToSave);
      const successMsg = this.isEditing ? '虚拟库已更新' : '虚拟库已添加';
      try {
        await action;
        ElMessage.success(successMsg);
        this.dialogVisible = false;
        await this._reloadConfigAndAllLibs();
      } catch (error) {
        this._handleApiError(error, '保存虚拟库失败');
      } finally {
        this.saving = false;
      }
    },
    
    resolveVisiblePersonNames() {
        if (!this.config.library) return;
        const personLibs = this.config.library.filter(lib => lib.resource_type === 'person');
        for (const lib of personLibs) {
            if (lib.resource_id) { this.resolvePersonName(lib.resource_id); }
        }
    },
    
    async fetchAllEmbyData() {
        this.dataLoading = true;
        this.dataStatus = { type: 'info', text: '正在刷新...' };
        try {
            const [classificationsRes, allLibsRes] = await Promise.all([
                api.getClassifications(),
                api.getAllLibraries(),
            ]);
            this.classifications = classificationsRes.data;
            this.allLibrariesForSorting = allLibsRes.data;
            this.dataStatus = { type: 'success', text: 'Emby数据已刷新' };
            ElMessage.success("分类和媒体库数据已从Emby刷新！");
        } catch (error) {
            this._handleApiError(error, '刷新Emby数据失败');
            this.dataStatus = { type: 'error', text: '刷新失败' };
        } finally {
            this.dataLoading = false;
        }
    },

    async saveDisplayOrder(orderedIds) {
        this.saving = true;
        try {
            // 直接修改 state.config.display_order
            this.config.display_order = orderedIds;
            // 然后将整个 config 对象保存
            await api.saveDisplayOrder(this.config.display_order);
            ElMessage.success("主页布局已保存！");
            await this._reloadConfigAndAllLibs();
        } catch (error) {
            this._handleApiError(error, "保存布局失败");
        } finally {
            this.saving = false;
        }
    },
    openLayoutManager() {
        this.layoutManagerVisible = true;
    },
    async deleteLibrary(id) {
        try {
            await api.deleteLibrary(id);
            ElMessage.success('虚拟库已删除');
            await this._reloadConfigAndAllLibs();
        } catch (error) {
            this._handleApiError(error, '删除虚拟库失败');
        }
    },
    async restartProxyServer() {
        this.saving = true;
        try {
            await api.restartProxy();
            ElMessage.success("代理服务重启命令已发送！它将在几秒后恢复服务。");
        } catch (error) {
            this._handleApiError(error, "重启代理服务失败");
        } finally {
            this.saving = false;
        }
    },

    async clearAllCovers() {
        this.saving = true;
        try {
            await api.clearCovers();
            ElMessage.success("所有本地封面已清空！");
            // 刷新配置以更新UI（清除image_tag）
            await this._reloadConfigAndAllLibs();
        } catch (error) {
            this._handleApiError(error, "清空封面失败");
        } finally {
            this.saving = false;
        }
    },
    
    async saveConfig() {
        this.saving = true;
        try {
            await api.updateConfig(this.config);
            ElMessage.success('系统设置已保存');
            this.originalConfigForComparison = JSON.parse(JSON.stringify(this.config));
        } catch (error) {
            this._handleApiError(error, '保存设置失败');
        } finally {
            this.saving = false;
        }
    },
    openAddDialog() {
        this.isEditing = false;
        this.currentLibrary = { 
            name: '', 
            resource_type: 'collection', 
            resource_id: '',
            merge_by_tmdb_id: false,
            image_tag: null
        };
        this.dialogVisible = true;
    },
    openEditDialog(library) {
        this.isEditing = true;
        this.currentLibrary = JSON.parse(JSON.stringify(library));
        if (this.currentLibrary.merge_by_tmdb_id === undefined) {
            this.currentLibrary.merge_by_tmdb_id = false;
        }
        if (library.resource_type === 'person' && library.resource_id) {
            this.resolvePersonName(library.resource_id);
        }
        this.dialogVisible = true;
    },
    _handleApiError(error, messagePrefix) {
        const detail = error.response?.data?.detail;
        ElMessage.error(`${messagePrefix}: ${detail || '请检查网络或联系管理员'}`);
    },
    async resolvePersonName(personId) {
        if (!personId || this.personNameCache[personId]) { return; }
        this.personNameCache[personId] = '...';
        try {
            const response = await api.resolveItem(personId);
            this.personNameCache[personId] = response.data.name;
        } catch (error) {
            console.error(`解析人员ID ${personId} 失败:`, error);
            this.personNameCache[personId] = '未知';
        }
    },
  },
});
