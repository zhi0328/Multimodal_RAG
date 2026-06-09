from langchain_core.messages import AIMessage
from ragas.embeddings import LangchainEmbeddingsWrapper
from evaluate.evaluate_self import RAGEvaluator, NoNLLMWrapper
from graph.my_state import MultiModalRAGState
from my_llm import llm, embedding
from utils.log_utils import log

# 使用自定义 NoNLLMWrapper 包装 llm，过滤掉 mimo API 不支持的 n 参数
evaluator_llm = NoNLLMWrapper(llm)
evaluator_embeddings = LangchainEmbeddingsWrapper(embedding)

# 创建RAG评估器
rag_evaluator = RAGEvaluator(evaluator_llm, evaluator_embeddings)

async def evaluate_answer(state: MultiModalRAGState):
    """评估大模型的响应：相关性 + 忠实度，取短板分"""
    context_retrieved = state.get('context_retrieved')
    input_text = state.get('input_text')
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage):
        answer = last_message.content

    # 第一层：答案相关性
    relevancy_score = await rag_evaluator.evaluate_answer(input_text, context_retrieved, answer)
    log.info(f"ResponseRelevancy Score: {relevancy_score}")

    # 第二层：忠实度（幻觉检测）
    faithfulness_score = await rag_evaluator.evaluate_faithfulness(input_text, context_retrieved, answer)
    log.info(f"Faithfulness Score: {faithfulness_score}")

    # 综合分：取短板（答案再相关，有幻觉也不行）
    final_score = min(float(relevancy_score), float(faithfulness_score))
    log.info(f"Final Evaluation Score: {final_score}")

    return {
        "evaluate_score": final_score,
        "faithfulness_score": float(faithfulness_score),
    }