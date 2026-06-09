"""
批量评估脚本：对测试集中的每个问题跑完整 RAG 流程 + 全部指标，输出评估报告。
使用方法：
    cd 项目根目录
    python evaluate/batch_evaluate.py
"""

import asyncio
import json
import os
import sys
import time
from typing import Dict, List

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ragas.embeddings import LangchainEmbeddingsWrapper

from evaluate.evaluate_self import RAGEvaluator, generate_answer, NoNLLMWrapper
from milvus_db.collections_operator import COLLECTION_NAME, client
from milvus_db.db_retriever import MilvusRetriever
from my_llm import llm, embedding
from utils.log_utils import log


def load_test_dataset(path: str) -> List[Dict]:
    """加载测试数据集，兼容锦标赛格式和 RAGAS 格式"""
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 锦标赛格式: {"qa_pairs": [{"question": ..., "answer": ..., "context": ...}]}
    if isinstance(data, dict) and 'qa_pairs' in data:
        items = data['qa_pairs']
        result = []
        for item in items:
            result.append({
                'question': item['question'],
                'reference': item.get('answer', ''),
                'category': item.get('category', 'default'),
            })
        return result

    # RAGAS 格式: [{"question": ..., "reference": ..., "category": ...}]
    if isinstance(data, list):
        return data

    raise ValueError(f"不支持的数据集格式: {list(data.keys()) if isinstance(data, dict) else type(data)}")


def retrieve_contexts(question: str, retriever: MilvusRetriever) -> List[Dict]:
    """从 Milvus 检索上下文"""
    return retriever.retrieve(question)


async def evaluate_single(
    evaluator: RAGEvaluator,
    question: str,
    contexts: List[Dict],
    reference: str,
) -> Dict[str, float]:
    """对单个问题跑全部指标"""
    # 生成答案
    try:
        response = generate_answer(question, contexts)
    except Exception as e:
        raise RuntimeError(f"答案生成失败: {e}")

    if not response or response.strip() == "":
        raise RuntimeError("答案生成失败: 返回空内容")

    # 跑所有指标
    results = await evaluator.evaluate_all(
        question=question,
        contexts=contexts,
        response=response,
        reference=reference,
    )
    results['generated_answer'] = response
    return results


