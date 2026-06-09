# RAG 评测平台

独立的 RAG 系统评测平台，支持**自动化数据集生成**、**多配置瑞士制锦标赛对比**和**历史结果管理**。前后端分离架构，后端 FastAPI + 前端 Vue 3。

## 核心功能

- **数据集生成** — 上传文档，自动采样 chunk 并用 LLM 生成高质量问答对
- **瑞士制锦标赛** — 多个 RAG 配置（不同 chunk size、检索策略、模型等）两两对决，LLM 做裁判，Elo 评分排名
- **多种检索策略** — 支持纯向量、BM25 混合检索、HyDE、MultiQuery、Parent-Child、Rerank 等策略组合
- **断点续跑** — 比赛进度自动持久化到 SQLite，中断后恢复继续
- **答案缓存** — 已生成的答案永久保存，重跑时直接复用
- **历史记录** — 每次锦标赛结果存入数据库，支持回溯对比

## 目录结构

```
rag_eval/
├── backend/
│   ├── main.py                 # FastAPI 应用（API + 异步任务系统）
│   ├── rag_engine.py           # RAG 检索引擎（多种检索策略）
│   ├── dataset_generator.py    # LLM 自动生成问答对
│   ├── tournament.py           # 瑞士制锦标赛 + Elo 评分
│   ├── filter_dataset.py       # 数据集过滤工具
│   ├── requirements.txt        # 后端依赖
│   └── data/
│       ├── rageval.db          # SQLite 数据库（锦标赛历史、答案缓存、checkpoint）
│       ├── uploads/            # 上传的源文档
│       └── datasets/           # 生成的问答对数据集
└── frontend/
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── App.vue
        └── components/
            ├── DatasetView.vue     # 数据集管理（上传、生成、编辑、导出）
            ├── EvaluationView.vue  # 锦标赛评测（配置选择、运行、实时进度）
            ├── HistoryView.vue     # 历史记录查看
            └── TaskQueue.vue       # 任务队列状态
```

## 快速开始

### 1. 启动后端

```bash
cd rag_eval/backend
pip install -r requirements.txt
python main.py
```

后端默认运行在 `http://localhost:8006`。

### 2. 启动前端

```bash
cd rag_eval/frontend
npm install
npm run dev
```

前端默认运行在 `http://localhost:5173`。

### 3. 使用流程

```
上传源文档 (.txt/.md)
       ↓
生成问答对数据集（指定数量，LLM 自动生成）
       ↓
编辑 / 筛选问答对（可选）
       ↓
配置实验参数（chunk size、检索策略、模型等）
       ↓
运行瑞士制锦标赛
       ↓
查看 Elo 排名 & 对战详情
```

## 检索策略配置

通过 `ExperimentConfig` 灵活组合：

| 参数 | 类型 | 说明 |
|---|---|---|
| `chunk_size` | int | 文本分块大小（默认 512） |
| `overlap` | int | 分块重叠长度（默认 64） |
| `top_k` | int | 返回的文档数量（默认 3） |
| `use_bm25` | bool | 是否启用 BM25 混合检索 |
| `vector_weight` / `keyword_weight` | float | 混合检索权重 |
| `use_rerank` | bool | 是否启用 Rerank 重排序 |
| `initial_top_k` | int | Rerank 前的候选数量（默认 50） |
| `use_hyde` | bool | 是否启用 HyDE（假设性文档嵌入） |
| `use_multiquery` | bool | 是否启用 MultiQuery（多查询变体） |
| `multiquery_count` | int | MultiQuery 生成的变体数量（默认 3） |
| `use_parent_child` | bool | 是否启用 Parent-Child 分块策略 |
| `parent_chunk_size` / `child_chunk_size` | int | 父/子块大小 |

## 锦标赛机制

### 比赛流程

1. **预生成答案** — 每个 RAG 配置对数据集中所有问题生成答案（支持断点续跑）
2. **瑞士制配对** — 按 Elo 评分相近配对，避免强强过早相遇
3. **LLM 裁判** — 对每对答案从准确性、相关性、检索质量、幻觉检测四个维度评判
4. **Elo 更新** — 根据胜负结果更新 Elo 评分（K=32）
5. **多轮循环** — `log2(N) + 1` 轮，确保排名收敛

### 评判标准

LLM 裁判对比两个系统的回答，输出 JSON：

```json
{"winner": "A", "reason": "系统A的回答更准确且无幻觉"}
```

支持 `A` / `B` / `Tie` 三种结果，兼容中英文输出。

## API 接口

### 设置

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/settings` | 获取全局配置（LLM 模型、API Key 等） |
| `POST` | `/api/settings` | 保存全局配置 |

### 数据集

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/dataset/upload` | 上传源文档（.txt / .md） |
| `GET` | `/api/datasets` | 列出所有数据集 |
| `GET` | `/api/dataset/{name}` | 获取数据集内容 |
| `POST` | `/api/dataset/generate` | 启动生成问答对任务 |
| `POST` | `/api/dataset/save` | 保存编辑后的数据集 |
| `DELETE` | `/api/dataset/{name}` | 删除数据集 |
| `GET` | `/api/file/content` | 分页读取上传的文件内容 |

### 评测

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/experiment/run` | 启动锦标赛 |
| `GET` | `/api/experiment/status/{task_id}` | 查询任务状态和进度 |
| `POST` | `/api/experiment/cancel/{task_id}` | 取消任务 |
| `GET` | `/api/experiment/checkpoint/{dataset}` | 查询是否有未完成的断点 |
| `DELETE` | `/api/experiment/checkpoint/{dataset` | 删除断点（重新开始） |
| `DELETE` | `/api/experiment/collections` | 清理 Milvus 临时集合 |

### 历史 & 任务

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/history/dataset/{name}` | 查看某数据集的历史评测记录 |
| `GET` | `/api/tasks` | 列出所有任务（生成 + 评测） |
| `DELETE` | `/api/task/{task_id}` | 删除任务 |

## 技术栈

| 层 | 技术 |
|---|---|
| 后端框架 | FastAPI + Uvicorn |
| 向量数据库 | Milvus (pymilvus) |
| 数据库 | SQLite（锦标赛历史 + 答案缓存 + checkpoint） |
| LLM 调用 | OpenAI SDK（兼容 SiliconFlow、MiMo 等 OpenAI 协议接口） |
| 文本切分 | LangChain Text Splitters |
| 关键词检索 | jieba + rank-bm25 |
| 前端框架 | Vue 3 + TypeScript |
| UI 组件库 | Element Plus |
| 构建工具 | Vite |

## 环境变量

后端从项目根目录的 `.env` 文件读取配置：

```bash
# 生成答案用的 LLM（默认 Qwen/Qwen3-8B @ SiliconFlow）
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_API_KEY=your_key

# 锦标赛裁判用的 LLM（默认 mimo-v2.5-pro）
MIMO_BASE_URL=https://api.siliconflow.cn/v1
MIMO_API_KEY=your_key

# Milvus 向量数据库
MILVUS_URI=http://localhost:19530
MILVUS_USER=root
MILVUS_PASSWORD=Milvus
```

也可以在前端「设置」页面直接修改，无需重启后端。
