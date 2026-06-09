<script setup lang="ts">
import { ref, defineProps, defineEmits, computed, onMounted, watch } from 'vue';
import axios from 'axios';

const props = defineProps<{
  modelValue: string // datasetPath
}>();

const emit = defineEmits(['update:modelValue']);

const API_URL = '/api';

// State
const file = ref<File | null>(null);
const numQuestions = ref(5);
const qaPairs = ref<Array<{ question: string, answer: string, context: string }>>([]);
const loading = ref(false);
const status = ref('');
const isDragging = ref(false);
const currentTaskId = ref<string | null>(null);
const generationProgress = ref(0);
const lastFileName = ref<string | null>(null);

const localDatasetPath = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
});

// Persistence Logic
const STORAGE_KEY = 'dataset_view_state';

const saveState = () => {
  const state = {
    numQuestions: numQuestions.value,
    qaPairs: qaPairs.value,
    localDatasetPath: localDatasetPath.value,
    // File object cannot be persisted directly, but we can persist the filename to show user what was last used
    lastFileName: file.value ? file.value.name : lastFileName.value
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
};

const restoreState = () => {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved) {
    try {
      const state = JSON.parse(saved);
      if (state.numQuestions) numQuestions.value = state.numQuestions;
      if (state.qaPairs) qaPairs.value = state.qaPairs;
      if (state.localDatasetPath) emit('update:modelValue', state.localDatasetPath);
      if (state.lastFileName) lastFileName.value = state.lastFileName;
    } catch (e) {
      console.error('Failed to restore state', e);
    }
  }
};

onMounted(() => {
  restoreState();
});

watch([numQuestions, qaPairs, localDatasetPath], () => {
  saveState();
}, { deep: true });

// Methods
const onFileChange = (e: Event) => {
  const target = e.target as HTMLInputElement;
  if (target.files) {
    file.value = target.files[0];
  }
};

const onDrop = (e: DragEvent) => {
  isDragging.value = false;
  if (e.dataTransfer?.files) {
    file.value = e.dataTransfer.files[0];
  }
};

const uploadAndGenerate = async () => {
  if (!file.value) return alert('请选择一个文件');
  
  loading.value = true;
  status.value = '正在上传文件...';
  generationProgress.value = 0;
  
  try {
    const formData = new FormData();
    formData.append('file', file.value);
    await axios.post(`${API_URL}/api/dataset/upload`, formData);
    
    status.value = '正在请求生成任务...';
    const res = await axios.post(`${API_URL}/api/dataset/generate`, { 
      num_questions: numQuestions.value,
      source_filename: file.value.name
    });
    const taskId = res.data.task_id;
    currentTaskId.value = taskId;
    
    // Non-blocking: allow user to continue interaction
    loading.value = false;
    status.value = '任务已提交，请在下方队列查看进度...';
    
    // Poll for result only (to update UI when done)
    const interval = setInterval(async () => {
        try {
            const pollRes = await axios.get(`${API_URL}/api/experiment/status/${taskId}`);
            const task = pollRes.data;
            generationProgress.value = task.progress;
            // status.value = `正在生成: ${task.progress}%`; // Optional: don't overwrite user status if they do other things
            
            if (task.status === 'completed') {
                clearInterval(interval);
                qaPairs.value = task.result.qa_pairs;
                // Capture metadata for saving
                if (task.result.metadata && task.result.metadata.source_file) {
                    lastFileName.value = task.result.metadata.source_file;
                    file.value = null; // Clear file input as we are using the generated one
                }
                status.value = '生成完成';
                currentTaskId.value = null;
            } else if (task.status === 'failed' || task.status === 'cancelled') {
                clearInterval(interval);
                status.value = `生成失败/取消: ${task.error || ''}`;
                loading.value = false;
                currentTaskId.value = null;
            }
        } catch(e) {
            console.error(e);
        }
    }, 1000);
    
  } catch (e) {
    console.error(e);
    status.value = '启动任务失败';
    loading.value = false;
  }
};

const cancelGeneration = async () => {
    if (currentTaskId.value) {
        try {
            await axios.post(`${API_URL}/api/experiment/cancel/${currentTaskId.value}`);
            status.value = "正在取消...";
        } catch (e) {
            alert('取消失败');
        }
    }
};

const showSaveSuccessModal = ref(false);

const saveDataset = async () => {
  loading.value = true;
  try {
    const res = await axios.post(`${API_URL}/api/dataset/save`, { 
      qa_pairs: qaPairs.value,
      filename: localDatasetPath.value,
      metadata: { source_file: file.value?.name || lastFileName.value }
    });
    status.value = `数据集已保存至 ${res.data.path}`;
    showSaveSuccessModal.value = true;
  } catch (e) {
    console.error(e);
    status.value = '保存数据集时出错';
  } finally {
    loading.value = false;
  }
};

