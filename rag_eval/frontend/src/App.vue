<script setup lang="ts">
import { ref } from 'vue';
import DatasetView from './components/DatasetView.vue';
import EvaluationView from './components/EvaluationView.vue';
import HistoryView from './components/HistoryView.vue';
import TaskQueue from './components/TaskQueue.vue';

const currentTab = ref('dataset');
const datasetPath = ref(''); // 空字符串表示未选择
</script>

<template>
  <div class="app-container">
    <aside class="sidebar">
      <div class="brand">
        <!-- Icon -->
        <div class="logo-icon">
           <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>
        </div>
        <div class="brand-text">
          <h2>Multimodal RAG</h2>
          <p>智能评测助手</p>
        </div>
      </div>
      <nav>
        <button 
          :class="{ active: currentTab === 'dataset' }" 
          @click="currentTab = 'dataset'"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
          数据集准备
        </button>
        <button 
          :class="{ active: currentTab === 'evaluation' }" 
          @click="currentTab = 'evaluation'"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
          RAG 评测
        </button>
        <button 
          :class="{ active: currentTab === 'history' }" 
          @click="currentTab = 'history'"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
          评测历史
        </button>
      </nav>
      <div class="footer-info">
        <p>v1.1.0 | SiliconFlow</p>
      </div>
    </aside>

    <main class="main-content">
      <Transition name="fade" mode="out-in">
        <DatasetView v-if="currentTab === 'dataset'" v-model="datasetPath" />
        <EvaluationView v-else-if="currentTab === 'evaluation'" :datasetPath="datasetPath" @update:datasetPath="val => datasetPath = val" />
        <HistoryView v-else-if="currentTab === 'history'" />
      </Transition>
    </main>

    <TaskQueue />
  </div>
</template>

<style>
/* Global Variables & Reset */
:root {
  /* Linear / Glass Theme Palette */
  --bg-gradient: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
  --sidebar-bg: rgba(255, 255, 255, 0.5);
  --sidebar-border: rgba(255, 255, 255, 0.5);
  
  --primary-color: #0f172a; /* Dark Slate */
  --accent-color: #6366f1; /* Indigo */
  
  --text-main: #1e293b;
  --text-secondary: #64748b;
  --text-light: #94a3b8;
  
  --glass-border: 1px solid rgba(255, 255, 255, 0.6);
  --glass-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
  
  --radius-sm: 6px;
  --radius-md: 12px;
}

body {
  margin: 0;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background: #f1f5f9;
  background-image: 
    radial-gradient(at 0% 0%, rgba(255,255,255,0.9) 0px, transparent 50%),
    radial-gradient(at 100% 0%, rgba(224, 231, 255, 0.5) 0px, transparent 50%),
    radial-gradient(at 100% 100%, rgba(243, 232, 255, 0.5) 0px, transparent 50%),
    radial-gradient(at 0% 100%, rgba(229, 231, 235, 0.5) 0px, transparent 50%);
  background-attachment: fixed;
  background-size: cover;
  color: var(--text-main);
  min-height: 100vh;
}

* {
  box-sizing: border-box;
}

.app-container {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

/* Sidebar */
.sidebar {
  width: 200px;
  background: var(--sidebar-bg);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-right: 1px solid rgba(255, 255, 255, 0.4);
  display: flex;
  flex-direction: column;
  padding: 24px 16px;
  flex-shrink: 0;
  z-index: 10;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 32px;
  padding: 0 12px;
}

.logo-icon {
  width: 36px;
  height: 36px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}

.brand-text h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -0.025em;
  color: #1e293b;
  white-space: nowrap;
}

.brand-text p {
  margin: 0;
  font-size: 12px;
  color: #64748b;
  font-weight: 500;
}

nav {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
}

nav button {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: none;
  background: transparent;
  color: #64748b;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border-radius: 8px;
  transition: all 0.2s ease;
  text-align: left;
}

nav button svg {
  opacity: 0.7;
  transition: all 0.2s;
}

nav button:hover {
  background: rgba(255, 255, 255, 0.6);
  color: #1e293b;
}

nav button.active {
  background: white;
  color: #1e293b;
  font-weight: 600;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.03);
}

nav button.active svg {
  opacity: 1;
  color: #6366f1;
}

.footer-info {
  margin-top: auto;
  padding: 12px;
  border-top: 1px solid rgba(0, 0, 0, 0.05);
}
.footer-info p {
  font-size: 11px;
  color: #94a3b8;
  margin: 0;
  text-align: center;
}

/* Main Content */
.main-content {
  flex: 1;
  overflow-y: auto;
  padding: 32px 40px;
  position: relative;
}

.view-container {
  max-width: 1100px;
  margin: 0 auto;
}

/* Typography & Common Elements */
h1 {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text-main);
  margin: 0 0 6px 0;
}

.subtitle {
  color: var(--text-secondary);
  margin: 0;
  font-size: 14px;
}

.header-section {
  margin-bottom: 32px;
}

/* Global Card Style */
.card {
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-radius: var(--radius-md);
  box-shadow: var(--glass-shadow);
  border: var(--glass-border);
  padding: 24px;
  margin-bottom: 24px;
}

/* Buttons */
.primary-btn {
  background: var(--primary-color);
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: var(--radius-sm);
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
}

.primary-btn:hover {
  background: #0f172a;
  transform: translateY(-1px);
  box-shadow: 0 6px 8px -1px rgba(0, 0, 0, 0.15);
}

.primary-btn:disabled {
  background: #94a3b8;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.secondary-btn {
  background: rgba(255, 255, 255, 0.5);
  color: var(--text-main);
  border: 1px solid rgba(0, 0, 0, 0.1);
  padding: 10px 20px;
  border-radius: var(--radius-sm);
  font-weight: 500;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.secondary-btn:hover {
  background: white;
  border-color: rgba(0, 0, 0, 0.2);
}

/* Form Elements */
input, textarea, select {
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
  font-size: 14px;
  color: var(--text-main);
  transition: all 0.2s;
  outline: none;
  background: rgba(255, 255, 255, 0.6);
}

input:focus, textarea:focus, select:focus {
  border-color: #6366f1;
  background: white;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

/* Transitions */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Loading Overlay */
.loading-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  gap: 16px;
  color: var(--primary-color);
  font-weight: 500;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid rgba(99, 102, 241, 0.1);
  border-left-color: #6366f1;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
