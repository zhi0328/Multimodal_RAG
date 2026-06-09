<script setup lang="ts">
import { ref, defineProps, defineEmits, onMounted, watch } from 'vue';
import axios from 'axios';

const props = defineProps<{
  datasetPath: string
}>();

const emit = defineEmits(['update:datasetPath']);

const API_URL = '/api';

interface DatasetFile {
  name: string;
  path: string;
  size: number;
  created_at: string;
}

interface Settings {
  llm_base_url: string;
  llm_model_name: string;
  llm_api_key: string;
  judge_base_url: string;
  judge_model_name: string;
  judge_api_key: string;
}

interface Config {
  id: number;
  name: string;
  retrieval_method: string; // vector, keyword, hybrid
  top_k: number;
  use_bm25: boolean;
  rrf_k: number;
  vector_weight: number;
  keyword_weight: number;
  
  use_rerank: boolean;
  initial_top_k: number;
  
  // Advanced slicing & HyDE & Multi-query
  chunk_size: number;
  overlap: number;
  
  use_hyde: boolean;
  use_multiquery: boolean;
  multiquery_count: number;
  
  use_parent_child: boolean;
  parent_chunk_size: number;
  parent_overlap: number;
  child_chunk_size: number;
  child_overlap: number;
}

// State
const datasets = ref<DatasetFile[]>([]);
const selectedDataset = ref(props.datasetPath);

// Settings State
const settings = ref<Settings>({
  llm_base_url: '',
  llm_model_name: '',
  llm_api_key: '',
  judge_base_url: '',
  judge_model_name: '',
  judge_api_key: ''
});
const settingsLoading = ref(false);
const settingsSaving = ref(false);
const settingsMessage = ref('');
const settingsErrorMsg = ref('');

const configs = ref<Config[]>([
  {
    id: 1,
    name: "Config 1",
    retrieval_method: 'vector',
    top_k: 3,
    use_bm25: false,
    rrf_k: 60,
    vector_weight: 1.0,
    keyword_weight: 1.0,
    
    use_rerank: false,
    initial_top_k: 50,
    
    chunk_size: 512,
    overlap: 64,
    
    use_hyde: false,
    use_multiquery: false,
    multiquery_count: 3,
    
    use_parent_child: false,
    parent_chunk_size: 1024,
    parent_overlap: 128,
    child_chunk_size: 512,
    child_overlap: 64
  },
  {
    id: 2,
    name: "Config 2",
    retrieval_method: 'hybrid',
    top_k: 3,
    use_bm25: true,
    rrf_k: 60,
    vector_weight: 1.0,
    keyword_weight: 1.0,
    
    use_rerank: true,
    initial_top_k: 50,
    
    chunk_size: 512,
    overlap: 64,
    
    use_hyde: false,
    use_multiquery: false,
    multiquery_count: 3,
    
    use_parent_child: false,
    parent_chunk_size: 1024,
    parent_overlap: 128,
    child_chunk_size: 512,
    child_overlap: 64
  }
]);

const loading = ref(false);
const status = ref('');
const rankings = ref<any[]>([]);
const rounds = ref<any[]>([]);
const taskId = ref<string | null>(null);
const pollTimer = ref<any>(null);
const showTaskStartedModal = ref(false);

// Fetch Datasets
const fetchDatasets = async () => {
  try {
    const res = await axios.get(`${API_URL}/api/datasets`);
    datasets.value = res.data;
  } catch (e) {
    console.error(e);
  }
};

// Fetch Settings
const fetchSettings = async () => {
  settingsLoading.value = true;
  try {
    const res = await axios.get(`${API_URL}/api/settings`);
    settings.value = res.data;
  } catch (e) {
    settingsErrorMsg.value = '无法加载设置';
    console.error(e);
  } finally {
    settingsLoading.value = false;
  }
};

const saveSettings = async () => {
  settingsSaving.value = true;
  settingsMessage.value = '';
  settingsErrorMsg.value = '';
  try {
    await axios.post(`${API_URL}/api/settings`, settings.value);
    settingsMessage.value = '设置保存成功';
    // Clear message after 3 seconds
    setTimeout(() => { settingsMessage.value = ''; }, 3000);
  } catch (e) {
    settingsErrorMsg.value = '保存失败';
    console.error(e);
  } finally {
    settingsSaving.value = false;
  }
};

