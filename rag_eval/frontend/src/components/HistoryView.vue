<script setup lang="ts">
import { ref, onMounted } from 'vue';
import axios from 'axios';

const API_URL = '/api';

interface DatasetFile {
  name: string;
  path: string;
  size: number;
  created_at: string;
}

interface TournamentRecord {
  id: number;
  dataset_name: string;
  timestamp: string;
  configs: any[];
  rankings: any[];
  rounds: any[];
}

const datasets = ref<DatasetFile[]>([]);
const historyCache = ref<Record<string, TournamentRecord[]>>({});
const expandedDatasets = ref<Set<string>>(new Set());
const loading = ref(false);

// Rename State
const renamingDataset = ref<string | null>(null);
const newDatasetName = ref('');

const fetchDatasets = async () => {
  loading.value = true;
  try {
    const res = await axios.get(`${API_URL}/api/datasets`);
    datasets.value = res.data;
  } catch (e) {
    console.error(e);
  } finally {
    loading.value = false;
  }
};

// Dataset Info Modal Logic
const showInfoModal = ref(false);
const selectedDatasetContent = ref<any[]>([]);
const selectedDatasetName = ref('');

// Match Details Modal Logic
const showMatchModal = ref(false);
const selectedRecord = ref<TournamentRecord | null>(null);

const openMatchDetails = (record: TournamentRecord) => {
  selectedRecord.value = record;
  showMatchModal.value = true;
};

const closeMatchModal = () => {
  showMatchModal.value = false;
  selectedRecord.value = null;
};

const viewDatasetInfo = async (ds: DatasetFile, event: Event) => {
  event.stopPropagation();
  try {
    const res = await axios.get(`${API_URL}/api/dataset/${ds.name}`);
    selectedDatasetContent.value = res.data;
    selectedDatasetName.value = ds.name.replace('.json', '');
    showInfoModal.value = true;
  } catch (e) {
    console.error(e);
    alert('获取数据集详情失败');
  }
};

const closeInfoModal = () => {
  showInfoModal.value = false;
  selectedDatasetContent.value = [];
  selectedDatasetName.value = '';
};

const deleteDataset = async (ds: DatasetFile, event: Event) => {
  event.stopPropagation();
  if (!confirm(`确定要删除数据集 ${ds.name.replace('.json', '')} 吗？此操作无法撤销。`)) return;
  
  try {
    await axios.delete(`${API_URL}/api/dataset/${ds.name}`);
    await fetchDatasets();
    // Clear history cache for this dataset
    if (historyCache.value[ds.name]) {
      delete historyCache.value[ds.name];
    }
  } catch (e) {
    console.error(e);
    alert('删除失败: ' + (e as any).message);
  }
};

const startRename = (ds: DatasetFile, event: Event) => {
  event.stopPropagation(); // Prevent toggling accordion
  renamingDataset.value = ds.name;
  newDatasetName.value = ds.name.replace('.json', '');
};

const cancelRename = () => {
  renamingDataset.value = null;
  newDatasetName.value = '';
};

const confirmRename = async () => {
  if (!renamingDataset.value || !newDatasetName.value) return;
  const currentNameNoExt = renamingDataset.value.replace('.json', '');
  if (currentNameNoExt === newDatasetName.value) {
    cancelRename();
    return;
  }
  
  try {
    await axios.post(`${API_URL}/api/dataset/rename`, {
      old_name: renamingDataset.value,
      new_name: newDatasetName.value
    });
    
    // Update local state or refetch
    await fetchDatasets();
    // Also update history cache keys if needed, but simpler to just clear/reload if accessed
    // For now, just clearing the cache for the old name might be enough, but refetching is safer
    if (historyCache.value[renamingDataset.value]) {
      const data = historyCache.value[renamingDataset.value];
      delete historyCache.value[renamingDataset.value];
      historyCache.value[newDatasetName.value] = data; // Move cache to new name (approx)
    }
    
    cancelRename();
  } catch (e) {
    console.error("Rename failed", e);
    alert("重命名失败: " + (e as any).message);
  }
};

// Config Modal Logic
const showConfigModal = ref(false);
const selectedConfig = ref<any>(null);

const openConfigDetails = (config: any) => {
  selectedConfig.value = config;
  showConfigModal.value = true;
};

const closeConfigModal = () => {
  showConfigModal.value = false;
  selectedConfig.value = null;
};