// Source File Viewer Logic
const showSourceModal = ref(false);
const sourceContent = ref('');
const sourcePage = ref(1);
const sourceTotalPages = ref(1);
const sourceTotalLines = ref(0);
const sourceLoading = ref(false);

const viewSourceFile = async () => {
    const filename = file.value ? file.value.name : lastFileName.value;
    if (!filename) return alert("没有关联的源文件");
    
    showSourceModal.value = true;
    sourcePage.value = 1;
    await fetchSourceContent();
};

const fetchSourceContent = async () => {
    const filename = file.value ? file.value.name : lastFileName.value;
    if (!filename) return;
    
    sourceLoading.value = true;
    try {
        const res = await axios.get(`${API_URL}/api/file/content`, {
            params: {
                filename: filename,
                page: sourcePage.value,
                page_size: 50 // Show 50 lines per page
            }
        });
        sourceContent.value = res.data.content;
        sourceTotalPages.value = res.data.total_pages;
        sourceTotalLines.value = res.data.total_lines;
        sourcePage.value = res.data.page;
    } catch (e) {
        console.error(e);
        sourceContent.value = "无法加载文件内容 (可能文件已被删除或路径错误)";
    } finally {
        sourceLoading.value = false;
    }
};

const changeSourcePage = (delta: number) => {
    const newPage = sourcePage.value + delta;
    if (newPage >= 1 && newPage <= sourceTotalPages.value) {
        sourcePage.value = newPage;
        fetchSourceContent();
    }
};
</script>

<template>
  <div class="view-container">
    <div class="header-section">
      <h1>数据集准备</h1>
      <p class="subtitle">上传文档自动生成问答对，构建高质量评测集</p>
    </div>

    <!-- Loading Overlay -->
    <!-- Removed blocking overlay as requested -->


    <div class="card upload-card">
      <h3>1. 上传与生成</h3>
      <div class="form-row">
        <!-- File Input -->
        <div 
          class="file-drop-zone" 
          :class="{ dragging: isDragging, 'has-file': file }"
          @dragover.prevent="isDragging = true"
          @dragleave.prevent="isDragging = false"
          @drop.prevent="onDrop"
        >
          <input type="file" id="file" @change="onFileChange" accept=".txt,.md" />
          <label for="file" class="file-label-content">
            <div class="icon-wrapper">
               <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            </div>
            <div class="text-content">
              <span v-if="file" class="filename">{{ file.name }}</span>
              <span v-else class="placeholder">点击或拖拽上传文件 (.txt, .md)</span>
            </div>
          </label>
        </div>
        
        <div class="controls-group">
          <!-- Num Questions (Horizontal) -->
          <div class="input-group-horizontal">
            <label>生成数量</label>
            <input type="number" v-model="numQuestions" min="1" max="50" class="small-input" />
          </div>

          <button class="primary-btn large-btn" @click="uploadAndGenerate" :disabled="loading">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/><path d="M5 3v4"/><path d="M9 3v4"/><path d="M3 9h4"/></svg>
            开始生成
          </button>
        </div>
      </div>
    </div>

    <div v-if="qaPairs.length > 0 || currentTaskId" class="qa-section">
      <div class="section-header">
        <h3>2. 预览与编辑</h3>
        <div class="actions-row">
          <button class="secondary-btn view-source-btn" @click="viewSourceFile" v-if="file || lastFileName">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
            查看源文件
          </button>
          <div class="input-wrapper">
             <input v-model="localDatasetPath" placeholder="输入保存的文件名 (如 dataset.json)" :disabled="!!currentTaskId" />
          </div>
          <button class="primary-btn save-btn" @click="saveDataset" :disabled="!!currentTaskId">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
            保存数据集
          </button>
        </div>
      </div>
      
      <div class="qa-container-wrapper">
        <div v-if="currentTaskId" class="generation-loading-overlay">
           <div class="spinner"></div>
           <p>正在生成问答对... {{ generationProgress }}%</p>
        </div>

        <div class="qa-grid" :class="{ 'content-blurred': currentTaskId }">
          <div v-for="(item, idx) in qaPairs" :key="idx" class="qa-card">
          <div class="qa-header-badge">Q{{ idx + 1 }}</div>
          <div class="qa-body">
            <div class="field-block">
              <label>问题</label>
              <textarea v-model="item.question" rows="3"></textarea>
            </div>
            <div class="field-block">
              <label>参考答案</label>
              <textarea v-model="item.answer" rows="6"></textarea>
            </div>
            <details>
              <summary>查看原文片段</summary>
              <p class="context-text">{{ item.context }}</p>
            </details>
          </div>
        </div>
      </div>
    </div>
  </div>

    <!-- Source File Modal -->
    <div v-if="showSourceModal" class="modal-overlay">
      <div class="modal-content source-modal">
        <div class="modal-header">
          <h3>源文件预览: {{ file ? file.name : lastFileName }}</h3>
          <button class="close-btn" @click="showSourceModal = false">×</button>
        </div>
        <div class="modal-body source-body">
          <div v-if="sourceLoading" class="loading-state">
             <div class="spinner small-spinner"></div> 加载中...
          </div>
          <pre v-else class="source-code">{{ sourceContent }}</pre>
        </div>
        <div class="modal-footer pagination-footer">
          <button :disabled="sourcePage <= 1" @click="changeSourcePage(-1)" class="page-btn">上一页</button>
          <span class="page-info">第 {{ sourcePage }} / {{ sourceTotalPages }} 页 (共 {{ sourceTotalLines }} 行)</span>
          <button :disabled="sourcePage >= sourceTotalPages" @click="changeSourcePage(1)" class="page-btn">下一页</button>
        </div>
      </div>
    </div>

    <!-- Save Success Modal -->
    <div v-if="showSaveSuccessModal" class="modal-overlay">
      <div class="modal-content save-modal">
        <div class="modal-header centered">
          <h3>✅ 保存成功</h3>
        </div>
        <div class="modal-body centered-body">
          <p>数据集已成功保存到本地。</p>
          <p class="sub-text">您可以前往 RAG 评测页面使用该数据集。</p>
          <button class="primary-btn full-width" @click="showSaveSuccessModal = false">确定</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.generation-loading-overlay {
  position: absolute;
  top: 0; left: 0; width: 100%; height: 100%;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.4) 0%, rgba(255, 255, 255, 0.1) 100%);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  z-index: 10;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  gap: 16px;
  border: none;
  box-shadow: none;
}

