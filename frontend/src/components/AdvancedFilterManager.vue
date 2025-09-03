<template>
  <el-card class="box-card" shadow="never">
    <template #header>
      <div class="card-header">
        <span>高级筛选器管理</span>
        <div>
          <!-- 说明文档触发按钮 -->
          <el-button :icon="InfoFilled" circle @click="helpDialogVisible = true" title="查看筛选效率说明"></el-button>
          <el-button type="primary" :icon="Plus" @click="openAddDialog">新增筛选器</el-button>
        </div>
      </div>
    </template>
    
    <el-table :data="filters" style="width: 100%" v-loading="store.saving">
      <el-table-column prop="name" label="筛选器名称" width="200"></el-table-column>
      <el-table-column label="匹配逻辑">
        <template #default="scope">
          匹配 {{ scope.row.match_all ? '所有' : '任意' }} 条件 (共 {{ scope.row.rules.length }} 条)
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" align="right">
        <template #default="scope">
          <el-button size="small" @click="openEditDialog(scope.row)">编辑</el-button>
          <el-popconfirm title="确定删除这个筛选器吗？" @confirm="deleteFilter(scope.row.id)">
            <template #reference>
              <el-button size="small" type="danger">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 编辑/新增筛选器的对话框 -->
    <el-dialog v-model="dialogVisible" :title="isEditing ? '编辑筛选器' : '新增筛选器'" width="60%">
      <el-form :model="currentFilter" label-width="120px">
        <el-form-item label="筛选器名称">
          <el-input v-model="currentFilter.name"></el-input>
        </el-form-item>
        <el-form-item label="匹配逻辑">
          <el-radio-group v-model="currentFilter.match_all">
            <el-radio :value="true">匹配所有条件 (AND)</el-radio>
            <el-radio :value="false">匹配任意条件 (OR)</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-divider>规则</el-divider>
        
        <!-- 【【【 MODIFIED: 优化了规则行的布局 】】】 -->
        <div v-for="(rule, index) in currentFilter.rules" :key="index" class="rule-row">
            <el-select v-model="rule.field" placeholder="选择字段" style="width: 280px; margin-right: 10px; flex-shrink: 0;">
                <el-option label="社区评分 (CommunityRating)" value="CommunityRating"></el-option>
                <el-option label="影评人评分 (CriticRating)" value="CriticRating"></el-option>
                <el-option label="官方分级 (OfficialRating)" value="OfficialRating"></el-option>
                <el-option label="发行年份 (ProductionYear)" value="ProductionYear"></el-option>
                <el-option label="首播日期 (PremiereDate)" value="PremiereDate"></el-option>
                <el-option label="类型 (Genres)" value="Genres"></el-option>
                <el-option label="标签 (Tags)" value="Tags"></el-option>
                <el-option label="工作室 (Studios)" value="Studios"></el-option>
                <el-option label="视频范围 (VideoRange)" value="VideoRange"></el-option>
                <el-option label="文件容器 (Container)" value="Container"></el-option>
                <el-option label="名称以...开头 (NameStartsWith)" value="NameStartsWith"></el-option>
                <el-option label="剧集状态 (SeriesStatus)" value="SeriesStatus"></el-option>
                <el-option label="是否为电影 (IsMovie)" value="IsMovie"></el-option>
                <el-option label="是否为剧集 (IsSeries)" value="IsSeries"></el-option>
                <el-option label="已播放 (IsPlayed)" value="IsPlayed"></el-option>
                <el-option label="未播放 (IsUnplayed)" value="IsUnplayed"></el-option>
                <el-option label="有字幕 (HasSubtitles)" value="HasSubtitles"></el-option>
                <el-option label="有官方评级 (HasOfficialRating)" value="HasOfficialRating"></el-option>
                <el-option label="拥有TMDB ID (ProviderIds.Tmdb)" value="ProviderIds.Tmdb"></el-option>
                <el-option label="拥有IMDB ID (ProviderIds.Imdb)" value="ProviderIds.Imdb"></el-option>
                <el-option label="名称 (Name)" value="Name"></el-option>
            </el-select>
            <el-select v-model="rule.operator" placeholder="选择操作" style="width: 150px; margin-right: 10px; flex-shrink: 0;">
                <el-option label="等于" value="equals"></el-option>
                <el-option label="不等于" value="not_equals"></el-option>
                <el-option label="包含" value="contains"></el-option>
                <el-option label="不包含" value="not_contains"></el-option>
                <el-option label="大于" value="greater_than"></el-option>
                <el-option label="小于" value="less_than"></el-option>
                <el-option label="为空" value="is_empty"></el-option>
                <el-option label="不为空" value="is_not_empty"></el-option>
            </el-select>
            <!-- 根据字段类型动态显示输入控件 -->
            <template v-if="!['is_empty', 'is_not_empty'].includes(rule.operator)">
              <div v-if="rule.field === 'PremiereDate'" style="display: flex; flex-grow: 1; margin-right: 10px;">
                <el-date-picker
                  v-model="rule.value"
                  type="date"
                  placeholder="选择日期"
                  value-format="YYYY-MM-DD"
                  style="flex-grow: 1;"
                  :disabled="!!rule.relative_days"
                />
                <el-input-number
                  :model-value="rule.relative_days"
                  @change="setRelativeDate(rule, $event)"
                  placeholder="最近N天内"
                  :min="1"
                  controls-position="right"
                  style="width: 150px; margin-left: 10px;"
                />
                <el-button text @click="setRelativeDate(rule, null)" v-if="rule.relative_days" style="margin-left: 5px;">清除</el-button>
              </div>
              <el-input 
                v-else 
                v-model="rule.value" 
                placeholder="输入值" 
                style="flex-grow: 1; margin-right: 10px;"
              ></el-input>
            </template>
            <el-button type="danger" :icon="Delete" circle @click="removeRule(index)"></el-button>
        </div>

        <el-button type="primary" plain @click="addRule" style="margin-top: 10px;">添加规则</el-button>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="saveFilter" :loading="store.saving">保存</el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 最终版说明对话框 -->
    <el-dialog v-model="helpDialogVisible" title="高级筛选器性能指南" width="65%">
      <div style="padding: 0 10px;">
        <h4 style="font-size: 18px; margin-top: 0;">
          <span style="color: #67C23A;">🚀 高效筛选规则对照表</span>
        </h4>
        <p>当您创建的规则完全符合下表中的“字段”和“高效操作符”组合时，筛选将由 Emby/Jellyfin 服务器原生执行，速度最快。</p>
        
        <el-table :data="efficientRulesTableData" border style="width: 100%" size="small">
          <el-table-column prop="field" label="字段" width="220"></el-table-column>
          <el-table-column prop="operators" label="高效操作符">
            <template #default="scope">
              <div v-html="scope.row.operators" class="operator-tags"></div>
            </template>
          </el-table-column>
          <el-table-column prop="notes" label="说明 / 示例">
             <template #default="scope">
              <div v-html="scope.row.notes"></div>
            </template>
          </el-table-column>
        </el-table>

        <el-divider></el-divider>

        <h4 style="font-size: 18px;">
          <span style="color: #E6A23C;">🐢 低效筛选规则说明</span>
        </h4>
        <p>当出现以下任意一种情况时，筛选将被降级到代理服务器处理，<strong style="color: #F56C6C;">可能导致性能问题</strong>：</p>
        <ul class="low-efficiency-list">
            <li>当 <strong>匹配逻辑</strong> 设置为 <el-tag type="warning" size="small">匹配任意条件 (OR)</el-tag> 时。</li>
            <li>当 <strong>字段</strong> 选择为 <el-tag type="warning" size="small">名称 (Name)</el-tag> 时 (无论使用何种操作符)。</li>
            <li>当 <strong>操作符</strong> 选择为 <el-tag type="warning" size="small">不等于</el-tag> <el-tag type="warning" size="small">包含</el-tag> <el-tag type="warning" size="small">不包含</el-tag> 时。</li>
            <li>当 <strong>操作符</strong> 为 <el-tag type="warning" size="small">为空</el-tag> / <el-tag type="warning" size="small">不为空</el-tag>，但 <strong>字段</strong> 不是 <el-tag type="success" size="small">拥有TMDB/IMDB ID</el-tag> 时。
                <br>
                <small><i>例如：检查 “社区评分” <el-tag type="warning" size="small">为空</el-tag> 是低效的。</i></small>
            </li>
        </ul>
        
        <el-alert
          title="💡 最佳实践建议"
          type="info"
          :closable="false"
          show-icon
          style="margin-top: 25px;"
        >
          <p style="margin: 0; line-height: 1.5;">优先使用 <el-tag size="small">匹配所有条件 (AND)</el-tag>，并确保每一条规则都符合上方“高效筛选对照表”。</p>
        </el-alert>

      </div>
      
      <template #footer>
          <span class="dialog-footer">
              <el-button type="primary" @click="helpDialogVisible = false">我明白了</el-button>
          </span>
      </template>
    </el-dialog>

  </el-card>