// Watchers
watch(() => props.datasetPath, (newVal) => {
  if (newVal !== selectedDataset.value) {
    selectedDataset.value = newVal;
  }
});

watch(selectedDataset, (newVal) => {
  emit('update:datasetPath', newVal);
});

// Config Management
const addConfig = () => {
  const newId = configs.value.length > 0 ? Math.max(...configs.value.map(c => c.id)) + 1 : 1;
  configs.value.push({
    id: newId,
    name: `Config ${newId}`,
    retrieval_method: 'vector',
    top_k: 3,
    use_bm25: false,
    rrf_k: 60,
    vector_weight: 1.0,
    keyword_weight: 1.0,
    
    use_rerank: false,
    initial_top_k: 50,
    
    chunk_size: 512,
    overlap: 64,
    
    use_hyde: false,
    use_multiquery: false,
    multiquery_count: 3,
    
    use_parent_child: false,
    parent_chunk_size: 1024,
    parent_overlap: 128,
    child_chunk_size: 512,
    child_overlap: 64
  });
};

const removeConfig = (index: number) => {
  configs.value.splice(index, 1);
};

const updateConfigMethod = (config: Config) => {
  if (config.retrieval_method === 'keyword') {
    config.use_bm25 = true; 
  } else if (config.retrieval_method === 'hybrid') {
    config.use_bm25 = true;
  } else {
    config.use_bm25 = false;
  }
};

// Start Evaluation
const startEvaluation = async () => {
  if (!selectedDataset.value) return alert('请选择一个数据集');
  if (configs.value.length < 1) return alert('请至少添加一个配置');

  loading.value = true;
  status.value = '正在启动评测...';
  rankings.value = [];
  rounds.value = [];
  taskId.value = null;

  try {
    // Prepare payload
    const payloadConfigs = configs.value.map(c => ({
      name: c.name,
      chunk_size: c.chunk_size,
      overlap: c.overlap,
      top_k: c.top_k,
      use_bm25: c.retrieval_method === 'hybrid' || c.retrieval_method === 'keyword',
      rrf_k: c.rrf_k,
      vector_weight: c.vector_weight,
      keyword_weight: c.keyword_weight,
      
      use_rerank: c.use_rerank,
      initial_top_k: c.initial_top_k,
      
      use_hyde: c.use_hyde,
      use_multiquery: c.use_multiquery,
      multiquery_count: c.multiquery_count,
      
      use_parent_child: c.use_parent_child,
      parent_chunk_size: c.parent_chunk_size,
      parent_overlap: c.parent_overlap,
      child_chunk_size: c.child_chunk_size,
      child_overlap: c.child_overlap
    }));

    const payload = {
      dataset_path: selectedDataset.value,
      configs: payloadConfigs
    };

    const res = await axios.post(`${API_URL}/api/experiment/run`, payload);
    taskId.value = res.data.task_id;
    
    // Stop loading immediately so user can interact
    loading.value = false;
    showTaskStartedModal.value = true;
    
    // Start background polling for results
    pollStatus();
  } catch (e) {
    console.error(e);
    status.value = '启动评测失败';
    loading.value = false;
  }
};

const closeTaskStartedModal = () => {
  showTaskStartedModal.value = false;
};

const pollStatus = async () => {
  if (!taskId.value) return;
  try {
    const res = await axios.get(`${API_URL}/api/experiment/status/${taskId.value}`);
    const data = res.data;
    
    if (data.status === 'completed') {
      rankings.value = data.result.rankings;
      rounds.value = data.result.rounds;
      loading.value = false;
      status.value = '评测完成！';
      taskId.value = null;
    } else if (data.status === 'failed') {
      status.value = '评测失败: ' + data.error;
      loading.value = false;
      taskId.value = null;
    } else if (data.status === 'cancelled') {
      status.value = '评测已取消';
      loading.value = false;
      taskId.value = null;
    } else {
      status.value = '正在进行瑞士制锦标赛评测...';
      pollTimer.value = setTimeout(pollStatus, 2000);
    }
  } catch (e) {
    console.error("Poll error", e);
    // 如果是 404 错误，说明任务已被删除，停止轮询
    if (e.response && e.response.status === 404) {
      status.value = '任务已取消或删除';
      loading.value = false;
      taskId.value = null;
      return;
    }
    // 其他临时错误继续轮询
    pollTimer.value = setTimeout(pollStatus, 2000);
  }
};

