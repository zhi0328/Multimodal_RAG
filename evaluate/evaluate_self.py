import os
import asyncio
# 告诉 GitPython 忽略找不到 git 的错误
os.environ["GIT_PYTHON_REFRESH"] = "quiet"


from typing import List, Dict, Optional, Any

from ragas import SingleTurnSample
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import LLMContextPrecisionWithReference, LLMContextPrecisionWithoutReference, ResponseRelevancy, \
    ContextRelevance, Faithfulness, LLMContextRecall


class NoNLLMWrapper(LangchainLLMWrapper):
    """
    自定义 LLM Wrapper：过滤掉 n 参数。
    mimo API 不支持 n 参数，但 RAGAS 的某些指标（如 ResponseRelevancy）会传 n 给 generate()。
    这个 Wrapper 在 agenerate_text 层面拦截：只调底层 LLM 一次（n=1），
    然后把结果复制 n 份，让 generate_multiple 的循环不会越界。
    """

    async def agenerate_text(self, prompt, n: int = 1, temperature=None, stop=None, callbacks=None):
        # 只调底层 LLM 一次，不传 n
        resp = await super().agenerate_text(prompt, n=1, temperature=temperature, stop=stop, callbacks=callbacks)
        # 如果需要多个结果，复制唯一的 generation 来填充
        if n > 1 and resp.generations and len(resp.generations[0]) == 1:
            original = resp.generations[0][0]
            resp.generations[0] = [original] * n
        return resp

from milvus_db.collections_operator import COLLECTION_NAME, client
from milvus_db.db_retriever import MilvusRetriever
from my_llm import llm, embedding
from utils.log_utils import log


def generate_answer(question: str, contexts: List[Dict]) -> str:
    """
    使用LLM基于检索到的上下文生成文本答案

    Args:
        question: 用户问题 (中文)
        contexts: 检索到的上下文列表 (包含text、category等字段)

    Returns:
        生成的中文答案
    """
    # 将检索到的上下文格式化为字符串，便于LLM理解
    # 每个上下文前加上"上下文X"标识，方便LLM区分
    context_str = "\n\n".join([f"上下文 {i + 1}: {context['text']}" for i, context in enumerate(contexts)])

    # 提示词模板 (已翻译成中文)
    prompt = f"""
你是一个AI助手，需要根据提供的上下文回答用户的问题。请确保你的回答基于提供的上下文，不要添加额外信息。

用户问题: {question}

检索到的上下文:
{context_str}

请基于以上上下文回答用户问题。
"""

    # 调用LLM生成答案
    response = llm.invoke(prompt)
    return response.content