</template>

<script setup>
import { ref, computed } from 'vue';
import { useMainStore } from '../stores/main';
import { ElMessage } from 'element-plus';
import { Plus, Delete, InfoFilled } from '@element-plus/icons-vue';
import { v4 as uuidv4 } from 'uuid';

const store = useMainStore();
const filters = computed(() => store.config.advanced_filters || []);

const dialogVisible = ref(false);
const isEditing = ref(false);
const currentFilter = ref(null);

const helpDialogVisible = ref(false);

// 修改：设置相对日期的方法
const setRelativeDate = (rule, days) => {
  if (days) {
    rule.relative_days = days;
    rule.value = null; // 清除绝对日期以避免混淆
    rule.operator = 'greater_than'; // 自动将操作符设置为“大于”
  } else {
    rule.relative_days = null; // 清除相对日期
  }
};

const efficientRulesTableData = ref([
  { field: '社区评分 (CommunityRating)', operators: '<el-tag type="info" size="small">大于</el-tag><el-tag type="info" size="small">小于</el-tag><el-tag type="info" size="small">等于</el-tag>', notes: '用于筛选数字评分。例：大于 <code>7.5</code>' },
  { field: '影评人评分 (CriticRating)', operators: '<el-tag type="info" size="small">大于</el-tag><el-tag type="info" size="small">小于</el-tag><el-tag type="info" size="small">等于</el-tag>', notes: '用于筛选数字评分。例：大于 <code>80</code>' },
  { field: '发行年份 (ProductionYear)', operators: '<el-tag type="info" size="small">大于</el-tag><el-tag type="info" size="small">小于</el-tag><el-tag type="info" size="small">等于</el-tag>', notes: '用于筛选年份。例：等于 <code>2023</code>' },
  { field: '首播日期 (PremiereDate)', operators: '<el-tag type="info" size="small">大于</el-tag><el-tag type="info" size="small">小于</el-tag><el-tag type="info" size="small">等于</el-tag>', notes: '用于筛选确切日期。例：大于 <code>2023-01-01</code><br>💡 支持输入相对时间。' },
  { field: '官方分级 (OfficialRating)', operators: '<el-tag size="small">等于</el-tag>', notes: '例：等于 <code>PG-13</code> (输入时不含引号)' },
  { field: '类型 (Genres)', operators: '<el-tag size="small">等于</el-tag>', notes: '效果为“包含该类型”。例：等于 <code>动作</code> (输入时不含引号)' },
  { field: '标签 (Tags)', operators: '<el-tag size="small">等于</el-tag>', notes: '效果为“包含该标签”。例：等于 <code>4K臻享</code> (输入时不含引号)' },
  { field: '工作室 (Studios)', operators: '<el-tag size="small">等于</el-tag>', notes: '效果为“包含该工作室”。例：等于 <code>Disney</code> (输入时不含引号)' },
  { field: '视频范围 (VideoRange)', operators: '<el-tag size="small">等于</el-tag>', notes: '例：等于 <code>HDR</code> (输入时不含引号)' },
  { field: '文件容器 (Container)', operators: '<el-tag size="small">等于</el-tag>', notes: '例：等于 <code>mkv</code> (输入时不含引号)' },
  { field: '名称以...开头 (NameStartsWith)', operators: '<el-tag size="small">等于</el-tag>', notes: '例：等于 <code>The</code>' },
  { field: '剧集状态 (SeriesStatus)', operators: '<el-tag size="small">等于</el-tag>', notes: '值为 <code>Continuing</code> 或 <code>Ended</code>' },
  { field: '是否为电影 (IsMovie)', operators: '<el-tag size="small">等于</el-tag>', notes: '值为 <code>true</code> 或 <code>false</code>' },
  { field: '是否为剧集 (IsSeries)', operators: '<el-tag size="small">等于</el-tag>', notes: '值为 <code>true</code> 或 <code>false</code>' },
  { field: '已播放 (IsPlayed)', operators: '<el-tag size="small">等于</el-tag>', notes: '值为 <code>true</code> 或 <code>false</code>' },
  { field: '未播放 (IsUnplayed)', operators: '<el-tag size="small">等于</el-tag>', notes: '值为 <code>true</code> 或 <code>false</code>' },
  { field: '有字幕 (HasSubtitles)', operators: '<el-tag size="small">等于</el-tag>', notes: '值为 <code>true</code> 或 <code>false</code>' },
  { field: '有官方评级 (HasOfficialRating)', operators: '<el-tag size="small">等于</el-tag>', notes: '值为 <code>true</code> 或 <code>false</code>' },
  { field: '拥有TMDB ID', operators: '<el-tag type="success" size="small">不为空</el-tag><el-tag type="danger" size="small">为空</el-tag>', notes: '选择此操作后，<strong>无需填写</strong>任何值。' },
  { field: '拥有IMDB ID', operators: '<el-tag type="success" size="small">不为空</el-tag><el-tag type="danger" size="small">为空</el-tag>', notes: '选择此操作后，<strong>无需填写</strong>任何值。' },
]);