const cancelEvaluation = async () => {
  if (!taskId.value) return;
  try {
    await axios.post(`${API_URL}/api/experiment/cancel/${taskId.value}`);
    status.value = '正在取消...';
  } catch (e) {
    console.error(e);
  }
};

onMounted(() => {
  fetchDatasets();
  fetchSettings();
});
</script>

<template>
  <div class="view-container">
    <div class="header-section">
      <h1>RAG 瑞士制评测</h1>
      <p class="subtitle">多配置锦标赛模式，基于 Elo 等级分自动排名</p>
    </div>

    <!-- Loading Overlay -->
    <div v-if="loading" class="loading-overlay">
      <div class="spinner"></div>
      <p>{{ status }}</p>
      <button v-if="taskId" class="cancel-btn" @click="cancelEvaluation">取消评测</button>
    </div>

    <div class="grid-layout-v2">
      <!-- Top Row: Dataset & Settings Merged -->
      <div class="top-row single-col">
        <div class="card merged-card">
            <div class="card-header-row">
                <h3>1. 基础配置 (数据集 & LLM)</h3>
                <button class="primary-btn small-btn" @click="saveSettings" :disabled="settingsSaving">
                  {{ settingsSaving ? '保存中...' : '保存配置' }}
                </button>
            </div>
            
            <div class="merged-form">
                <!-- Dataset Selection -->
                <div class="field-group full-width-group">
                    <label>选择数据集</label>
                    <select v-model="selectedDataset" class="full-width-select">
                      <option value="" disabled>请选择数据集</option>
                      <option v-for="ds in datasets" :key="ds.name" :value="ds.name">
                        {{ ds.name }} ({{ (ds.size / 1024).toFixed(1) }} KB)
                      </option>
                    </select>
                    <div v-if="datasets.length === 0" class="hint">
                      暂无数据集，请先去“数据集准备”页面生成。
                    </div>
                </div>

                <!-- LLM Settings: 生成答案模型 -->
                 <div class="model-section-label">生成答案模型</div>
                 <div class="form-row-3">
                    <div class="field-group">
                        <label>API Base URL</label>
                        <input v-model="settings.llm_base_url" placeholder="https://api.openai.com/v1" />
                    </div>
                    <div class="field-group">
                        <label>Model Name</label>
                        <input v-model="settings.llm_model_name" placeholder="gpt-4" />
                    </div>
                    <div class="field-group">
                       <label>API Key</label>
                       <input type="password" v-model="settings.llm_api_key" placeholder="sk-..." />
                    </div>
                 </div>

                 <!-- LLM Settings: Judge 评判模型 -->
                 <div class="model-section-label">Judge 评判模型</div>
                 <div class="form-row-3">
                    <div class="field-group">
                        <label>API Base URL</label>
                        <input v-model="settings.judge_base_url" placeholder="https://api.openai.com/v1" />
                    </div>
                    <div class="field-group">
                        <label>Model Name</label>
                        <input v-model="settings.judge_model_name" placeholder="mimo-v2.5-pro" />
                    </div>
                    <div class="field-group">
                       <label>API Key</label>
                       <input type="password" v-model="settings.judge_api_key" placeholder="sk-..." />
                    </div>
                 </div>
                 
                 <div class="msg-row">
                   <span v-if="settingsMessage" class="success-msg">{{ settingsMessage }}</span>
                   <span v-if="settingsErrorMsg" class="error-msg">{{ settingsErrorMsg }}</span>
                </div>
            </div>
        </div>
      </div>

      <!-- Configs Section -->
      <div class="configs-section">
        <div class="configs-header">
          <h3>2. 参赛配置 ({{ configs.length }})</h3>
          <button class="text-btn" @click="addConfig">+ 添加配置</button>
        </div>

        <div class="configs-grid">
          <div v-for="(config, index) in configs" :key="config.id" class="card config-card">
            <div class="card-header-row">
              <input v-model="config.name" class="config-name-input" placeholder="配置名称" />
              <button class="icon-btn" @click="removeConfig(index)" title="删除配置">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
            
            <div class="config-form">
              <div class="form-row-2">
                <div class="field-group">
                  <label>检索方式</label>
                  <select v-model="config.retrieval_method" @change="updateConfigMethod(config)">
                    <option value="vector">纯向量 (Vector)</option>
                    <option value="hybrid">混合检索 (Hybrid)</option>
                  </select>
                </div>
                <div class="field-group">
                  <label>最终 Top K</label>
                  <input type="number" v-model="config.top_k" min="1" max="20" />
                </div>
              </div>

              <!-- Basic Chunking -->
              <div class="form-row-2">
                <div class="field-group" :class="{ disabled: config.use_parent_child }">
                    <label>切片大小 (Chunk Size)</label>
                    <input type="number" v-model="config.chunk_size" step="64" :disabled="config.use_parent_child" />
                </div>
                <div class="field-group" :class="{ disabled: config.use_parent_child }">
                    <label>重叠大小 (Overlap)</label>
                    <input type="number" v-model="config.overlap" step="16" :disabled="config.use_parent_child" />
                </div>
              </div>

              <!-- Hybrid Settings -->
              <div v-if="config.retrieval_method === 'hybrid'" class="sub-settings">
                 <div class="form-row-3">
                    <div class="field-group">
                        <label>向量权重</label>
                        <input type="number" v-model="config.vector_weight" step="0.1" />
                    </div>
                    <div class="field-group">
                        <label>关键词权重</label>
                        <input type="number" v-model="config.keyword_weight" step="0.1" />
                    </div>
                    <div class="field-group">
                        <label>RRF K常数</label>
                        <input type="number" v-model="config.rrf_k" />
                    </div>
                 </div>
              </div>

              <!-- Rerank Settings -->
              <div class="setting-block">
                <div class="field-group checkbox-group">
                    <input type="checkbox" :id="'rerank-'+config.id" v-model="config.use_rerank" />
                    <label :for="'rerank-'+config.id">启用重排序 (Rerank)</label>
                </div>
                <div v-if="config.use_rerank" class="field-group indented">
                    <label>初筛数量 (Initial Top K)</label>
                    <input type="number" v-model="config.initial_top_k" step="10" />
                </div>
              </div>

              <!-- Advanced Settings -->
              <details class="advanced-details">
                  <summary>高级参数 (Query Expansion / Parent-Child)</summary>
                  <div class="advanced-form">
                    
                    <!-- Query Expansion -->
                    <div class="setting-group">
                        <div class="field-group checkbox-group">
                            <input type="checkbox" :id="'hyde-'+config.id" v-model="config.use_hyde" />
                            <label :for="'hyde-'+config.id">启用 HyDE (假设性文档)</label>
                        </div>
                        
                        <div class="field-group checkbox-group">
                            <input type="checkbox" :id="'mq-'+config.id" v-model="config.use_multiquery" />
                            <label :for="'mq-'+config.id">启用多路查询 (Multi-query)</label>
                        </div>
                        <div v-if="config.use_multiquery" class="field-group indented">
                            <label>改写问题数量</label>
                            <input type="number" v-model="config.multiquery_count" min="1" max="10" />
                        </div>
                    </div>
                    
                    <!-- Parent Child -->
                    <div class="setting-group">
                        <div class="field-group checkbox-group">
                            <input type="checkbox" :id="'pc-'+config.id" v-model="config.use_parent_child" />
                            <label :for="'pc-'+config.id">启用父子索引 (Parent-Child)</label>
                        </div>
                        
                        <div v-if="config.use_parent_child" class="pc-settings">
                            <div class="form-row-2">
                                <div class="field-group">
                                    <label>父级切片大小</label>
                                    <input type="number" v-model="config.parent_chunk_size" step="128" />
                                </div>
                                <div class="field-group">
                                    <label>父级重叠</label>
                                    <input type="number" v-model="config.parent_overlap" step="64" />
                                </div>
                            </div>
                            <div class="form-row-2">
                                <div class="field-group">
                                    <label>子级切片大小</label>
                                    <input type="number" v-model="config.child_chunk_size" step="64" />
                                </div>
                                <div class="field-group">
                                    <label>子级重叠</label>
                                    <input type="number" v-model="config.child_overlap" step="32" />
                                </div>
                            </div>
                        </div>
                    </div>

                  </div>
              </details>
            </div>
          </div>
        </div>

        <button class="primary-btn run-btn" @click="startEvaluation" :disabled="loading || !selectedDataset || configs.length === 0">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          开始锦标赛
        </button>

      </div>
    </div>

    <!-- Task Started Modal -->
    <div v-if="showTaskStartedModal" class="modal-overlay" @click="closeTaskStartedModal">
      <div class="modal-content" @click.stop>
        <div class="modal-header centered">
          <h3>🚀 评测任务已启动</h3>
        </div>
        <div class="modal-body centered-body">
          <p>任务已加入后台队列，您可以继续其他操作。</p>
          <p class="sub-text">请在右下角任务队列中查看进度。</p>
          <button class="primary-btn full-width" @click="closeTaskStartedModal">我知道了</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Modal Styles */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(4px);
}