class RAGEvaluator:
    """
    RAG的评估类
    """

    def __init__(self, evaluator_llm, evaluator_embeddings):
        self.evaluator_llm = evaluator_llm  # 推理模型
        self.evaluator_embeddings = evaluator_embeddings  # 嵌入模型

    ''' 修改的代码'''
    # 10月18日的代码基础上，修改了一下。
    async def evaluate_context(self, question: str, contexts: List[str]) -> float:
        """上下文相关性评估: 检索到的上下文（块或段落）是否与用户输入相关。"""
        # 0 → 检索到的上下文与用户查询完全不相关。
        # 1 → 上下文部分相关。
        # 2 → 上下文完全相关。
        # SingleTurnSample用于表示单轮对话的评估样本
        sample = SingleTurnSample(
            user_input=question,  # 用户输入的问题
            retrieved_contexts=contexts,  # 检索到的上下文
        )
        scorer = ContextRelevance(llm=self.evaluator_llm)
        return await scorer.single_turn_ascore(sample)


    async def evaluate_answer(self, question: str, contexts: List[Dict], response: str) -> float:
        """评估生成的答案质量"""
        # SingleTurnSample用于表示单轮对话的评估样本
        sample = SingleTurnSample(
            user_input=question,  # 用户输入的问题
            retrieved_contexts=[context['text'] for context in contexts],  # 检索到的上下文
            response=response,  # 生成的答案
        )
        log.info("开始评估答案质量：")
        scorer = ResponseRelevancy(llm=self.evaluator_llm, embeddings=self.evaluator_embeddings)
        return await scorer.single_turn_ascore(sample)

    async def evaluate_faithfulness(self, question: str, contexts: List[Dict], response: str) -> float:
        """
        忠实度评估：答案是否忠于检索到的上下文（检测幻觉）。
        不需要标准答案。分数 0-1，越高越好。
        """
        sample = SingleTurnSample(
            user_input=question,
            retrieved_contexts=[context['text'] for context in contexts],
            response=response,
        )
        scorer = Faithfulness(llm=self.evaluator_llm)
        return await scorer.single_turn_ascore(sample)

    async def evaluate_context_recall(self, question: str, contexts: List[Dict], reference: str) -> float:
        """
        上下文召回率：检索结果覆盖了多少标准答案中的信息。
        需要标准答案（reference）。分数 0-1，越高越好。
        """
        sample = SingleTurnSample(
            user_input=question,
            retrieved_contexts=[context['text'] for context in contexts],
            reference=reference,
        )
        scorer = LLMContextRecall(llm=self.evaluator_llm)
        return await scorer.single_turn_ascore(sample)

    async def evaluate_context_precision(self, question: str, contexts: List[Dict], response: str, reference: str = None) -> float:
        """
        上下文精确度：相关文档是否排在前面。
        有 reference 时用 LLMContextPrecisionWithReference，否则用 WithoutReference。
        分数 0-1，越高越好。
        """
        sample = SingleTurnSample(
            user_input=question,
            retrieved_contexts=[context['text'] for context in contexts],
            response=response,
            reference=reference
        )
        if reference:
            context_precision = LLMContextPrecisionWithReference(llm=self.evaluator_llm)
        else:
            context_precision = LLMContextPrecisionWithoutReference(llm=self.evaluator_llm)
        return await context_precision.single_turn_ascore(sample)

    async def _retry_on_429(self, coro_fn, max_retries=3):
        """带 429 重试的评估调用"""
        for attempt in range(max_retries):
            try:
                return await coro_fn()
            except Exception as e:
                if '429' in str(e) and attempt < max_retries - 1:
                    wait = 5 * (attempt + 1)
                    log.info(f"[429重试] 等待 {wait}s 后重试 ({attempt+1}/{max_retries})")
                    await asyncio.sleep(wait)
                else:
                    raise

    async def evaluate_all(self, question: str, contexts: List[Dict], response: str, reference: str = None) -> Dict[str, float]:
        """
        一次性跑完所有指标，返回字典。
        Faithfulness 和 ResponseRelevancy 不需要 reference；
        ContextRecall 需要 reference，没有则跳过。
        每个指标带 429 自动重试。
        """
        results = {}

        # 1. ContextRelevance（检索相关性，不需要 reference）
        results['context_relevance'] = await self._retry_on_429(
            lambda: self.evaluate_context(question, [c['text'] for c in contexts]))

        # 2. ResponseRelevancy（答案相关性，不需要 reference）
        results['response_relevancy'] = await self._retry_on_429(
            lambda: self.evaluate_answer(question, contexts, response))

        # 3. Faithfulness（忠实度/幻觉检测，不需要 reference）
        results['faithfulness'] = await self._retry_on_429(
            lambda: self.evaluate_faithfulness(question, contexts, response))

        # 4. ContextPrecision（上下文精确度，不需要 reference 也可以跑）
        results['context_precision'] = await self._retry_on_429(
            lambda: self.evaluate_context_precision(question, contexts, response, reference))

        # 5. ContextRecall（上下文召回率，需要 reference）
        if reference:
            results['context_recall'] = await self._retry_on_429(
                lambda: self.evaluate_context_recall(question, contexts, reference))
        else:
            results['context_recall'] = None

        return results


async def main():
    evaluator_llm = LangchainLLMWrapper(llm)
    evaluator_embeddings = LangchainEmbeddingsWrapper(embedding)

    # 创建RAG评估器
    rag_evaluator = RAGEvaluator(evaluator_llm, evaluator_embeddings)

    question = "有界流和无界流有什么区别？"
    # 检索上下文 (从您的Milvus知识库获取)
    m_re = MilvusRetriever(COLLECTION_NAME, client)
    contexts = m_re.retrieve(question)

    generated_answer = generate_answer(question, contexts)
    print(f"生成的答案: {generated_answer}")

    await rag_evaluator.evaluate_metrics(question, contexts, generated_answer)


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())