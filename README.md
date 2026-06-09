# Multimodal RAG — 多模态检索增强生成系统

基于 **LangGraph** 构建的多模态 RAG（Retrieval-Augmented Generation）系统，支持 PDF 文档解析、图文混合检索、智能问答、自我评估与人工审批，并附带独立的 RAG 评测平台。

## ✨ 核心特性

- **PDF 多模态解析** — 基于 Dots OCR 将 PDF 转为 Markdown，保留文字与图片
- **混合检索** — Milvus 向量数据库支持密集向量 + 稀疏向量（BM25）混合检索，带加权重排
- **LangGraph 工作流** — 多节点有向图：输入处理 → 意图路由 → 知识库检索 / 历史上下文检索 → 多模态生成 → 自我评估 → 人工审批 → 联网搜索
- **多模型灵活切换** — 支持智谱 GLM、硅基流动、通义、MiniMax、Moonshot、MiMo 等多种 LLM / Embedding 服务
- **上下文记忆** — 对话历史异步写入 Milvus，支持跨会话上下文检索
- **会话状态持久化** — 基于 Redis 的 LangGraph Checkpoint，支持工作流中断恢复
- **RAGAS 自评估** — 在线双重校验（答案相关性 + 忠实度），离线五维评估
- **RAG 评测平台** — 独立的评测系统，支持数据集自动生成、瑞士制锦标赛对比、多维度 RAGAS 指标评估
- **Gradio Web UI** — 提供知识库构建和智能对话两个交互界面

## 🏗️ 项目结构

```
Multimodal_RAG/
├── main.py                     # 知识库构建 Gradio 界面（PDF 上传 → 解析 → 入库）
├── my_llm.py                   # LLM / Embedding 模型统一配置
├── graph/
│   ├── workflow.py             # LangGraph 工作流定义（核心）
│   ├── workflow_gradio.py      # 对话 Gradio 界面
│   ├── my_state.py             # 工作流状态定义
│   ├── tools.py                # 检索工具 & 网络搜索工具
│   ├── search_node.py          # 知识库检索节点
│   ├── evaluate_node.py        # RAGAS 自评估节点
│   ├── save_context.py         # 上下文写入 Milvus
│   ├── redis_checkpointer.py   # Redis Checkpoint（会话状态持久化）
│   ├── all_router.py           # 条件路由逻辑
│   └── print_messages.py       # 消息格式化输出
├── milvus_db/
│   ├── collections_operator.py # Milvus 集合创建与管理
│   ├── db_operator.py          # 文档写入操作
│   └── db_retriever.py         # 混合检索器（密集 + 稀疏 + 重排）
├── dots_ocr/                   # PDF / 图片 OCR 解析模块
├── splitters/
│   └── splitter_md.py          # Markdown 语义切分（含图片提取）
├── utils/                      # 通用工具（日志、环境变量、Embedding 等）
├── evaluate/                   # RAGAS 评测脚本（自评测 + 批量评测）
└── rag_eval/                   # RAG 评测平台（独立子系统）
    ├── backend/                # FastAPI 后端（数据集生成 + 锦标赛 + Web API）
    └── frontend/               # Vue 3 前端
```

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/your-username/Multimodal_RAG.git
cd Multimodal_RAG
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

> **GPU 加速提示**：`sentence-transformers` 依赖 PyTorch。如需 GPU 推理，建议先根据你的 CUDA 版本单独安装 PyTorch，再执行上述命令。

### 3. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的 API 密钥、Milvus 连接信息和 Redis 连接信息。

### 4. 启动 Milvus

项目使用 Milvus 向量数据库。推荐使用 Docker 快速启动：

```bash
docker run -d --name milvus \
  -p 19530:19530 \
  -p 9091:9091 \
  milvusdb/milvus:latest
```

### 5. 启动 Redis

项目使用 Redis 存储会话状态（支持工作流中断恢复）。

```bash
# Windows
D:\redis\redis-server.exe

# Linux / Mac
redis-server
```

> Redis 默认端口 6379，配置详见 `.env` 中的 `REDIS_URL`。

### 6. 运行

#### 知识库构建界面

```bash
python main.py
```

上传 PDF → 解析 → 预览 Markdown → 存入 Milvus 知识库。

#### 智能对话界面

```bash
python graph/workflow_gradio.py
```

启动 Gradio 对话界面，支持文本 + 图片混合输入。

#### 命令行对话

```bash
python graph/workflow.py
```

#### RAG 评测平台

```bash
# 启动后端（默认端口 8006）
cd rag_eval/backend
python main.py

# 启动前端
cd rag_eval/frontend
npm install
npm run dev
```

#### RAGAS 批量评估

```bash
python evaluate/batch_evaluate.py
```

支持断点续跑，评估结果保存至 `evaluate/evaluation_report.json`。

## 🔧 技术栈

| 模块 | 技术 |
|---|---|
| 工作流编排 | LangGraph |
| LLM 框架 | LangChain (langchain-core, langchain-openai) |
| 向量数据库 | Milvus (pymilvus) |
| 会话状态存储 | Redis |
| 文档解析 | Dots OCR, PyMuPDF, Pillow |
| 文本切分 | LangChain Text Splitters, LangChain Experimental (SemanticChunker) |
| 评估框架 | RAGAS |
| Web UI | Gradio |
| 评测平台后端 | FastAPI, Uvicorn |
| 评测平台前端 | Vue 3 + Vite |
| 日志 | Loguru |
| Embedding | DashScope API, Sentence-Transformers |

## 📄 License

本项目仅供学习交流使用。