.modal-content {
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(16px);
  padding: 24px;
  border-radius: 16px;
  width: 90%;
  max-width: 400px;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.5);
  animation: modalPop 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.modal-header.centered {
  display: flex;
  justify-content: center;
  margin-bottom: 16px;
}

.modal-header h3 {
  margin: 0;
  font-size: 1.25rem;
  color: #1e293b;
}

.modal-body.centered-body {
  text-align: center;
}

.modal-body p {
  color: #475569;
  margin-bottom: 8px;
}

.modal-body .sub-text {
  font-size: 0.875rem;
  color: #94a3b8;
  margin-bottom: 24px;
}

.primary-btn.full-width {
  width: 100%;
  justify-content: center;
}

@keyframes modalPop {
  from { opacity: 0; transform: scale(0.95) translateY(10px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}

/* Glassmorphism & Linear Style Variables */
/* Disabled state */
.field-group.disabled {
  opacity: 0.5;
  pointer-events: none;
}
.field-group.disabled label {
  color: #94a3b8;
}
input:disabled {
  background-color: rgba(241, 245, 249, 0.5);
  cursor: not-allowed;
  color: #94a3b8;
  border-color: rgba(0,0,0,0.05);
}

.view-container {
  /* Inherits from global, but we ensure content is readable */
}

.grid-layout {
  display: grid;
  grid-template-columns: 100%;
  gap: 32px;
}

.config-column {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.configs-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 20px;
}

/* Grid Layout V2 */
.grid-layout-v2 {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.top-row {
  display: grid;
  grid-template-columns: 1fr;
  gap: 24px;
  align-items: start;
}

.configs-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
}

.full-width-group {
  margin-bottom: 20px;
}

/* Settings Card Styles */
.settings-card {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.card-header-row.compact {
  margin-bottom: 16px;
  padding-bottom: 8px;
}

.compact-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.compact-form .field-group {
  margin-bottom: 0;
}

.model-section-label {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #6366f1;
  margin-bottom: 8px;
  margin-top: 4px;
}

.msg-row {
  min-height: 20px;
  font-size: 12px;
  display: flex;
  align-items: center;
}

.success-msg { color: #10b981; }
.error-msg { color: #ef4444; }

.small-btn {
  padding: 6px 12px;
  font-size: 12px;
}

/* Card Style - Glassmorphism */
.card, .config-card, .rankings-card, .match-card {
  background: rgba(255, 255, 255, 0.65);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.5);
  border-radius: 12px;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02), 0 2px 4px -1px rgba(0, 0, 0, 0.02);
  padding: 24px;
  transition: all 0.3s ease;
}

.config-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -2px rgba(0, 0, 0, 0.025);
  border-color: rgba(255, 255, 255, 0.8);
}

.config-card {
  border-left: none; /* Remove the green bar */
  height: 100%;
  display: flex;
  flex-direction: column;
}

.card-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
}

/* Inputs & Form Elements */
.config-name-input {
  font-weight: 600;
  font-size: 16px;
  border: 1px solid transparent;
  border-radius: 6px;
  padding: 4px 8px;
  width: 70%;
  background: transparent;
  color: #1e293b;
  transition: all 0.2s;
}
.config-name-input:focus {
  background: rgba(255, 255, 255, 0.8);
  border-color: #e2e8f0;
  outline: none;
}
.config-name-input:hover {
  background: rgba(255, 255, 255, 0.5);
}

.field-group label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
  margin-bottom: 6px;
}