def get_report_path() -> str:
    """评估报告保存路径：evaluate/evaluation_report.json"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'evaluation_report.json')


def load_existing_report() -> tuple:
    """加载已有评估报告，返回 (已评估的问题集合, 已有结果列表)"""
    report_path = get_report_path()
    if os.path.exists(report_path):
        with open(report_path, 'r', encoding='utf-8') as f:
            results = json.load(f)
        done_questions = {r['question'] for r in results}
        return done_questions, results
    return set(), []


def save_report(results: List[Dict]):
    """保存评估报告到文件"""
    report_path = get_report_path()
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


async def batch_evaluate(test_dataset_path: str, top_k: int = 3):
    """批量评估主函数（支持断点续跑）"""
    # 初始化（使用 NoNLLMWrapper 过滤掉 mimo API 不支持的 n 参数）
    evaluator_llm = NoNLLMWrapper(llm)
    evaluator_embeddings = LangchainEmbeddingsWrapper(embedding)
    evaluator = RAGEvaluator(evaluator_llm, evaluator_embeddings)
    retriever = MilvusRetriever(COLLECTION_NAME, client, top_k=top_k)

    # 加载测试集
    test_data = load_test_dataset(test_dataset_path)
    print(f"加载测试集: {len(test_data)} 个问题")

    # 加载已有结果（断点续跑）
    done_questions, all_results = load_existing_report()
    if done_questions:
        print(f"检测到已有评估结果: {len(done_questions)} 道已完成，跳过这些题目")

    # 逐题评估
    for item in test_data:
        question = item['question']
        reference = item['reference']
        category = item['category']

        # 跳过已评估的题目
        if question in done_questions:
            continue

        print(f"\n[{len(all_results)+1}/{len(test_data)}] 评估: {question[:50]}...")

        # 检索
        contexts = retrieve_contexts(question, retriever)
        if not contexts:
            print(f"  ⚠️ 未检索到上下文，跳过")
            result = {
                'question': question,
                'category': category,
                'error': 'no_context',
            }
            all_results.append(result)
            save_report(all_results)
            continue

        # 评估（带 429 重试）
        max_retries = 3
        for attempt in range(max_retries):
            try:
                start_time = time.time()
                results = await evaluate_single(evaluator, question, contexts, reference)
                elapsed = time.time() - start_time

                results['question'] = question
                results['category'] = category
                results['elapsed_seconds'] = round(elapsed, 1)
                all_results.append(results)

                print(f"  Relevancy={results.get('response_relevancy', 'N/A'):.3f}  "
                      f"Faithfulness={results.get('faithfulness', 'N/A'):.3f}  "
                      f"Precision={results.get('context_precision', 'N/A'):.3f}  "
                      f"Recall={results.get('context_recall', 'N/A')}  "
                      f"CtxRelevance={results.get('context_relevance', 'N/A')}  "
                      f"({elapsed:.1f}s)")

                # 每完成一题立即写入文件
                save_report(all_results)
                break
            except Exception as e:
                if '429' in str(e) and attempt < max_retries - 1:
                    wait = 5 * (attempt + 1)
                    print(f"  ⏳ 限速，等待 {wait}s 后重试 ({attempt+1}/{max_retries})")
                    await asyncio.sleep(wait)
                    continue
                print(f"  ❌ 评估失败: {e}")
                result = {
                    'question': question,
                    'category': category,
                    'error': str(e),
                }
                all_results.append(result)
                save_report(all_results)
                break

        # 每题之间暂停 1 秒（mimo RPM=100，每题 ~15 次调用，间隔 1 秒足够）
        await asyncio.sleep(1)

    # 输出报告
    print_report(all_results)
    print(f"\n详细结果已保存到: {get_report_path()}")


def print_report(results: List[Dict]):
    """打印评估报告"""
    # 过滤掉有错误的结果
    valid = [r for r in results if 'error' not in r]
    errors = [r for r in results if 'error' in r]

    print("\n" + "=" * 60)
    print("RAG 评估报告")
    print("=" * 60)
    print(f"总问题数: {len(results)}")
    print(f"成功评估: {len(valid)}")
    print(f"失败/跳过: {len(errors)}")

    if not valid:
        print("没有有效的评估结果。")
        return

    # 整体指标
    metrics = ['response_relevancy', 'faithfulness', 'context_precision', 'context_recall', 'context_relevance']
    print(f"\n{'指标':<25} {'平均分':<10} {'最低分':<10} {'最高分':<10}")
    print("-" * 55)
    for metric in metrics:
        values = [r[metric] for r in valid if r.get(metric) is not None]
        if values:
            avg = sum(values) / len(values)
            print(f"{metric:<25} {avg:<10.3f} {min(values):<10.3f} {max(values):<10.3f}")

    # 按类别分组
    categories = {}
    for r in valid:
        cat = r.get('category', 'unknown')
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(r)

    print(f"\n按类别统计:")
    print(f"{'类别':<15} {'数量':<6} {'Relevancy':<12} {'Faithfulness':<14} {'Precision':<12} {'Recall':<12} {'CtxRelevance':<14}")
    print("-" * 85)
    for cat, items in categories.items():
        rel_avg = sum(r.get('response_relevancy', 0) for r in items) / len(items)
        faith_avg = sum(r.get('faithfulness', 0) for r in items) / len(items)
        prec_values = [r.get('context_precision', 0) for r in items if r.get('context_precision') is not None]
        prec_avg = sum(prec_values) / len(prec_values) if prec_values else 0
        recall_values = [r.get('context_recall', 0) for r in items if r.get('context_recall') is not None]
        recall_avg = sum(recall_values) / len(recall_values) if recall_values else 0
        crel_values = [r.get('context_relevance', 0) for r in items if r.get('context_relevance') is not None]
        crel_avg = sum(crel_values) / len(crel_values) if crel_values else 0
        print(f"{cat:<15} {len(items):<6} {rel_avg:<12.3f} {faith_avg:<14.3f} {prec_avg:<12.3f} {recall_avg:<12.3f} {crel_avg:<14.3f}")


if __name__ == '__main__':
    # 默认使用锦标赛数据集，也可通过命令行参数指定其他数据集
    if len(sys.argv) > 1:
        dataset_path = sys.argv[1]
    else:
        dataset_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    'rag_eval', 'backend', 'data', 'datasets', 'eval_dataset_100.json')
    asyncio.run(batch_evaluate(dataset_path, top_k=3))
