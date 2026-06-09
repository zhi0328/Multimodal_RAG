from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer
from zhipuai import ZhipuAI

from utils.env_utils import GLM_API_KEY, GLM_BASE_URL, SILICONFLOW_API_KEY, SILICONFLOW_BASE_URL, MIMO_API_KEY, MIMO_BASE_URL


multiModal_llm = ChatOpenAI(  # 多模态大模型
    model='mimo-v2.5',
    api_key=MIMO_API_KEY,
    base_url=MIMO_BASE_URL,
)

embedding = OpenAIEmbeddings(
    api_key=SILICONFLOW_API_KEY,
    base_url=SILICONFLOW_BASE_URL,
    model="Qwen/Qwen3-VL-Embedding-8B",
    check_embedding_ctx_length=False  # 关键参数
)

llm = ChatOpenAI(
    model='mimo-v2.5-pro',
    temperature=0.6,
    api_key=MIMO_API_KEY,
    base_url=MIMO_BASE_URL,
    # extra_body={'enable_thinking': True},
)

# SiliconFlow 的 Qwen3-8B（用于 rag_eval 评测系统：生成问答对、锦标赛评判等）
siliconflow_llm = ChatOpenAI(
    model='Qwen/Qwen3-8B',
    temperature=0.7,
    api_key=SILICONFLOW_API_KEY,
    base_url=SILICONFLOW_BASE_URL,
)

zhipuai_client = ZhipuAI(api_key=GLM_API_KEY)

# llm = ChatOpenAI(  # 调用 硅基流动 的deepseek 模型
#     model='deepseek-ai/DeepSeek-V3.2',
#     api_key=SILICONFLOW_API_KEY,
#     base_url=SILICONFLOW_BASE_URL,
# )

# llm = ChatOpenAI(  # 调用 GLM 的 glm-4.7 模型
#     model='glm-4.7',
#     api_key=GLM_API_KEY,
#     base_url=GLM_BASE_URL,
# )


# llm = ChatOpenAI(  # 调用私有化部署的大模型 (全模态的大模型)
#     model='qwen-omni-3b',
#     api_key='xx',
#     base_url=LOCAL_BASE_URL,
# )

# embedding = ChatOpenAI(  # 调用 硅基流动 的embedding 模型
#     model='Qwen/Qwen3-Embedding-8B',
#     api_key=SILICONFLOW_API_KEY,
#     base_url=SILICONFLOW_BASE_URL,
# )










# openai的大模型
# llm = ChatOpenAI(
#     # model='gpt-4o-mini',
#     model='gpt-4o',
#     temperature=0.6,
#     api_key=OPENAI_API_KEY,
#     base_url=OPENAI_BASE_URL,
# )

# embedding = OpenAIEmbeddings(
#     api_key=OPENAI_API_KEY,
#     base_url=OPENAI_BASE_URL,
#     model="text-embedding-3-small",
# )
# print(embedding.embed_query("今天，北京的天气怎么样？"))

#  claude 的大模型调用
# llm = ChatOpenAI(
#     model='claude-3-7-sonnet-20250219',
#     temperature=0.8,
#     api_key=OPENAI_API_KEY,
#     base_url=OPENAI_BASE_URL,
# )

# 官方的deepseek
# llm = ChatOpenAI(
#     model='deepseek-reasoner',
#     # model='deepseek-chat',
#     temperature=0.8,
#     api_key=SILICONFLOW_API_KEY,
#     base_url=SILICONFLOW_BASE_URL,
#     # model_kwargs={ "response_format": { "type": "json_object" } },
# )

# 本地vllm 私有化部署的大模型: 采用--tool-call-parser == hermes
# 流式输出的时候，会有错误
# llm = ChatOpenAI(
#     model='qwen3-8b',
#     temperature=0.8,
#     api_key='xx',
#     base_url=LOCAL_BASE_URL,
#     extra_body={'chat_template_kwargs': {'enable_thinking': True}},
# )

# 本地sglang 本地私有化部署的大模型： 采用--tool-call-parser == qwen25
# llm = ChatOpenAI(
#     model='qwen3-8b',
#     temperature=0.8,
#     api_key='xx',
#     base_url='http://i-2.gpushare.com:42124/v1',
#     extra_body={'chat_template_kwargs': {'enable_thinking': True}},
# )

# llm = ChatOpenAI(
#     model='ds-qwen3-8b',
#     temperature=0.5,
#     api_key='',
#     base_url=LOCAL_BASE_URL,
#     # extra_body={'chat_template_kwargs': {'enable_thinking': True}},
# )

# multiModal_llm = ChatOpenAI(  # 多模态大模型
#     model='qwen-omni-3b',
#     api_key='xx',
#     base_url=LOCAL_BASE_URL,
# )

# llm = ChatOpenAI(
#     model='kimi-k2-0711-preview',
#     temperature=0.6,
#     api_key=K2_API_KEY,
#     base_url=K2_BASE_URL,
#     # extra_body={'enable_thinking': True},
# )

# llm.invoke(input=[{"role": "user", "content": "今天，北京的天气怎么样？"}])

# zhipuai_client = ZhipuAI(api_key=ZHIPU_API_KEY)



class CustomQwen3Embeddings(Embeddings):
    """自定义一个qwen3的Embedding和langchain整合的类"""


    def __init__(self, model_name):
        self.qwen3_embedding = SentenceTransformer(model_name)

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.qwen3_embedding.encode(texts)