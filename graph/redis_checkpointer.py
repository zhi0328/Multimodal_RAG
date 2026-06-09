"""
基于普通 Redis 命令的 Checkpointer（不需要 RedisJSON 模块）
使用 JSON 序列化存储 checkpoint 数据
"""
import asyncio
import json
from typing import Any, AsyncIterator, Iterator, Optional, Sequence
from functools import partial

import redis
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    ChannelVersions,
)
from langchain_core.runnables import RunnableConfig


class SimpleRedisSaver(BaseCheckpointSaver):
    """使用普通 Redis 命令存储 checkpoint（不需要 RedisJSON）"""

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        super().__init__()
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        self.prefix = "lg:checkpoint:"

    def _make_key(self, thread_id: str, checkpoint_ns: str = "", checkpoint_id: str = "") -> str:
        if checkpoint_id:
            return f"{self.prefix}{thread_id}:{checkpoint_ns}:{checkpoint_id}"
        return f"{self.prefix}{thread_id}:{checkpoint_ns}:latest"

    def _make_writes_key(self, thread_id: str, checkpoint_ns: str = "", checkpoint_id: str = "") -> str:
        return f"{self.prefix}writes:{thread_id}:{checkpoint_ns}:{checkpoint_id}"

    def _to_json(self, obj: Any, _depth: int = 0) -> Any:
        """递归转换为 JSON 可序列化对象"""
        if _depth > 30:
            return None
        if obj is None or isinstance(obj, (bool, int, float, str)):
            return obj
        if callable(obj):
            return None
        if isinstance(obj, dict):
            return {str(k): self._to_json(v, _depth + 1) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._to_json(item, _depth + 1) for item in obj]
        if isinstance(obj, set):
            return [self._to_json(item, _depth + 1) for item in obj]
        if isinstance(obj, bytes):
            try:
                return obj.decode('utf-8')
            except Exception:
                return None
        # 自定义对象（LangChain Message 等）
        if hasattr(obj, '__dict__'):
            return {str(k): self._to_json(v, _depth + 1) for k, v in obj.__dict__.items()}
        # 兜底
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)

    def _serialize(self, data: Any) -> str:
        return json.dumps(self._to_json(data), ensure_ascii=False)

    def _deserialize(self, data: str) -> Any:
        return json.loads(data)

    # ── 同步方法 ──

    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")

        latest_key = self._make_key(thread_id, checkpoint_ns)
        checkpoint_id = self.redis_client.get(latest_key)
        if not checkpoint_id:
            return None

        ckpt_key = self._make_key(thread_id, checkpoint_ns, checkpoint_id)
        data_str = self.redis_client.get(ckpt_key)
        if not data_str:
            return None

        data = self._deserialize(data_str)
        checkpoint = data["checkpoint"]
        metadata = data["metadata"]
        parent_config = data.get("parent_config")

        writes_key = self._make_writes_key(thread_id, checkpoint_ns, checkpoint_id)
        writes_str = self.redis_client.get(writes_key)
        writes = self._deserialize(writes_str) if writes_str else []

        return CheckpointTuple(
            config={"configurable": {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "checkpoint_id": checkpoint_id}},
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=parent_config,
            pending_writes=writes,
        )

    def put(self, config: RunnableConfig, checkpoint: Checkpoint, metadata: CheckpointMetadata, new_versions: ChannelVersions) -> RunnableConfig:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = checkpoint["id"]

        ckpt_key = self._make_key(thread_id, checkpoint_ns, checkpoint_id)
        data = {"checkpoint": checkpoint, "metadata": metadata, "parent_config": config}
        self.redis_client.set(ckpt_key, self._serialize(data))

        latest_key = self._make_key(thread_id, checkpoint_ns)
        self.redis_client.set(latest_key, checkpoint_id)

        return {"configurable": {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "checkpoint_id": checkpoint_id}}

    def put_writes(self, config: RunnableConfig, writes: Sequence[tuple[str, Any]], task_id: str, task_path: str = "") -> None:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"].get("checkpoint_id", "")
        writes_key = self._make_writes_key(thread_id, checkpoint_ns, checkpoint_id)
        self.redis_client.set(writes_key, self._serialize(list(writes)))

    def list(self, config: RunnableConfig | None, *, filter: dict[str, Any] | None = None, before: RunnableConfig | None = None, limit: int | None = None) -> Iterator[CheckpointTuple]:
        if config is None:
            return iter([])

        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")

        pattern = f"{self.prefix}{thread_id}:{checkpoint_ns}:*"
        keys = self.redis_client.keys(pattern)
        ckpt_keys = [k for k in keys if not k.endswith(":latest") and ":writes:" not in k]

        results = []
        for key in ckpt_keys:
            data_str = self.redis_client.get(key)
            if data_str:
                data = self._deserialize(data_str)
                checkpoint_id = data["checkpoint"]["id"]
                results.append(CheckpointTuple(
                    config={"configurable": {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "checkpoint_id": checkpoint_id}},
                    checkpoint=data["checkpoint"],
                    metadata=data["metadata"],
                    parent_config=data.get("parent_config"),
                ))

        results.sort(key=lambda x: x["checkpoint"]["id"], reverse=True)
        if limit:
            results = results[:limit]
        return iter(results)

    def delete_thread(self, thread_id: str) -> None:
        pattern = f"{self.prefix}{thread_id}:*"
        keys = self.redis_client.keys(pattern)
        if keys:
            self.redis_client.delete(*keys)

    # ── 异步方法 ──

    async def aget_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self.get_tuple, config))

    async def aput(self, config: RunnableConfig, checkpoint: Checkpoint, metadata: CheckpointMetadata, new_versions: ChannelVersions) -> RunnableConfig:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self.put, config, checkpoint, metadata, new_versions))

    async def aput_writes(self, config: RunnableConfig, writes: Sequence[tuple[str, Any]], task_id: str, task_path: str = "") -> None:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self.put_writes, config, writes, task_id, task_path))

    async def adelete_thread(self, thread_id: str) -> None:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self.delete_thread, thread_id))

    async def alist(self, config: RunnableConfig | None, *, filter: dict[str, Any] | None = None, before: RunnableConfig | None = None, limit: int | None = None) -> AsyncIterator[CheckpointTuple]:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, partial(self.list, config, filter=filter, before=before, limit=limit))
        if result:
            for item in result:
                yield item

    async def aprune(self, thread_ids: Sequence[str], *, strategy: str = "keep_latest") -> None:
        pass
