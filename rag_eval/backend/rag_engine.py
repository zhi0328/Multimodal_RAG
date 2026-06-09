"""
RAG 检索引擎：支持多种检索策略（HyDE、MultiQuery、Parent-Child、BM25+RRF、Rerank）
适配用户现有的 Milvus + mimo + SiliconFlow embedding 技术栈。
使用 MilvusClient API 与现有项目保持一致。
"""

import os
import re
import time
import logging
import threading
from typing import List, Dict, Any, Optional

import requests
import numpy as np
import jieba
from rank_bm25 import BM25Okapi
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


# ────────────────────── 限速器 ──────────────────────

class RateLimiter:
    """
    固定窗口速率限制器
    用于控制 API 调用频率，避免超出 RPM/TPM 限制
    """
    def __init__(self, rpm_limit: int, name: str = ""):
        self.rpm_limit = rpm_limit
        self.name = name
        self.interval = 60.0 / rpm_limit  # 每次请求的最小间隔（秒）
        self.last_request_time = 0
        self.lock = threading.Lock()

    def acquire(self):
        """获取请求许可，如果需要会阻塞"""
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_request_time
            if elapsed < self.interval:
                sleep_time = self.interval - elapsed
                time.sleep(sleep_time)
            self.last_request_time = time.monotonic()


# 创建全局限速器实例
# Qwen/Qwen3-VL-Embedding-8B: RPM 2,000
embedding_limiter = RateLimiter(rpm_limit=2000, name="Embedding")
# BAAI/bge-reranker-v2-m3: RPM 2,000
rerank_limiter = RateLimiter(rpm_limit=2000, name="Rerank")
# Qwen/Qwen3-8B: RPM 1,000
llm_limiter = RateLimiter(rpm_limit=1000, name="LLM")


