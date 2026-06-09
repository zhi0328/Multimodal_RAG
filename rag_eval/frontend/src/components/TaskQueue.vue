<template>
  <div class="task-queue-container" v-if="tasks.length > 0">
    <div class="queue-header" @click="collapsed = !collapsed">
      <h3>任务队列 ({{ activeTasks.length }} 进行中)</h3>
      <span class="toggle-icon">{{ collapsed ? '▲' : '▼' }}</span>
    </div>
    
    <div class="queue-body" v-if="!collapsed">
      <div v-for="task in tasks" :key="task.id" class="task-item">
        <div class="task-info">
          <div class="task-name" :title="task.name">{{ task.name }}</div>
          <div class="task-status" :class="task.status">{{ formatStatus(task.status) }}</div>
        </div>
        
        <div class="progress-bar-container" v-if="task.status === 'running' || task.status === 'pending'">
          <div class="progress-bar" :style="{ width: task.progress + '%' }"></div>
        </div>
        
        <div class="task-message">{{ task.message }}</div>
        
        <div class="task-actions">
          <button v-if="task.status === 'running' || task.status === 'pending'" @click="cancelTask(task.id)" class="btn-cancel">取消</button>
          <button @click="deleteTask(task.id)" class="btn-delete">删除记录</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue';
import axios from 'axios';

const API_URL = '/api';
const tasks = ref([]);
const collapsed = ref(false);
let pollInterval = null;

const activeTasks = computed(() => {
  return tasks.value.filter(t => ['running', 'pending'].includes(t.status));
});

const fetchTasks = async () => {
  try {
    const res = await axios.get(`${API_URL}/api/tasks`);
    tasks.value = res.data;
  } catch (e) {
    console.error("Failed to fetch tasks", e);
  }
};

const formatStatus = (status) => {
  const map = {
    'pending': '等待中',
    'running': '进行中',
    'completed': '已完成',
    'failed': '失败',
    'cancelled': '已取消'
  };
  return map[status] || status;
};

const cancelTask = async (taskId) => {
  if (!confirm('确定要取消这个任务吗？')) return;
  try {
    await axios.post(`${API_URL}/api/experiment/cancel/${taskId}`);
    fetchTasks();
  } catch (e) {
    alert('取消失败');
  }
};

const deleteTask = async (taskId) => {
  try {
    await axios.delete(`${API_URL}/api/task/${taskId}`);
    fetchTasks();
  } catch (e) {
    alert('删除失败');
  }
};

onMounted(() => {
  fetchTasks();
  pollInterval = setInterval(fetchTasks, 2000);
});

onUnmounted(() => {
  if (pollInterval) clearInterval(pollInterval);
});
</script>

<style scoped>
.task-queue-container {
  position: fixed;
  bottom: 20px;
  right: 20px;
  width: 350px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  border: 1px solid #eee;
  z-index: 1000;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
}

.queue-header {
  padding: 12px 16px;
  background: #f8f9fa;
  border-bottom: 1px solid #eee;
  border-radius: 8px 8px 0 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
}

.queue-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}

.queue-body {
  overflow-y: auto;
  padding: 10px;
}

.task-item {
  padding: 10px;
  border-bottom: 1px solid #f0f0f0;
}

.task-item:last-child {
  border-bottom: none;
}

.task-info {
  display: flex;
  justify-content: space-between;
  margin-bottom: 5px;
}

.task-name {
  font-weight: 500;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
}

.task-status {
  font-size: 12px;
  padding: 2px 6px;
  border-radius: 4px;
}

.task-status.running { background: #e6f7ff; color: #1890ff; }
.task-status.completed { background: #f6ffed; color: #52c41a; }
.task-status.failed { background: #fff1f0; color: #f5222d; }
.task-status.cancelled { background: #f5f5f5; color: #d9d9d9; }

.progress-bar-container {
  height: 4px;
  background: #f0f0f0;
  border-radius: 2px;
  margin: 8px 0;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: #1890ff;
  transition: width 0.3s ease;
}

.task-message {
  font-size: 11px;
  color: #888;
  margin-bottom: 8px;
}

.task-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

button {
  font-size: 11px;
  padding: 2px 8px;
  border: 1px solid #d9d9d9;
  background: white;
  border-radius: 4px;
  cursor: pointer;
}

.btn-cancel { color: #faad14; border-color: #faad14; }
.btn-delete { color: #ff4d4f; border-color: #ff4d4f; }

button:hover { opacity: 0.8; }
</style>