.field-group select, .field-group input[type="number"], .field-group input[type="text"] {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.5);
  color: #334155;
  font-size: 13px;
  transition: all 0.2s;
}
.field-group select:focus, .field-group input:focus {
  outline: none;
  border-color: #6366f1; /* Linear Indigo */
  background: #ffffff;
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.1);
}

/* Layout Helpers */
.form-row-2, .form-row-3 {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}
.form-row-2 .field-group, .form-row-3 .field-group {
  flex: 1;
}

/* Buttons */
.icon-btn {
  background: rgba(0, 0, 0, 0.03);
  border: 1px solid transparent;
  color: #64748b;
  cursor: pointer;
  padding: 6px;
  border-radius: 6px;
  transition: all 0.2s;
}
.icon-btn:hover {
  background: #fee2e2;
  color: #ef4444;
}

.text-btn {
  background: none;
  border: 1px solid rgba(99, 102, 241, 0.2);
  color: #6366f1;
  font-weight: 500;
  font-size: 13px;
  padding: 6px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}
.text-btn:hover {
  background: rgba(99, 102, 241, 0.05);
  border-color: rgba(99, 102, 241, 0.4);
}

.primary-btn.run-btn {
  background: #1e293b; /* Dark Slate */
  color: white;
  border: none;
  padding: 12px 24px;
  border-radius: 8px;
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
  width: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
  transition: all 0.2s;
  margin-top: 24px;
}
.primary-btn.run-btn:hover:not(:disabled) {
  background: #0f172a;
  transform: translateY(-1px);
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
}
.primary-btn.run-btn:disabled {
  background: #94a3b8;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.cancel-btn {
  margin-top: 12px;
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
  border: 1px solid rgba(239, 68, 68, 0.2);
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
  font-size: 13px;
  transition: all 0.2s;
}
.cancel-btn:hover {
  background: rgba(239, 68, 68, 0.2);
  border-color: rgba(239, 68, 68, 0.4);
}

