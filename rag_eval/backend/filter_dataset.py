"""
数据集质量筛选工具
从 eval_dataset.json 中筛选出最合理、质量最高的 N 条问答对

使用方法：
    cd rag_eval/backend
    python filter_dataset.py --n 100
"""

import json
import os
import re
import argparse


def load_dataset(filepath: str) -> dict:
    """加载数据集"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_dataset(data: dict, filepath: str):
    """保存数据集"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def calculate_quality_score(qa_pair: dict) -> float:
    """
    计算问答对的质量分数 (0-100)

    评分标准：
    1. 问题质量 (30分)
       - 问题长度适中 (10-100字)
       - 问题清晰，有明确的疑问词
    2. 答案质量 (40分)
       - 答案长度适中 (50-500字)
       - 答案结构清晰
    3. 上下文质量 (30分)
       - 上下文长度适中 (50-500字)
       - 上下文与问题相关
    """
    score = 0

    question = qa_pair.get("question", "")
    answer = qa_pair.get("answer", "")
    context = qa_pair.get("context", "")

    # ========== 问题质量 (30分) ==========

    # 1. 问题长度 (10分)
    q_len = len(question)
    if 10 <= q_len <= 100:
        score += 10
    elif 5 <= q_len <= 150:
        score += 5
    else:
        score += 0

    # 2. 问题清晰度 (10分) - 包含疑问词
    question_words = ["如何", "什么", "为什么", "怎样", "哪些", "怎么", "哪个", "?", "？"]
    if any(w in question for w in question_words):
        score += 10
    elif "?" in question or "？" in question:
        score += 5

    # 3. 问题具体性 (10分) - 包含具体技术术语
    tech_terms = ["Flink", "Java", "Scala", "Kafka", "HBase", "MySQL", "Redis", "Maven",
                  "DataStream", "Sink", "Source", "map", "flatMap", "filter", "keyBy"]
    if any(term in question for term in tech_terms):
        score += 10
    elif len(question) > 15:  # 至少有一定长度
        score += 5

    # ========== 答案质量 (40分) ==========

    # 1. 答案长度 (15分)
    a_len = len(answer)
    if 50 <= a_len <= 500:
        score += 15
    elif 30 <= a_len <= 800:
        score += 10
    elif a_len > 10:
        score += 5

    # 2. 答案结构 (15分) - 包含列表、步骤、代码等
    if re.search(r'\d+\.|\d+、|步骤|第一|第二|首先|然后|最后', answer):
        score += 15
    elif re.search(r'```|代码|实现|配置', answer):
        score += 10
    elif len(answer) > 50:
        score += 5

    # 3. 答案完整性 (10分) - 不是太短也不是太长
    if 100 <= a_len <= 400:
        score += 10
    elif 50 <= a_len <= 600:
        score += 5

    # ========== 上下文质量 (30分) ==========

    # 1. 上下文长度 (10分)
    c_len = len(context)
    if 50 <= c_len <= 500:
        score += 10
    elif 30 <= c_len <= 800:
        score += 5

    # 2. 上下文完整性 (10分) - 包含代码或完整段落
    if re.search(r'```|代码|实现|配置|import|public|class|def', context):
        score += 10
    elif len(context) > 100:
        score += 5

    # 3. 上下文与问题相关性 (10分) - 简单检查关键词重叠
    q_keywords = set(re.findall(r'[一-龥a-zA-Z]+', question))
    c_keywords = set(re.findall(r'[一-龥a-zA-Z]+', context))
    overlap = len(q_keywords & c_keywords)
    if overlap >= 3:
        score += 10
    elif overlap >= 1:
        score += 5

    return score


def filter_dataset(input_path: str, n: int, output_path: str = None):
    """
    策选高质量问答对

    Args:
        input_path: 输入文件路径
        n: 策选数量
        output_path: 输出文件路径
    """
    # 加载数据
    dataset = load_dataset(input_path)
    qa_pairs = dataset.get("qa_pairs", [])

    print(f"原始数据集: {len(qa_pairs)} 条问答对")

    # 计算每条的质量分数
    scored_pairs = []
    for i, qa in enumerate(qa_pairs):
        score = calculate_quality_score(qa)
        scored_pairs.append((score, i, qa))

    # 按分数降序排序
    scored_pairs.sort(key=lambda x: x[0], reverse=True)

    # 选取前 n 条
    selected = scored_pairs[:n]
    selected_pairs = [item[2] for item in selected]

    # 统计分数分布
    scores = [item[0] for item in scored_pairs]
    print(f"质量分数统计:")
    print(f"  最高分: {max(scores)}")
    print(f"  最低分: {min(scores)}")
    print(f"  平均分: {sum(scores)/len(scores):.1f}")
    print(f"  选取分数范围: {selected[-1][0]} - {selected[0][0]}")

    # 生成输出路径
    if output_path is None:
        input_dir = os.path.dirname(input_path)
        output_path = os.path.join(input_dir, "100条.json")

    # 保存
    new_dataset = {
        "qa_pairs": selected_pairs,
        "metadata": {
            "source_file": dataset.get("metadata", {}).get("source_file", "unknown"),
            "total_available": len(qa_pairs),
            "selected_count": n,
            "min_score": selected[-1][0],
            "max_score": selected[0][0],
            "filter_method": "quality_score"
        }
    }

    save_dataset(new_dataset, output_path)

    print(f"\n[完成] 策选完成!")
    print(f"   原始数据: {len(qa_pairs)} 条")
    print(f"   选取数量: {n} 条")
    print(f"   输出文件: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="从数据集中筛选高质量问答对")
    parser.add_argument("--n", type=int, default=100, help="筛选数量（默认100）")
    parser.add_argument("--input", type=str, default="data/datasets/eval_dataset.json",
                        help="输入文件路径（默认：data/datasets/eval_dataset.json）")
    parser.add_argument("--output", type=str, default=None,
                        help="输出文件路径（默认：data/datasets/100条.json）")

    args = parser.parse_args()

    filter_dataset(
        input_path=args.input,
        n=args.n,
        output_path=args.output
    )
