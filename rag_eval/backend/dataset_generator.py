"""
自动化数据集生成：从文档中随机采样 chunk，用 LLM 生成问答对。
"""

import os
import re
import random
import logging
from typing import List, Dict, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

GENERATION_PROMPT = """请基于以下文本内容，生成一个高质量的问题和对应的答案。

文本内容：
{text}

请严格按照以下格式输出：
Question: <问题>
Answer: <答案>"""


def generate_dataset(
    source_text: str,
    num_questions: int,
    llm_caller,
    source_filename: str = "unknown",
    cancel_check=None,
    progress_callback=None,
) -> Dict:
    """
    从源文本生成问答对数据集。

    Args:
        source_text: 源文档的完整文本
        num_questions: 要生成的问题数量
        llm_caller: LLM 调用函数 fn(messages, temperature, max_tokens) -> str
        source_filename: 源文件名（用于元数据）
        cancel_check: 可选的取消检查函数 fn() -> bool
        progress_callback: 可选的进度回调 fn(progress: int, message: str)

    Returns:
        {"qa_pairs": [...], "metadata": {...}}
    """
    # 分块
    splitter = RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=0)
    chunks = splitter.split_text(source_text)

    if not chunks:
        return {"qa_pairs": [], "metadata": {"source_file": source_filename, "error": "文档为空"}}

    # 随机采样
    actual_count = min(num_questions, len(chunks))
    selected_chunks = random.sample(chunks, actual_count)

    qa_pairs = []
    for i, chunk in enumerate(selected_chunks):
        # 检查取消
        if cancel_check and cancel_check():
            logger.info("数据集生成已取消")
            break

        # 更新进度
        if progress_callback:
            progress = int((i / actual_count) * 100)
            progress_callback(progress, f"正在生成第 {i+1}/{actual_count} 个问答对...")

        try:
            prompt = GENERATION_PROMPT.format(text=chunk)
            response = llm_caller([{"role": "user", "content": prompt}], temperature=0.7, max_tokens=1024)

            # 解析
            question, answer = _parse_qa_response(response)
            if question and answer:
                qa_pairs.append({
                    "question": question,
                    "answer": answer,
                    "context": chunk,
                })
        except Exception as e:
            logger.warning(f"生成第 {i+1} 个问答对失败: {e}")
            continue

    if progress_callback:
        progress_callback(100, f"生成完成，共 {len(qa_pairs)} 个问答对")

    return {
        "qa_pairs": qa_pairs,
        "metadata": {
            "source_file": source_filename,
            "total_chunks": len(chunks),
            "requested": num_questions,
            "generated": len(qa_pairs),
        }
    }


def _parse_qa_response(response: str) -> tuple:
    """解析 LLM 返回的问答对"""
    # 尝试正则匹配
    q_match = re.search(r'Question:\s*(.*?)(?:\n|$)', response, re.IGNORECASE)
    a_match = re.search(r'Answer:\s*(.*)', response, re.IGNORECASE | re.DOTALL)

    if q_match and a_match:
        question = q_match.group(1).strip().strip('<>').strip()
        answer = a_match.group(1).strip().strip('<>').strip()
        return question, answer

    # 备选：按行分割
    lines = [l.strip() for l in response.strip().split('\n') if l.strip()]
    if len(lines) >= 2:
        return lines[0], lines[1]

    return None, None


def load_source_text(filepath: str) -> str:
    """加载源文本文件"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def list_source_files(upload_dir: str) -> List[Dict]:
    """列出上传目录中的所有源文件"""
    files = []
    if not os.path.exists(upload_dir):
        return files
    for name in os.listdir(upload_dir):
        if name.endswith(('.txt', '.md')):
            path = os.path.join(upload_dir, name)
            files.append({
                "name": name,
                "path": path,
                "size": os.path.getsize(path),
                "created_at": os.path.getctime(path),
            })
    files.sort(key=lambda x: x["created_at"], reverse=True)
    return files
