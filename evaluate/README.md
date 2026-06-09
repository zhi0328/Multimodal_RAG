# RAG 评估模块

基于 [RAGAS](https://github.com/explodinggradients/ragas) 框架的 RAG 系统质量评估模块，支持单条评测和批量评测（含断点续跑）。

## 文件说明

| 文件 | 用途 |
|------|------|
| `evaluate_self.py` | `RAGEvaluator` 类，封装 5 个 RAGAS 评估指标，支持一键全量评估 |
| `batch_evaluate.py` | 批量评估脚本，对测试集逐题执行检索 → 生成 → 评估，输出 JSON 报告 |
| `evaluation_report.json` | 最近一次批量评估的详细结果（自动生成） |

## 5 个评估指标

| 指标 | 需要标准答案？ | 评估维度 | 分数范围 |
|------|:---:|---|:---:|
| **ResponseRelevancy** | 否 | 生成的答案是否回答了用户的问题 | 0~1 |
| **Faithfulness** | 否 | 答案是否忠于检索到的上下文（幻觉检测） | 0~1 |
| **ContextPrecision** | 否 | 检索排序质量 — 相关文档是否排在前面 | 0~1 |
| **ContextRecall** | 是 | 检索覆盖度 — 标准答案的信息被覆盖了多少 | 0~1 |
| **ContextRelevance** | 否 | 检索到的上下文是否与用户问题相关 | 0~1 |

## 使用方法

### 单条评测

```python
from evaluate.evaluate_self import RAGEvaluator, generate_answer
from milvus_db.collections_operator import COLLECTION_NAME, client
from milvus_db.db_retriever import MilvusRetriever
from my_llm import llm, embedding
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper

evaluator = RAGEvaluator(
    LangchainLLMWrapper(llm),
    LangchainEmbeddingsWrapper(embedding),
)

# 从 Milvus 检索
retriever = MilvusRetriever(COLLECTION_NAME, client)
question = "有界流和无界流有什么区别？"
contexts = retriever.retrieve(question)

# 生成答案
answer = generate_answer(question, contexts)

# 一次性跑全部指标
import asyncio
results = asyncio.run(evaluator.evaluate_all(question, contexts, answer))
print(results)
```

### 批量评测

```bash
# 在项目根目录执行
python evaluate/batch_evaluate.py [测试集路径]
```

- 不指定路径时，默认使用 `rag_eval/backend/data/datasets/eval_dataset_100.json`
- 支持两种测试集格式：RAGAS 格式（`[{question, reference, category}]`）和锦标赛格式（`{qa_pairs: [...]}`）
- **断点续跑**：已评估的题目会自动跳过，中断后重新运行即可继续
- 评估报告实时写入 `evaluate/evaluation_report.json`

## 测试集格式

### RAGAS 格式

```json
[
  {
    "question": "Flink 中的 Checkpoint 机制是什么？",
    "reference": "Checkpoint 是 Flink 实现容错的核心机制...",
    "category": "概念解释"
  }
]
```

### 锦标赛格式（兼容 rag_eval 生成的数据集）

```json
{
  "qa_pairs": [
    {
      "question": "Flink 中的 Checkpoint 机制是什么？",
      "answer": "Checkpoint 是 Flink 实现容错的核心机制...",
      "category": "概念解释"
    }
  ]
}
```

## 关键配置

| 配置项 | 值 | 说明 |
|---|---|---|
| 推理 LLM | `mimo-v2.5-pro` | 评估用的大语言模型 |
| Embedding | `Qwen/Qwen3-VL-Embedding-8B` | SiliconFlow 提供的向量模型 |
| API 限速 | RPM=100 | 评估指标遇 HTTP 429 自动重试（最多 3 次，指数退避） |
| 批量评测间隔 | 1 秒/题 | 每题约 15 次 API 调用，间隔 1 秒足够 |

## 评估流程

```
测试集 ──→ 逐题检索 Milvus 知识库 ──→ LLM 生成答案 ──→ RAGAS 5 指标评估 ──→ 写入报告
                                              ↑                                    |
                                              └──── 断点续跑：跳过已完成的题目 ←────┘
```

## 报告示例

`evaluation_report.json` 中每条记录包含：

```json
{
  "question": "有界流和无界流有什么区别？",
  "category": "概念解释",
  "response_relevancy": 0.872,
  "faithfulness": 0.915,
  "context_precision": 0.833,
  "context_recall": 0.750,
  "context_relevance": 0.667,
  "generated_answer": "有界流（Bounded Stream）是指...",
  "elapsed_seconds": 12.3
}
```

批量评估完成后会打印汇总报告，包含整体均值/极值和按类别的分组统计。
