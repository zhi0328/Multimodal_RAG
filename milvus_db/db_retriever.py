import os
from typing import List, Dict, Any

from pymilvus import MilvusClient, AnnSearchRequest, WeightedRanker

from milvus_db.collections_operator import client, COLLECTION_NAME
from utils.embeddings_utils import image_to_base64, call_dashscope_once


class MilvusRetriever:
    def __init__(self, collection_name: str, milvus_client: MilvusClient, top_k: int = 3):
        self.collection_name = collection_name
        self.client: MilvusClient = milvus_client
        self.top_k = top_k

    # 密集向量检索
    def dense_search(self, query_embedding, limit=5):
        """
        密集向量检索
        :param query_embedding: 已经向量后的内容
        :param limit:
        :return:
        """
        search_params = {"metric_type": "IP", "params": {"nprobe": 10}}
        res = self.client.search(
            collection_name=self.collection_name,
            data=[query_embedding],
            anns_field="dense",  # 密集向量中有图片和文本
            limit=limit,
            output_fields=["text", 'category', 'filename', 'image_path', 'title'],
            search_params=search_params,
        )
        return res[0]

    # 稀疏向量检索
    def sparse_search(self, query, limit=5):
        """
        稀疏向量搜索： 全文检索。
        :param query:  搜索的关键词文本
        :param limit:
        :return:
        """
        return self.client.search(
            collection_name=self.collection_name,
            data=[query],
            anns_field="sparse",  # 全文检索： 只能检索文本
            limit=limit,
            output_fields=["text", 'category', 'filename', 'image_path', 'title'],
            search_params={"metric_type": "BM25", "params": {'drop_ratio_search': 0.2}},
        )[0]


    # 混合检索
    def hybrid_search(
            self,
            query_dense_embedding,
            query_sparse_embedding,
            sparse_weight=1.0,
            dense_weight=1.0,
            limit=10,
    ):
        dense_search_params = {"metric_type": "IP", "params": {"nprobe": 10}}
        dense_req = AnnSearchRequest(
            [query_dense_embedding], "dense", dense_search_params, limit=limit
        )
        sparse_search_params = {"metric_type": "BM25", 'params': {'drop_ratio_search': 0.2}}
        sparse_req = AnnSearchRequest(
            [query_sparse_embedding], "sparse", sparse_search_params, limit=limit
        )
        # 重排算法
        rerank = WeightedRanker(sparse_weight, dense_weight)
        return self.client.hybrid_search(
            collection_name=self.collection_name,
            reqs=[sparse_req, dense_req],
            ranker=rerank,  # 重排算法
            limit=limit,
            output_fields=["text", 'category', 'filename', 'image_path', 'title']
        )[0]

    def hybrid_search2(
            self,
            query_dense_embedding,
            query_sparse_embedding,
            sparse_weight=1.0,
            dense_weight=1.0,
            limit=10,
    ):
        dense_search_params = {"metric_type": "IP", "params": {"nprobe": 10}}
        dense_req = AnnSearchRequest(
            [query_dense_embedding], "dense", dense_search_params, limit=limit
        )
        sparse_search_params = {"metric_type": "BM25", 'params': {'drop_ratio_search': 0.2}}
        sparse_req = AnnSearchRequest(
            [query_sparse_embedding], "sparse", sparse_search_params, limit=limit
        )

        # search1 = [sparse_req, dense_req]
        # search2 = AnnSearchRequest(
        #     [query_dense_embedding], "dense", dense_search_params, limit=limit
        # )
        # 重排算法
        rerank = WeightedRanker(sparse_weight, dense_weight)
        return self.client.hybrid_search(
            collection_name=self.collection_name,
            reqs=[sparse_req, dense_req],
            ranker=rerank,  # 重排算法
            limit=limit,
            output_fields=["text", 'category', 'filename', 'image_path', 'title']
        )[0]


    def retrieve(self, query: str) -> List[Dict[str, Any]]:
        """
        正式开始搜索
        :param query: 可能是图片（路径）, 也可能是文本
        :return:

        稀疏向量本质上是一种全文检索，通过倒排索引来检索

        图片是不存在做全文检索，即没办法用稀疏向量，故后面提到图片不能做混合检索
        """
        if os.path.isfile(query):
            # 构建图像输入数据
            input_data = [{'image': image_to_base64(query)[0]}]
            # 调用API获取图像嵌入向量
            ok, embedding, status, retry_after = call_dashscope_once(input_data)
        else:
            # 构建文本输入数据
            input_data = [{'text': query}]
            # 调用API获取嵌入向量
            ok, embedding, status, retry_after = call_dashscope_once(input_data)

        if ok:
            if os.path.isfile(query):  # 纯图片不能用混合检索
                results = self.dense_search(embedding, limit=self.top_k)
            else:
                results = self.hybrid_search(embedding, query, limit=self.top_k)
                # results = self.dense_search(embedding, limit=self.top_k)
        # 返回文档内容
        # return results

        docs = []
        # print(results)
        for hit in results:
            docs.append({"text": hit.get("text"), "category": hit.get("category"), "image_path": hit.get("image_path"),
                         "filename": hit.get("filename"), })

        return docs


if __name__ == '__main__':
    m_re = MilvusRetriever(collection_name=COLLECTION_NAME, milvus_client=client)
    docs = m_re.retrieve("有界流和无界流")  # 输入的是文本 Any-To-Any
    # docs = m_re.retrieve(r"D:\项目视频\大模型\6.大模型直播课（二期）\my_code\Multimodal_RAG\milvus_db\搜索测试.png")
    for d in docs:
        print(d)