const toggleDataset = async (datasetName: string) => {
  if (expandedDatasets.value.has(datasetName)) {
    expandedDatasets.value.delete(datasetName);
  } else {
    expandedDatasets.value.add(datasetName);
    if (!historyCache.value[datasetName]) {
      await fetchHistoryForDataset(datasetName);
    }
  }
};

const fetchHistoryForDataset = async (datasetName: string) => {
  try {
    const cleanName = datasetName.replace('.json', '');
    const res = await axios.get(`${API_URL}/api/history/dataset/${cleanName}`);
    historyCache.value[datasetName] = res.data;
  } catch (e) {
    console.error(e);
  }
};

const formatDate = (isoStr: string) => {
  return new Date(isoStr).toLocaleString();
};

onMounted(() => {
  fetchDatasets();
});
</script>

<template>
  <div class="view-container">
    <div class="header-section">
      <h1>评测历史档案</h1>
      <p class="subtitle">以数据集为维度归档所有锦标赛记录</p>
    </div>

    <div v-if="loading && datasets.length === 0" class="loading-overlay">
      <div class="spinner"></div>
    </div>

    <div class="datasets-list">
      <div v-for="ds in datasets" :key="ds.name" class="dataset-block">
        
        <!-- Dataset Header (Clickable) -->
        <div class="dataset-header" @click="toggleDataset(ds.name)">
          <div class="ds-info">
            <span class="ds-icon">📂</span>
            
            <!-- Rename UI -->
            <div v-if="renamingDataset === ds.name" class="rename-container" @click.stop>
              <input v-model="newDatasetName" class="rename-input" @keyup.enter="confirmRename" />
              <button class="icon-btn-success" @click="confirmRename" title="确认">✓</button>
              <button class="icon-btn-cancel" @click="cancelRename" title="取消">✕</button>
            </div>
            
            <div v-else class="ds-name-container">
              <span class="ds-name">{{ ds.name.replace('.json', '') }}</span>
              <button class="rename-trigger-btn" @click="(e) => startRename(ds, e)" title="重命名">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
              </button>
              <button class="action-btn info-btn" @click="(e) => viewDatasetInfo(ds, e)" title="查看详情">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
              </button>
              <button class="action-btn delete-btn" @click="(e) => deleteDataset(ds, e)" title="删除">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
              </button>
            </div>

            <span class="ds-meta">{{ (ds.size / 1024).toFixed(1) }} KB</span>
          </div>
          <div class="ds-action">
             <span v-if="expandedDatasets.has(ds.name)">▼</span>
             <span v-else>▶</span>
          </div>
        </div>

        <!-- Expanded History Content -->
        <div v-if="expandedDatasets.has(ds.name)" class="dataset-history">
          <div v-if="!historyCache[ds.name]" class="loading-history">加载记录中...</div>
          <div v-else-if="historyCache[ds.name].length === 0" class="empty-history">该数据集暂无评测记录</div>
          
          <div v-else class="timeline">
            <div v-for="record in historyCache[ds.name]" :key="record.id" class="timeline-item">
              <div class="timeline-marker"></div>
              <div class="timeline-content card">
                <div class="record-header">
                  <span class="record-time">{{ formatDate(record.timestamp) }}</span>
                  <button class="record-badge btn-details" @click="openMatchDetails(record)">比赛详情</button>
                </div>
                
                <div class="record-body">
                   <div class="configs-tags">
                      <span class="label">参赛选手:</span>
                      <div class="tags-list">
                        <span 
                          v-for="cfg in record.configs" 
                          :key="cfg.name" 
                          class="config-tag clickable"
                          @click="openConfigDetails(cfg)"
                          title="点击查看详情"
                        >
                          {{ cfg.name }}
                        </span>
                      </div>
                   </div>
                   
                   <!-- Mini Ranking Table -->
                   <table class="mini-table">
                     <thead>
                       <tr>
                         <th>排名</th>
                         <th>配置</th>
                         <th>Elo</th>
                         <th>胜率</th>
                       </tr>
                     </thead>
                     <tbody>
                       <tr v-for="p in record.rankings.slice(0, 3)" :key="p.name">
                         <td>#{{ p.rank }}</td>
                         <td class="font-medium">{{ p.name }}</td>
                         <td>{{ Math.round(p.elo) }}</td>
                         <td>{{ p.matches_played ? Math.round((p.wins / p.matches_played)*100) : 0 }}%</td>
                       </tr>
                       <tr v-if="record.rankings.length > 3">
                         <td colspan="4" class="more-row">... 以及其他 {{ record.rankings.length - 3 }} 位选手</td>
                       </tr>
                     </tbody>
                   </table>
                </div>
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>

    <!-- Config Details Modal -->
    <div v-if="showConfigModal" class="modal-overlay" @click="closeConfigModal">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>配置详情: {{ selectedConfig?.name }}</h3>
          <button class="close-btn" @click="closeConfigModal">×</button>
        </div>
        <div class="modal-body">
          <div class="param-grid">
            <div class="param-item" v-for="(value, key) in selectedConfig" :key="key">
              <span class="param-key">{{ key }}</span>
              <span class="param-value">{{ value }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Match Details Modal -->
    <div v-if="showMatchModal" class="modal-overlay" @click="closeMatchModal">
      <div class="modal-content large-modal" @click.stop>
        <div class="modal-header">
          <h3>比赛详情</h3>
          <button class="close-btn" @click="closeMatchModal">×</button>
        </div>
        <div class="modal-body">
          <div v-if="!selectedRecord?.rounds || selectedRecord.rounds.length === 0" class="empty-state">
            暂无比赛详细记录
          </div>
          <div v-else class="rounds-container">
            <div v-for="round in selectedRecord.rounds" :key="round.round" class="round-block">
              <h4 class="round-title">第 {{ round.round }} 轮</h4>
              <div class="matches-list">
                <div v-for="(match, mIdx) in round.matches" :key="mIdx" class="match-card">
                  <div class="match-summary">
                    <div class="player player-a" :class="{ winner: match.winner === 'A' }">
                      <span class="p-name">{{ match.player_a }}</span>
                      <span class="p-score">{{ match.score_a }}胜</span>
                    </div>
                    <div class="vs">VS</div>
                    <div class="player player-b" :class="{ winner: match.winner === 'B' }">
                      <span class="p-score">{{ match.score_b }}胜</span>
                      <span class="p-name">{{ match.player_b }}</span>
                    </div>
                    <div class="match-result">
                      <span v-if="match.winner === 'Tie'" class="badge tie">平局</span>
                      <span v-else class="badge win">{{ match.winner === 'A' ? match.player_a : match.player_b }} 胜</span>
                    </div>
                  </div>
                  
                  <details v-if="match.details && match.details.length > 0" class="match-details">
                    <summary>查看判决详情</summary>
                    <div class="details-list">
                      <div v-for="(detail, dIdx) in match.details" :key="dIdx" class="detail-item">
                        <div class="detail-q"><strong>Q{{ dIdx + 1 }}:</strong> {{ detail.question }}</div>
                        
                        <div class="detail-answers-comparison" v-if="detail.answer_a && detail.answer_b">
                          <div class="ans-box">
                            <span class="ans-label">选手A:</span>
                            <div class="ans-text">{{ detail.answer_a }}</div>
                          </div>
                          <div class="ans-box">
                            <span class="ans-label">选手B:</span>
                            <div class="ans-text">{{ detail.answer_b }}</div>
                          </div>
                        </div>

                        <div class="detail-r">
                           <span class="winner-tag" :class="detail.winner">
                             {{ detail.winner === 'A' ? '选手A胜' : (detail.winner === 'B' ? '选手B胜' : '平局') }}
                           </span>
                           <span class="reason">{{ detail.reason }}</span>
                        </div>
                      </div>
                    </div>
                  </details>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Dataset Info Modal -->
    <div v-if="showInfoModal" class="modal-overlay" @click="closeInfoModal">
      <div class="modal-content info-modal" @click.stop>
        <div class="modal-header">
          <h3>数据集详情: {{ selectedDatasetName }}</h3>
          <button class="close-btn" @click="closeInfoModal">×</button>
        </div>
        <div class="modal-body scrollable">
          <div v-if="selectedDatasetContent.length === 0" class="empty-state">
            暂无数据或数据为空
          </div>
          <div v-else class="qa-list">
            <div v-for="(item, index) in selectedDatasetContent" :key="index" class="qa-item">
              <div class="qa-pair">
                <div class="qa-label">Q:</div>
                <div class="qa-text">{{ item.question }}</div>
              </div>
              <div class="qa-pair">
                <div class="qa-label">A:</div>
                <div class="qa-text">{{ item.answer }}</div>
              </div>
              <div class="qa-context-block" v-if="item.context">
                <div class="qa-label">Context:</div>
                <div class="qa-text context-text">{{ item.context }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Modal Styles */
.modal-overlay {
  position: fixed;
  top: 0; left: 0; width: 100%; height: 100%;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(2px);
}

.modal-content {
  background: white;
  border-radius: 12px;
  width: 90%;
  max-width: 500px;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
  border: none;
  outline: none;
  overflow: hidden;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
}

.modal-content.large-modal {
  max-width: 800px;
}

.modal-content.info-modal {
  max-width: 800px;
}

.modal-header {
  padding: 16px 24px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #f8fafc;
}

.modal-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #334155;
}

.close-btn {
  border: none;
  background: none;
  font-size: 24px;
  color: #94a3b8;
  cursor: pointer;
  line-height: 1;
}

.close-btn:hover { color: #ef4444; }

.modal-body {
  padding: 24px;
  overflow-y: auto;
}

.modal-body.scrollable {
  overflow-y: auto;
}

/* Match Details Styles */
.rounds-container {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.round-block {
  background: #f8fafc;
  border-radius: 8px;
  padding: 16px;
  border: 1px solid rgba(0,0,0,0.05);
}

.round-title {
  margin: 0 0 16px 0;
  font-size: 14px;
  font-weight: 600;
  color: #64748b;
  border-bottom: 1px solid rgba(0,0,0,0.05);
  padding-bottom: 8px;
}

.matches-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.match-card {
  background: white;
  border: 1px solid rgba(0,0,0,0.1);
  border-radius: 8px;
  overflow: hidden;
}

.match-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: white;
}

.player {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  flex: 1;
}

.player.winner .p-name {
  color: #16a34a;
  font-weight: 600;
}

.p-name {
  font-size: 14px;
  color: #334155;
}

.p-score {
  font-size: 18px;
  font-weight: 700;
  color: #64748b;
}

.vs {
  font-size: 12px;
  font-weight: 700;
  color: #94a3b8;
  margin: 0 20px;
}

.match-result .badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.match-result .badge.win {
  background: #dcfce7;
  color: #166534;
}

.match-result .badge.tie {
  background: #f1f5f9;
  color: #64748b;
}

.match-details {
  border-top: 1px solid rgba(0,0,0,0.05);
  background: #fdfdfd;
}

.match-details summary {
  padding: 8px 16px;
  font-size: 12px;
  color: #64748b;
  cursor: pointer;
  background: #fafafa;
}

.details-list {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-item {
  font-size: 13px;
  border-bottom: 1px dashed rgba(0,0,0,0.1);
  padding-bottom: 12px;
}

.detail-item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.detail-q {
  margin-bottom: 6px;
  color: #334155;
  line-height: 1.5;
  font-weight: 500;
}

.detail-answers-comparison {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 8px 0;
  background: rgba(248, 250, 252, 0.5);
  padding: 8px;
  border-radius: 6px;
}

.ans-box {
  display: flex;
  gap: 8px;
  font-size: 12px;
}

.ans-label {
  font-weight: 700;
  color: #64748b;
  min-width: 45px;
  flex-shrink: 0;
}

.ans-text {
  color: #475569;
  line-height: 1.4;
}

.detail-r {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.winner-tag {
  flex-shrink: 0;
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 3px;
  font-weight: 600;
}

.winner-tag.A { background: #dcfce7; color: #166534; }
.winner-tag.B { background: #dcfce7; color: #166534; }
.winner-tag.Tie { background: #f1f5f9; color: #64748b; }

.reason {
  color: #64748b;
  font-style: italic;
  font-size: 12px;
}

/* Existing Dataset Info Styles */
.qa-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.qa-item {
  background: rgba(248, 250, 252, 0.6);
  padding: 16px;
  border-radius: 8px;
  border: 1px solid rgba(0,0,0,0.05);
}

.qa-pair {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.qa-context-block {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed rgba(0,0,0,0.1);
}

.qa-label {
  font-weight: 700;
  color: #64748b;
  width: 24px;
  flex-shrink: 0;
  font-size: 13px;
}

.qa-text {
  color: #334155;
  font-size: 14px;
  line-height: 1.5;
}

.context-text {
  font-size: 12px;
  color: #475569;
  background: rgba(255,255,255,0.5);
  padding: 8px;
  border-radius: 4px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  flex-shrink: 0;
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
  cursor: pointer;
  color: #64748b;
  line-height: 1;
}

.param-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.param-item {
  background: rgba(241, 245, 249, 0.5);
  padding: 8px 12px;
  border-radius: 6px;
  display: flex;
  flex-direction: column;
}

.param-key {
  font-size: 11px;
  text-transform: uppercase;
  color: #64748b;
  margin-bottom: 2px;
  font-weight: 600;
}

.param-value {
  font-size: 13px;
  color: #334155;
  word-break: break-all;
}

.datasets-list {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.dataset-block {
  border: 1px solid rgba(255, 255, 255, 0.5);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.4);
  backdrop-filter: blur(12px);
  overflow: hidden;
  transition: all 0.2s;
}

.dataset-block:hover {
  background: rgba(255, 255, 255, 0.6);
  box-shadow: 0 8px 12px -3px rgba(0, 0, 0, 0.05);
  transform: translateY(-1px);
}

.dataset-header {
  padding: 20px 24px;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.ds-info {
  display: flex;
  align-items: center;
  gap: 16px;
}

.ds-name-container {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rename-trigger-btn, .action-btn {
  background: none;
  border: none;
  color: #94a3b8;
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  opacity: 0;
  transition: all 0.2s;
  border-radius: 4px;
}

.dataset-header:hover .rename-trigger-btn,
.dataset-header:hover .action-btn {
  opacity: 1;
}

.rename-trigger-btn:hover {
  color: #6366f1;
  background: rgba(99, 102, 241, 0.1);
}

.action-btn.info-btn:hover {
  color: #3b82f6;
  background: rgba(59, 130, 246, 0.1);
}

.action-btn.delete-btn:hover {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

.rename-container {
  display: flex;
  align-items: center;
  gap: 6px;
}

.rename-input {
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 15px;
  width: 180px;
  background: white;
  color: #1e293b;
}

.rename-input:focus {
  outline: none;
  border-color: #6366f1;
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.1);
}

.icon-btn-success, .icon-btn-cancel {
  border: none;
  border-radius: 6px;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 14px;
  font-weight: bold;
  transition: all 0.2s;
}

.icon-btn-success { background: #dcfce7; color: #166534; }
.icon-btn-success:hover { background: #bbf7d0; transform: scale(1.05); }
.icon-btn-cancel { background: #fee2e2; color: #dc2626; }
.icon-btn-cancel:hover { background: #fecaca; transform: scale(1.05); }

.ds-icon { font-size: 20px; }
.ds-name { font-weight: 600; font-size: 16px; color: #1e293b; }
.ds-meta { 
  font-size: 12px; 
  color: #64748b; 
  background: rgba(0, 0, 0, 0.05); 
  padding: 4px 8px; 
  border-radius: 6px; 
  font-weight: 500;
}

.ds-action {
  color: #94a3b8;
  font-size: 12px;
}

.dataset-history {
  padding: 24px;
  background: rgba(255, 255, 255, 0.3);
  border-top: 1px solid rgba(0, 0, 0, 0.05);
}

.loading-history, .empty-history {
  text-align: center;
  color: #64748b;
  padding: 20px;
  font-size: 14px;
}

.timeline {
  position: relative;
  padding-left: 20px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.timeline::before {
  content: '';
  position: absolute;
  left: 0;
  top: 10px;
  bottom: 10px;
  width: 2px;
  background: linear-gradient(to bottom, #e2e8f0, rgba(226, 232, 240, 0));
}

.timeline-item {
  position: relative;
  padding-left: 24px;
}

.timeline-marker {
  position: absolute;
  left: -25px; /* Adjust based on padding + line width */
  top: 18px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #6366f1;
  border: 2px solid white;
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2);
}

.timeline-content {
  /* Using global .card style effectively */
  padding: 20px;
}

.record-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  padding-bottom: 12px;
}

.record-time {
  font-size: 14px;
  color: #64748b;
  font-weight: 500;
}

.record-badge {
  background: linear-gradient(135deg, #6366f1, #818cf8);
  color: white;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  box-shadow: 0 2px 4px rgba(99, 102, 241, 0.3);
}

.configs-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 20px;
  align-items: center;
}

.label {
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  margin-right: 4px;
}

.config-tag {
  background: white;
  border: 1px solid rgba(0, 0, 0, 0.05);
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 12px;
  color: #334155;
  font-weight: 500;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.config-tag.clickable {
  cursor: pointer;
  transition: all 0.2s;
}

.config-tag.clickable:hover {
  background: #f8fafc;
  border-color: #cbd5e1;
  color: #0f172a;
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

.mini-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 13px;
}

.mini-table th {
  text-align: left;
  padding: 8px 12px;
  color: #64748b;
  font-weight: 600;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.mini-table td {
  padding: 10px 12px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.03);
  color: #334155;
}

.mini-table tr:last-child td {
  border-bottom: none;
}

.font-medium {
  font-weight: 600;
  color: #1e293b;
}

.more-row {
  text-align: center;
  color: #94a3b8;
  padding: 12px;
  font-style: italic;
  font-size: 12px;
}
</style>