/* Advanced Details */
.advanced-details {
  background: rgba(241, 245, 249, 0.5);
  padding: 12px;
  border-radius: 8px;
  margin: 16px 0;
  border: 1px solid rgba(0, 0, 0, 0.05);
}
.advanced-details summary {
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  cursor: pointer;
  user-select: none;
}
.advanced-form {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Checkbox Groups */
.checkbox-group {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 8px;
}
.checkbox-group input {
  width: auto;
  accent-color: #6366f1;
}
.checkbox-group label {
  margin: 0;
  font-weight: 500;
  color: #334155;
  text-transform: none;
  letter-spacing: normal;
}

.indented, .pc-settings {
  margin-left: 24px;
  padding-left: 12px;
  border-left: 2px solid rgba(0, 0, 0, 0.05);
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* Rankings Table */
.rankings-table th {
  text-transform: uppercase;
  font-size: 11px;
  letter-spacing: 0.05em;
  color: #64748b;
  padding: 16px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
}
.rankings-table td {
  padding: 16px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.03);
  color: #334155;
}
.rank-badge {
  font-family: monospace;
  background: #e2e8f0;
  color: #475569;
}
.rank-badge.rank-1 { background: linear-gradient(135deg, #fcd34d, #f59e0b); color: white; box-shadow: 0 2px 4px rgba(245, 158, 11, 0.3); }
.rank-badge.rank-2 { background: linear-gradient(135deg, #e2e8f0, #94a3b8); color: white; }
.rank-badge.rank-3 { background: linear-gradient(135deg, #fdba74, #ea580c); color: white; }

/* Match Cards */
.match-card {
  border: 1px solid rgba(0, 0, 0, 0.05);
  background: rgba(255, 255, 255, 0.4);
}
.round-header {
  color: #1e293b;
  border-bottom: 1px solid rgba(0, 0, 0, 0.1);
}

.win { color: #059669; }
.loss { color: #dc2626; }
.badge.winner { background: rgba(5, 150, 105, 0.1); color: #059669; border: 1px solid rgba(5, 150, 105, 0.2); }
.badge.tie { background: rgba(100, 116, 139, 0.1); color: #64748b; border: 1px solid rgba(100, 116, 139, 0.2); }

/* Scrollbars */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.1);
  border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.2);
}
</style>