def get_embedding(text: str, settings, max_retries: int = 3) -> List[float]:
    """调用 SiliconFlow embedding API（带限速和重试）"""
    # 限速：RPM 2,000
    embedding_limiter.acquire()

    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": settings.embedding_model,
        "input": {"text": text}
    }

    for attempt in range(max_retries):
        try:
            resp = requests.post(
                settings.embedding_api_url,
                headers=headers,
                json=data,
                timeout=60
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 指数退避: 1s, 2s, 4s
                logger.warning(f"Embedding 请求超时，{wait_time}秒后重试 ({attempt+1}/{max_retries})")
                time.sleep(wait_time)
            else:
                raise


def rerank_documents(query: str, documents: List[str], settings, top_n: int = 3, max_retries: int = 3) -> List[str]:
    """调用 SiliconFlow Rerank API（带限速和重试）"""
    try:
        # 限速：RPM 2,000
        rerank_limiter.acquire()

        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": settings.rerank_model,
            "query": query,
            "documents": documents,
            "top_n": top_n,
            "return_documents": True,
        }

        for attempt in range(max_retries):
            try:
                resp = requests.post(
                    settings.rerank_api_url,
                    headers=headers,
                    json=data,
                    timeout=60
                )
                resp.raise_for_status()
                results = resp.json().get("results", [])
                break
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Rerank 请求超时，{wait_time}秒后重试 ({attempt+1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    raise
        sorted_indices = [item["index"] for item in results]
        return [documents[i] for i in sorted_indices]
    except Exception as e:
        logger.warning(f"Rerank 失败: {e}, 使用原始顺序")
        return documents[:top_n]


class ExperimentConfig:
    """RAG 实验配置"""
    def __init__(self, name: str, chunk_size: int = 512, overlap: int = 64,
                 top_k: int = 3, use_bm25: bool = False, rrf_k: int = 60,
                 vector_weight: float = 1.0, keyword_weight: float = 1.0,
                 use_rerank: bool = False, initial_top_k: int = 50,
                 use_hyde: bool = False, use_parent_child: bool = False,
                 parent_chunk_size: int = 1024, parent_overlap: int = 128,
                 child_chunk_size: int = 512, child_overlap: int = 64,
                 use_multiquery: bool = False, multiquery_count: int = 3):
        self.name = name
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.top_k = top_k
        self.use_bm25 = use_bm25
        self.rrf_k = rrf_k
        self.vector_weight = vector_weight
        self.keyword_weight = keyword_weight
        self.use_rerank = use_rerank
        self.initial_top_k = initial_top_k
        self.use_hyde = use_hyde
        self.use_parent_child = use_parent_child
        self.parent_chunk_size = parent_chunk_size
        self.parent_overlap = parent_overlap
        self.child_chunk_size = child_chunk_size
        self.child_overlap = child_overlap
        self.use_multiquery = use_multiquery
        self.multiquery_count = multiquery_count

    def to_dict(self):
        return self.__dict__


class RAGEngine:
    """RAG 检索引擎，支持 Milvus 向量检索 + BM25 + 多种高级策略"""

    # 评测使用的临时集合名称
    EVAL_COLLECTION_NAME = "rag_eval_temp"

    def __init__(self, milvus_client, settings, llm_caller):
        """
        Args:
            milvus_client: pymilvus.MilvusClient 实例
            settings: 全局设置对象
            llm_caller: LLM 调用函数 fn(messages, temperature, max_tokens) -> str
        """
        self.client = milvus_client
        self.settings = settings
        self.llm_caller = llm_caller
        self.bm25_store = None

    def build_index(self, text: str, config: ExperimentConfig, collection_name: str = None,
                    cancel_check=None, skip_if_exists: bool = False) -> dict:
        """构建向量索引 + 可选的 BM25 索引"""
        from pymilvus import DataType, Function, FunctionType

        if collection_name is None:
            collection_name = self.EVAL_COLLECTION_NAME

        # 如果集合已存在
        if self.client.has_collection(collection_name):
            if skip_if_exists:
                stats = self.client.get_collection_stats(collection_name)
                row_count = int(stats.get("row_count", 0))
                if row_count > 0:
                    logger.info(f"集合 {collection_name} 已存在且有 {row_count} 条数据，跳过重建")
                    return {}
            # 删除重建
            self.client.drop_collection(collection_name)

        # 创建集合 schema（与现有项目保持一致）
        schema = self.client.create_schema(auto_id=True, enable_dynamic_field=True)
        schema.add_field("id", DataType.INT64, is_primary=True)
        schema.add_field("text", DataType.VARCHAR, max_length=16000,
                         enable_analyzer=True,
                         analyzer_params={"tokenizer": "jieba", "filter": ["cnalphanumonly"]})
        schema.add_field("parent_text", DataType.VARCHAR, max_length=16000, nullable=True)
        schema.add_field("sparse", DataType.SPARSE_FLOAT_VECTOR)
        schema.add_field("dense", DataType.FLOAT_VECTOR, dim=self.settings.embedding_dim)

        # 添加 BM25 函数（与现有项目一致）
        bm25_function = Function(
            name="text_bm25_emb",
            input_field_names=["text"],
            output_field_names=["sparse"],
            function_type=FunctionType.BM25,
        )
        schema.add_function(bm25_function)

        # 创建索引（与现有项目保持一致）
        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="sparse",
            index_name="sparse_inverted_index",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="BM25",
            params={
                "inverted_index_algo": "DAAT_MAXSCORE",
                "bm25_k1": 1.2,
                "bm25_b": 0.75
            }
        )
        index_params.add_index(
            field_name="dense",
            index_name="dense_inverted_index",
            index_type="AUTOINDEX",
            metric_type="IP"
        )

        self.client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_params
        )

        # 分块
        if config.use_parent_child:
            parent_splitter = RecursiveCharacterTextSplitter(
                chunk_size=config.parent_chunk_size, chunk_overlap=config.parent_overlap)
            child_splitter = RecursiveCharacterTextSplitter(
                chunk_size=config.child_chunk_size, chunk_overlap=config.child_overlap)
            parents = parent_splitter.split_text(text)
            all_texts, all_parent_texts = [], []
            for p in parents:
                children = child_splitter.split_text(p)
                for c in children:
                    all_texts.append(c)
                    all_parent_texts.append(p)
        else:
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=config.chunk_size, chunk_overlap=config.overlap)
            all_texts = splitter.split_text(text)
            all_parent_texts = all_texts.copy()

        # Embedding
        embeddings = []
        for i, text in enumerate(all_texts):
            # 检查取消
            if cancel_check and cancel_check():
                logger.info("构建索引被取消")
                return None

            embedding = get_embedding(text, self.settings)
            embeddings.append(embedding)
            if i % 10 == 0:
                logger.info(f"[进度] 已处理 {i+1}/{len(all_texts)} 个文本块")
            time.sleep(0.1)  # 限速

        # 插入 Milvus
        data = [
            {"text": t, "parent_text": pt, "dense": e}
            for t, pt, e in zip(all_texts, all_parent_texts, embeddings)
        ]
        self.client.insert(collection_name, data)

        # BM25 索引（使用 jieba 中文分词）
        bm25_model = None
        if config.use_bm25:
            tokenized = [list(jieba.cut(doc)) for doc in all_texts]
            bm25_model = BM25Okapi(tokenized)

        self.bm25_store = {"model": bm25_model, "corpus": all_texts, "parent_corpus": all_parent_texts}
        logger.info(f"[索引] 已创建集合 {collection_name}，共 {len(all_texts)} 个文本块")
        return self.bm25_store

    def generate_multiquery(self, question: str, count: int) -> List[str]:
        """生成多个查询变体"""
        prompt = (
            f"你是一个AI助手。请生成 {count} 个不同版本的用户问题，用于从向量数据库中检索相关文档。"
            f"通过生成多个视角的问题，帮助克服距离相似度搜索的局限性。"
            f"每行一个改写后的问题。原始问题：{question}"
        )
        response = self.llm_caller([{"role": "user", "content": prompt}], temperature=0.7, max_tokens=500)
        queries = []
        for line in response.strip().split("\n"):
            line = line.strip()
            if line:
                line = re.sub(r'^\d+\.\s*', '', line)
                queries.append(line)
        return queries[:count]

    def retrieve(self, query: str, config: ExperimentConfig, collection_name: str = None) -> List[Dict[str, Any]]:
        """执行检索"""
        from pymilvus import AnnSearchRequest, WeightedRanker

        if collection_name is None:
            collection_name = self.EVAL_COLLECTION_NAME

        queries = [query]
        if config.use_multiquery:
            try:
                extra = self.generate_multiquery(query, config.multiquery_count)
                queries.extend(extra)
            except Exception as e:
                logger.warning(f"MultiQuery 失败: {e}")

        limit = config.initial_top_k if config.use_rerank else config.top_k * 2
        results = []

        for q_text in queries:
            search_q = q_text

            # HyDE
            if config.use_hyde:
                try:
                    hyde_prompt = f"请写一段简短的文字来回答这个问题：{q_text}"
                    hypothetical = self.llm_caller([{"role": "user", "content": hyde_prompt}], temperature=0.7, max_tokens=300)
                    search_q = hypothetical
                except Exception as e:
                    logger.warning(f"HyDE 失败: {e}")

            # 获取查询嵌入向量
            query_embedding = get_embedding(search_q, self.settings)

            if not config.use_bm25:
                # 纯向量检索
                search_params = {"metric_type": "IP", "params": {"nprobe": 10}}
                search_results = self.client.search(
                    collection_name=collection_name,
                    data=[query_embedding],
                    anns_field="dense",
                    limit=limit,
                    output_fields=["text", "parent_text"],
                    search_params=search_params
                )
                for hit in search_results[0]:
                    text = hit["entity"].get("parent_text") or hit["entity"].get("text")
                    results.append({
                        "text": text,
                        "score": hit["distance"]
                    })
            else:
                # 混合检索（与现有项目保持一致）
                dense_search_params = {"metric_type": "IP", "params": {"nprobe": 10}}
                dense_req = AnnSearchRequest(
                    [query_embedding], "dense", dense_search_params, limit=limit
                )
                sparse_search_params = {"metric_type": "BM25", "params": {"drop_ratio_search": 0.2}}
                sparse_req = AnnSearchRequest(
                    [search_q], "sparse", sparse_search_params, limit=limit
                )

                # 使用 WeightedRanker 进行重排
                rerank = WeightedRanker(config.keyword_weight, config.vector_weight)
                search_results = self.client.hybrid_search(
                    collection_name=collection_name,
                    reqs=[sparse_req, dense_req],
                    ranker=rerank,
                    limit=limit,
                    output_fields=["text", "parent_text"]
                )
                for hit in search_results[0]:
                    text = hit["entity"].get("parent_text") or hit["entity"].get("text")
                    results.append({
                        "text": text,
                        "score": hit["distance"]
                    })

        # 去重并按分数排序
        seen = set()
        unique_results = []
        for r in results:
            if r["text"] not in seen:
                seen.add(r["text"])
                unique_results.append(r)

        unique_results.sort(key=lambda x: x["score"], reverse=True)

        # 提取文本
        texts = [r["text"] for r in unique_results]

        # Rerank
        if config.use_rerank:
            candidates = texts[:config.initial_top_k]
            return rerank_documents(query, candidates, self.settings, config.top_k)
        else:
            return texts[:config.top_k]

    def generate_answer(self, question: str, context: str) -> str:
        """根据上下文生成答案"""
        prompt = f"请根据以下上下文回答问题。\n上下文：{context}\n问题：{question}\n答案："
        return self.llm_caller([{"role": "user", "content": prompt}], temperature=0.7, max_tokens=1024)

    def cleanup(self, collection_name: str = None):
        """清理 Milvus 临时集合"""
        if collection_name is None:
            collection_name = self.EVAL_COLLECTION_NAME
        if self.client.has_collection(collection_name):
            self.client.drop_collection(collection_name)
            logger.info(f"[清理] 已删除临时集合 {collection_name}")