const openAddDialog = () => {
  isEditing.value = false;
  currentFilter.value = {
    id: uuidv4(),
    name: '',
    match_all: true,
    rules: [],
  };
  dialogVisible.value = true;
};

const openEditDialog = (filter) => {
  isEditing.value = true;
  currentFilter.value = JSON.parse(JSON.stringify(filter));
  dialogVisible.value = true;
};

const addRule = () => {
  currentFilter.value.rules.push({
    field: '',
    operator: 'equals',
    value: '',
    relative_days: null, // 确保新规则对象包含此字段
  });
};

const removeRule = (index) => {
  currentFilter.value.rules.splice(index, 1);
};

const saveFilter = async () => {
  if (!currentFilter.value.name || currentFilter.value.rules.length === 0) {
    ElMessage.warning('请填写筛选器名称并至少添加一条规则');
    return;
  }
  
  const newFilters = [...(store.config.advanced_filters || [])];
  if (isEditing.value) {
    const index = newFilters.findIndex(f => f.id === currentFilter.value.id);
    if (index !== -1) {
      newFilters[index] = currentFilter.value;
    }
  } else {
    newFilters.push(currentFilter.value);
  }

  try {
    await store.saveAdvancedFilters(newFilters);
    dialogVisible.value = false;
    ElMessage.success('筛选器已保存');
  } catch (error) {
    // 错误消息由 store action 统一处理
  }
};

const deleteFilter = async (id) => {
  const newFilters = (store.config.advanced_filters || []).filter(f => f.id !== id);
  try {
    await store.saveAdvancedFilters(newFilters);
    ElMessage.success('筛选器已删除');
  } catch (error) {
    // 错误消息由 store action 统一处理
  }
};
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.rule-row {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
}

/* 使用 :deep() 以确保样式能应用到 v-html 和 el-tag 组件 */
:deep(code) {
  background-color: var(--el-color-info-light-8);
  padding: 2px 5px;
  border-radius: 4px;
  border: 1px solid var(--el-color-info-light-5);
  color: var(--el-text-color-primary);
  margin: 0 2px;
}

/* 为表格中的操作符标签添加间距 */
:deep(.operator-tags .el-tag) {
  margin: 2px;
}

/* 优化低效列表的行高和边距 */
.low-efficiency-list {
  list-style-type: disc;
  padding-left: 25px;
}
.low-efficiency-list li {
  margin-bottom: 12px;
  line-height: 1.8;
}
</style>