.view-container {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.file-drop-zone {
  border: 2px dashed rgba(0, 0, 0, 0.1);
  border-radius: 12px;
  padding: 40px;
  text-align: center;
  transition: all 0.2s;
  background: rgba(255, 255, 255, 0.3);
  position: relative;
  cursor: pointer;
}

.file-drop-zone:hover, .file-drop-zone.dragging {
  border-color: #6366f1;
  background: rgba(99, 102, 241, 0.05);
}

.file-drop-zone.has-file {
  border-style: solid;
  border-color: #6366f1;
  background: rgba(99, 102, 241, 0.05);
}

.file-drop-zone input {
  position: absolute;
  top: 0; left: 0; width: 100%; height: 100%;
  opacity: 0;
  cursor: pointer;
}

.file-label-content {
  pointer-events: none;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.icon-wrapper {
  color: #64748b;
  background: white;
  padding: 16px;
  border-radius: 16px;
  box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
  transition: all 0.2s;
}

.file-drop-zone:hover .icon-wrapper {
  transform: translateY(-2px);
  color: #6366f1;
  box-shadow: 0 6px 8px -1px rgba(99, 102, 241, 0.1);
}

.text-content {
  font-size: 15px;
  color: #334155;
  font-weight: 500;
}

.controls-group {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 16px;
}

.input-group-horizontal {
  display: flex;
  align-items: center;
  gap: 12px;
  background: rgba(255, 255, 255, 0.5);
  padding: 8px 16px;
  border-radius: 8px;
  border: 1px solid rgba(0, 0, 0, 0.05);
}

.input-group-horizontal label {
  font-size: 13px;
  color: #64748b;
  margin: 0;
  white-space: nowrap;
  font-weight: 500;
}

.small-input {
  width: 70px;
  padding: 6px 8px;
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 6px;
  text-align: center;
  background: white;
}

.large-btn {
  padding: 12px 24px;
  font-size: 15px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.qa-section {
  margin-top: 40px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.section-header h3 {
  margin: 0;
  font-size: 18px;
  color: #1e293b;
}

.actions-row {
  display: flex;
  gap: 16px;
  align-items: center;
}

.input-wrapper input {
  width: 280px;
  background: white;
}

.save-btn {
  display: flex;
  align-items: center;
  gap: 8px;
}

.qa-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 24px;
}

.qa-card {
  background: rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.5);
  border-radius: 12px;
  padding: 24px;
  position: relative;
  transition: all 0.2s;
}

.qa-card:hover {
  background: rgba(255, 255, 255, 0.8);
  transform: translateY(-2px);
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05);
}

.qa-header-badge {
  position: absolute;
  top: -10px;
  left: 20px;
  background: #6366f1;
  color: white;
  font-size: 12px;
  font-weight: 700;
  padding: 4px 10px;
  border-radius: 20px;
  box-shadow: 0 4px 6px -1px rgba(99, 102, 241, 0.3);
}

.qa-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-top: 8px;
}

.field-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-block label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  color: #64748b;
  letter-spacing: 0.05em;
}

.field-block textarea {
  width: 100%;
  resize: vertical;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 8px;
  padding: 10px;
  font-size: 14px;
  line-height: 1.5;
}

.field-block textarea:focus {
  background: white;
  border-color: #6366f1;
}

details {
  margin-top: 8px;
  font-size: 13px;
  color: #64748b;
}

summary {
  cursor: pointer;
  font-weight: 500;
  margin-bottom: 8px;
  user-select: none;
}

.context-text {
  background: rgba(0, 0, 0, 0.02);
  padding: 12px;
  border-radius: 8px;
  line-height: 1.6;
  margin: 0;
  font-size: 12px;
  color: #475569;
}

.progress-container {
  width: 100%;
  max-width: 300px;
  height: 6px;
  background: rgba(255,255,255,0.3);
  border-radius: 3px;
  margin: 10px 0;
  overflow: hidden;
  border: 1px solid rgba(255,255,255,0.5);
}

.progress-bar {
  height: 100%;
  background: #6366f1;
  transition: width 0.3s ease;
}

.cancel-btn {
  background: rgba(255,255,255,0.2);
  border: 1px solid rgba(255,255,255,0.5);
  padding: 4px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  color: #333;
  margin-top: 10px;
}
.cancel-btn:hover {
  background: rgba(255,255,255,0.4);
}

.qa-container-wrapper {
  position: relative;
  min-height: 200px;
}

/* duplicate removed */

.generation-loading-overlay p {
  color: #6366f1;
  font-weight: 600;
  font-size: 16px;
  text-shadow: 0 2px 4px rgba(255,255,255,0.8);
}

.content-blurred {
  filter: blur(8px);
  pointer-events: none;
  opacity: 0.4;
  transition: all 0.5s ease;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid rgba(99, 102, 241, 0.1);
  border-left-color: #6366f1;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  box-shadow: 0 0 15px rgba(99, 102, 241, 0.2);
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.secondary-btn {
  background: white;
  color: #475569;
  border: 1px solid #cbd5e1;
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 6px;
}

.secondary-btn:hover {
  background: #f8fafc;
  border-color: #94a3b8;
  color: #334155;
}

.view-source-btn {
  height: 40px; /* Match input height roughly */
}

/* Modal Styles */
.modal-overlay {
  position: fixed;
  top: 0; left: 0; width: 100%; height: 100%;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 100;
  backdrop-filter: blur(4px);
}

.modal-content {
  background: white;
  border-radius: 16px;
  width: 90%;
  max-width: 800px;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
  display: flex;
  flex-direction: column;
  max-height: 85vh;
  border: none;
}

.modal-header {
  padding: 20px 24px;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
  color: #1e293b;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  color: #94a3b8;
  cursor: pointer;
}

.close-btn:hover {
  color: #475569;
}

.modal-body.source-body {
  padding: 0;
  overflow: auto;
  flex: 1;
  background: #f8fafc;
  position: relative;
}

.source-code {
  margin: 0;
  padding: 24px;
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
  color: #334155;
  white-space: pre-wrap;
  word-break: break-all;
}

.modal-footer {
  padding: 16px 24px;
  border-top: 1px solid #e2e8f0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: white;
  border-bottom-left-radius: 16px;
  border-bottom-right-radius: 16px;
}

.page-btn {
  padding: 8px 16px;
  border: 1px solid #cbd5e1;
  background: white;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: #475569;
}

.page-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-info {
  font-size: 13px;
  color: #64748b;
  font-variant-numeric: tabular-nums;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: #64748b;
  gap: 12px;
}

.small-spinner {
  width: 24px;
  height: 24px;
  border-width: 2px;
}

/* Save Modal Styles */
.save-modal {
  max-width: 400px;
  padding: 32px;
}

.modal-header.centered {
  justify-content: center;
  border-bottom: none;
  padding-bottom: 0;
  padding-top: 0;
}

.modal-body.centered-body {
  text-align: center;
  padding: 16px 0;
}

.modal-body p {
  margin: 8px 0;
  color: #334155;
}

.sub-text {
  font-size: 13px;
  color: #94a3b8 !important;
  margin-bottom: 24px !important;
}

.full-width {
  width: 100%;
  justify-content: center;
}
</style>
