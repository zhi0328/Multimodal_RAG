"""
RAG 评测平台后端：数据集生成 + 瑞士制锦标赛 + Web API
端口：8006
"""

import os
import sys
import json
import uuid
import sqlite3
import logging
import hashlib
import threading
from datetime import datetime
from typing import List, Optional, Dict, Any
from threading import Event

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# 项目根目录加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dataset_generator import generate_dataset, load_source_text, list_source_files
from tournament import run_tournament
from rag_engine import RAGEngine, ExperimentConfig

# ────────────────────── 配置 ──────────────────────

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', '..', '.env'))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "data", "uploads")
DATASET_DIR = os.path.join(BASE_DIR, "data", "datasets")
DB_PATH = os.path.join(BASE_DIR, "data", "rageval.db")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DATASET_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ────────────────────── 全局设置 ──────────────────────

class GlobalSettings(BaseModel):
    llm_base_url: str = os.getenv("SILICONFLOW_BASE_URL")
    llm_model_name: str = "Qwen/Qwen3-8B"
    llm_api_key: str = os.getenv("SILICONFLOW_API_KEY")
    judge_base_url: str = os.getenv("MIMO_BASE_URL")
    judge_model_name: str = "mimo-v2.5-pro"
    judge_api_key: str = os.getenv("MIMO_API_KEY")
    embedding_api_url: str = "https://api.siliconflow.cn/v1/embeddings"
    embedding_model: str = "Qwen/Qwen3-VL-Embedding-8B"
    embedding_dim: int = 4096
    rerank_api_url: str = "https://api.siliconflow.cn/v1/rerank"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"


current_settings = GlobalSettings()

# OpenAI client for LLM calls
from openai import OpenAI

client: Optional[OpenAI] = None
judge_client: Optional[OpenAI] = None


def update_client():
    global client, judge_client
    client = OpenAI(api_key=current_settings.llm_api_key, base_url=current_settings.llm_base_url)
    judge_client = OpenAI(api_key=current_settings.judge_api_key, base_url=current_settings.judge_base_url)


update_client()


def llm_caller(messages, temperature=0.7, max_tokens=1024):
    """生成答案用的 LLM 调用函数（带限速）"""
    from rag_engine import llm_limiter
    llm_limiter.acquire()

    resp = client.chat.completions.create(
        model=current_settings.llm_model_name,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=120,
    )
    return resp.choices[0].message.content.strip()


def judge_llm_caller(messages, temperature=0.1, max_tokens=512):
    """Judge 评判用的 LLM 调用函数（带限速）"""
    from rag_engine import llm_limiter
    llm_limiter.acquire()

    resp = judge_client.chat.completions.create(
        model=current_settings.judge_model_name,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=120,
    )
    return resp.choices[0].message.content.strip()


def judge_llm_caller(messages, temperature=0.1, max_tokens=512):
    """锦标赛评判专用 LLM 调用函数（使用 judge 模型）"""
    from rag_engine import llm_limiter
    llm_limiter.acquire()

    resp = judge_client.chat.completions.create(
        model=current_settings.judge_model_name,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=120,
    )
    return resp.choices[0].message.content.strip()


# ────────────────────── Milvus 连接 ──────────────────────

from pymilvus import MilvusClient

milvus_uri = os.getenv("MILVUS_URI")
milvus_user = os.getenv("MILVUS_USER")
milvus_password = os.getenv("MILVUS_PASSWORD")
milvus_client = MilvusClient(uri=milvus_uri, user=milvus_user, password=milvus_password)

rag_engine = RAGEngine(milvus_client, current_settings, llm_caller)


# ────────────────────── 数据库 ──────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    # 最终比赛结果（历史记录，多次比赛累积）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tournaments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dataset_name TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            configs_json TEXT,
            rankings_json TEXT,
            rounds_json TEXT
        )
    """)
    # 生成的答案（永久保存，逐条记录）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS eval_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dataset_name TEXT NOT NULL,
            config_name TEXT NOT NULL,
            question_index INTEGER NOT NULL,
            question TEXT,
            answer TEXT,
            context TEXT,
            UNIQUE(dataset_name, config_name, question_index)
        )
    """)
    # 比赛进度（断点续跑，完成后删除）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tournament_checkpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dataset_name TEXT NOT NULL,
            configs_fingerprint TEXT NOT NULL,
            players_json TEXT,
            rounds_json TEXT,
            pairings_json TEXT,
            current_round INTEGER DEFAULT 0,
            matches_in_round INTEGER DEFAULT 0,
            total_rounds INTEGER DEFAULT 0,
            phase TEXT DEFAULT 'generating',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(dataset_name, configs_fingerprint)
        )
    """)
    conn.commit()
    conn.close()


init_db()


# ────────────────────── 断点续跑：辅助函数 ──────────────────────

def compute_fingerprint(data) -> str:
    """计算数据的 SHA256 指纹，用于检测配置是否变化"""
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


# ── 答案存储 ──

def save_eval_answer(dataset_name: str, config_name: str, q_idx: int,
                     question: str, answer: str, context: str):
    """保存一条生成的答案（INSERT OR IGNORE，已存在则跳过）"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR IGNORE INTO eval_answers "
        "(dataset_name, config_name, question_index, question, answer, context) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (dataset_name, config_name, q_idx, question, answer, context)
    )
    conn.commit()
    conn.close()


def load_answers_for_config(dataset_name: str, config_name: str) -> Dict[int, dict]:
    """加载某配置的所有已生成答案，返回 {question_index: {answer, context}}"""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT question_index, answer, context FROM eval_answers "
        "WHERE dataset_name = ? AND config_name = ? ORDER BY question_index",
        (dataset_name, config_name)
    ).fetchall()
    conn.close()
    return {r[0]: {"answer": r[1], "context": r[2]} for r in rows}


def count_answers_for_config(dataset_name: str, config_name: str) -> int:
    """统计某配置已生成的答案数量"""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT COUNT(*) FROM eval_answers WHERE dataset_name = ? AND config_name = ?",
        (dataset_name, config_name)
    ).fetchone()
    conn.close()
    return row[0]


# ── 比赛进度 ──

def save_tournament_checkpoint(dataset_name: str, configs_fp: str,
                                players_data: list, rounds_data: list,
                                current_round: int, total_rounds: int,
                                phase: str = "tournament",
                                matches_in_round: int = 0,
                                pairings: list = None):
    """保存或更新比赛进度 checkpoint"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO tournament_checkpoints
            (dataset_name, configs_fingerprint, players_json, rounds_json, pairings_json,
             current_round, matches_in_round, total_rounds, phase)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(dataset_name, configs_fingerprint) DO UPDATE SET
            players_json = excluded.players_json,
            rounds_json = excluded.rounds_json,
            pairings_json = excluded.pairings_json,
            current_round = excluded.current_round,
            matches_in_round = excluded.matches_in_round,
            total_rounds = excluded.total_rounds,
            phase = excluded.phase,
            updated_at = CURRENT_TIMESTAMP
    """, (dataset_name, configs_fp, json.dumps(players_data, ensure_ascii=False),
          json.dumps(rounds_data, ensure_ascii=False),
          json.dumps(pairings) if pairings else None,
          current_round, matches_in_round, total_rounds, phase))
    conn.commit()
    conn.close()
    logger.info(f"比赛进度已保存: dataset={dataset_name}, round={current_round}, match={matches_in_round}, phase={phase}")


def load_tournament_checkpoint(dataset_name: str, configs_fp: str) -> Optional[Dict]:
    """加载比赛进度 checkpoint，返回 None 表示无可用 checkpoint"""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT players_json, rounds_json, pairings_json, current_round, matches_in_round, total_rounds, phase "
        "FROM tournament_checkpoints WHERE dataset_name = ? AND configs_fingerprint = ?",
        (dataset_name, configs_fp)
    ).fetchone()
    conn.close()

    if not row:
        return None

    return {
        "players_data": json.loads(row[0]) if row[0] else None,
        "rounds_history": json.loads(row[1]) if row[1] else [],
        "pairings": json.loads(row[2]) if row[2] else None,
        "current_round": row[3],
        "matches_in_round": row[4],
        "total_rounds": row[5],
        "phase": row[6],
    }


def delete_tournament_checkpoint(dataset_name: str, configs_fp: str):
    """删除已完成的 checkpoint"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "DELETE FROM tournament_checkpoints WHERE dataset_name = ? AND configs_fingerprint = ?",
        (dataset_name, configs_fp)
    )
    conn.commit()
    conn.close()
    logger.info(f"比赛 checkpoint 已删除: dataset={dataset_name}")


def cleanup_eval_collections(milvus_client, collection_prefix: str, config_names: list):
    """清理锦标赛使用的所有临时 Milvus 集合"""
    import re
    for name in config_names:
        safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        coll = f"{collection_prefix}_{safe_name}"
        try:
            if milvus_client.has_collection(coll):
                milvus_client.drop_collection(coll)
                logger.info(f"已清理临时集合: {coll}")
        except Exception as e:
            logger.warning(f"清理集合 {coll} 失败: {e}")


# ────────────────────── 异步任务系统 ──────────────────────

tasks: Dict[str, dict] = {}


def create_task(task_type: str, name: str) -> str:
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "type": task_type,
        "name": name,
        "status": "pending",
        "progress": 0,
        "message": "",
        "created_at": datetime.now().isoformat(),
        "cancel_flag": False,
        "stop_event": Event(),  # 用于通知后台线程立即停止
        "error": None,
        "result": None,
    }
    return task_id


def background_generate(task_id: str, num_questions: int, source_filename: str = None):
    """后台生成数据集"""
    logger.info(f"生成问答对使用的模型: {current_settings.llm_model_name}")
    tasks[task_id]["status"] = "running"
    try:
        # 找源文件
        if source_filename:
            filepath = os.path.join(UPLOAD_DIR, source_filename)
        else:
            files = list_source_files(UPLOAD_DIR)
            if not files:
                raise FileNotFoundError("没有上传的文件")
            filepath = files[0]["path"]

        source_text = load_source_text(filepath)
        source_name = os.path.basename(filepath)

        stop_event = tasks.get(task_id, {}).get("stop_event", Event())

        def is_cancelled():
            return stop_event.is_set()

        def progress_cb(pct, msg):
            t = tasks.get(task_id)
            if t:
                t["progress"] = pct
                t["message"] = msg

        result = generate_dataset(
            source_text=source_text,
            num_questions=num_questions,
            llm_caller=llm_caller,
            source_filename=source_name,
            cancel_check=is_cancelled,
            progress_callback=progress_cb,
        )

        if is_cancelled():
            logger.info(f"数据集生成已被用户取消 (task_id={task_id})")
            t = tasks.get(task_id)
            if t:
                t["status"] = "cancelled"
            return

        t = tasks.get(task_id)
        if t:
            t["status"] = "completed"
            t["result"] = result
            t["progress"] = 100
        logger.info(f"数据集生成完成，共 {len(result.get('qa_pairs', []))} 个问答对")
    except Exception as e:
        logger.exception(f"数据集生成失败: {e}")
        t = tasks.get(task_id)
        if t:
            t["status"] = "failed"
            t["error"] = str(e)


def background_tournament(task_id: str, dataset_path: str, configs: list):
    """后台运行锦标赛（支持断点续跑）"""
    logger.info(f"生成答案使用的模型: {current_settings.llm_model_name}")
    logger.info(f"Judge 评判使用的模型: {current_settings.judge_model_name}")
    t = tasks.get(task_id)
    if t:
        t["status"] = "running"
    collection_prefix = "rag_eval"
    config_names = [c.name for c in configs]
    completed_normally = False

    try:
        # 如果只是文件名，拼接完整路径
        if not os.path.isabs(dataset_path):
            dataset_path = os.path.join(DATASET_DIR, dataset_path)

        with open(dataset_path, 'r', encoding='utf-8') as f:
            dataset = json.load(f)

        # 兼容两种格式
        if isinstance(dataset, list):
            dataset = {"qa_pairs": dataset}

        # 找源文本
        metadata = dataset.get("metadata", {})
        source_file = metadata.get("source_file", "")
        source_path = os.path.join(UPLOAD_DIR, source_file)
        if not os.path.exists(source_path):
            files = list_source_files(UPLOAD_DIR)
            if files:
                source_path = files[0]["path"]
            else:
                raise FileNotFoundError("找不到源文档")

        full_text = load_source_text(source_path)

        # 数据集名称和配置指纹
        ds_name = os.path.basename(dataset_path).replace('.json', '')
        configs_fp = compute_fingerprint([c.to_dict() for c in configs])

        # 加载已有 checkpoint
        checkpoint = load_tournament_checkpoint(ds_name, configs_fp)
        if checkpoint:
            logger.info(f"检测到未完成的锦标赛 (phase={checkpoint['phase']}, round={checkpoint['current_round']})")

        stop_event = tasks.get(task_id, {}).get("stop_event", Event())

        def is_cancelled():
            return stop_event.is_set()

        def progress_cb(pct, msg):
            t = tasks.get(task_id)
            if t:
                t["progress"] = pct
                t["message"] = msg

        def save_checkpoint_cb(players_data, rounds_data, current_round, total_rounds,
                               matches_in_round=0, pairings=None):
            save_tournament_checkpoint(ds_name, configs_fp, players_data, rounds_data,
                                       current_round, total_rounds, phase="tournament",
                                       matches_in_round=matches_in_round, pairings=pairings)

        def save_answer_cb(config_name, q_idx, question, answer, context):
            save_eval_answer(ds_name, config_name, q_idx, question, answer, context)

        def load_answers_cb(config_name):
            return load_answers_for_config(ds_name, config_name)

        rankings, rounds_history = run_tournament(
            dataset=dataset,
            rag_engine=rag_engine,
            configs=configs,
            full_text=full_text,
            llm_caller=judge_llm_caller,
            collection_prefix=collection_prefix,
            dataset_name=ds_name,
            cancel_check=is_cancelled,
            progress_callback=progress_cb,
            checkpoint_data=checkpoint,
            save_checkpoint_callback=save_checkpoint_cb,
            save_answer_callback=save_answer_cb,
            load_answers_callback=load_answers_cb,
        )

        if is_cancelled():
            logger.info(f"锦标赛已被用户取消 (task_id={task_id})，进度已保存")
            t = tasks.get(task_id)
            if t:
                t["status"] = "cancelled"
            return

        # 比赛完成，保存最终结果
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO tournaments (dataset_name, configs_json, rankings_json, rounds_json) VALUES (?, ?, ?, ?)",
            (ds_name, json.dumps([c.to_dict() for c in configs]), json.dumps(rankings), json.dumps(rounds_history))
        )
        conn.commit()
        conn.close()

        # 删除 checkpoint（已完成）
        delete_tournament_checkpoint(ds_name, configs_fp)
        completed_normally = True

        t = tasks.get(task_id)
        if t:
            t["status"] = "completed"
            t["result"] = {"rankings": rankings, "rounds": rounds_history}
            t["progress"] = 100
    except Exception as e:
        logger.exception(f"锦标赛失败: {e}")
        t = tasks.get(task_id)
        if t:
            t["status"] = "failed"
            t["error"] = str(e)
    finally:
        # Milvus 集合保留不清理，方便重跑时跳过索引重建
        # 如需手动清理，调用 DELETE /api/experiment/collections
        pass


# ────────────────────── FastAPI 应用 ──────────────────────

app = FastAPI(title="RAG 评测平台")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── 请求模型 ──

class GenerateRequest(BaseModel):
    num_questions: int = 5
    source_filename: Optional[str] = None

class DatasetSaveRequest(BaseModel):
    qa_pairs: List[Dict[str, str]]
    filename: str
    metadata: Optional[Dict[str, Any]] = None

class EvaluationRequest(BaseModel):
    dataset_path: str
    configs: List[Dict[str, Any]]


# ── 设置 API ──

@app.get("/api/settings")
def get_settings():
    return current_settings

@app.post("/api/settings")
def save_settings(settings: GlobalSettings):
    global current_settings
    current_settings = settings
    update_client()
    rag_engine.settings = current_settings
    return {"status": "success"}


# ── 数据集 API ──

@app.post("/api/dataset/upload")
async def upload_file(file: UploadFile = File(...)):
    path = os.path.join(UPLOAD_DIR, file.filename)
    with open(path, "wb") as f:
        f.write(await file.read())
    return {"filename": file.filename, "path": path}

@app.get("/api/datasets")
def list_datasets():
    result = []
    if os.path.exists(DATASET_DIR):
        for name in os.listdir(DATASET_DIR):
            if name.endswith('.json'):
                path = os.path.join(DATASET_DIR, name)
                result.append({
                    "name": name,
                    "path": path,
                    "size": os.path.getsize(path),
                    "created_at": datetime.fromtimestamp(os.path.getctime(path)).isoformat(),
                })
    result.sort(key=lambda x: x["created_at"], reverse=True)
    return result

@app.post("/api/dataset/generate")
def start_generation(req: GenerateRequest):
    task_id = create_task("generation", f"生成 {req.num_questions} 个问答对")
    thread = threading.Thread(target=background_generate, args=(task_id, req.num_questions, req.source_filename))
    thread.daemon = True
    thread.start()
    return {"task_id": task_id, "status": "pending"}

@app.post("/api/dataset/save")
def save_dataset(req: DatasetSaveRequest):
    path = os.path.join(DATASET_DIR, req.filename if req.filename.endswith('.json') else req.filename + '.json')
    data = {"qa_pairs": req.qa_pairs, "metadata": req.metadata or {}}
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {"status": "saved", "path": path}

@app.get("/api/dataset/{name}")
def get_dataset(name: str):
    path = os.path.join(DATASET_DIR, name)
    if not os.path.exists(path):
        raise HTTPException(404, "数据集不存在")
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    return data.get("qa_pairs", [])

@app.delete("/api/dataset/{name}")
def delete_dataset(name: str):
    path = os.path.join(DATASET_DIR, name)
    if os.path.exists(path):
        os.remove(path)
    return {"status": "deleted"}


# ── 文件浏览 API ──

@app.get("/api/file/content")
def get_file_content(filename: str, page: int = 1, page_size: int = 50):
    path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(404, "文件不存在")
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    total = len(lines)
    total_pages = max(1, (total + page_size - 1) // page_size)
    start = (page - 1) * page_size
    content = "".join(lines[start:start + page_size])
    return {"filename": filename, "page": page, "page_size": page_size,
            "total_lines": total, "total_pages": total_pages, "content": content}


# ── 评测 API ──

@app.post("/api/experiment/run")
def start_evaluation(req: EvaluationRequest):
    configs = []
    for c in req.configs:
        configs.append(ExperimentConfig(**c))

    task_id = create_task("evaluation", f"锦标赛: {os.path.basename(req.dataset_path)}")
    thread = threading.Thread(target=background_tournament, args=(task_id, req.dataset_path, configs))
    thread.daemon = True
    thread.start()
    return {"task_id": task_id, "status": "pending"}

def _clean_task(t: dict) -> dict:
    """去掉不可 JSON 序列化的字段（如 threading.Event）"""
    return {k: v for k, v in t.items() if k != "stop_event"}


@app.get("/api/experiment/status/{task_id}")
def get_task_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(404, "任务不存在")
    return {"task_id": task_id, **_clean_task(tasks[task_id])}

@app.post("/api/experiment/cancel/{task_id}")
def cancel_task(task_id: str):
    if task_id in tasks:
        tasks[task_id]["cancel_flag"] = True
        tasks[task_id]["stop_event"].set()  # 通知后台线程立即停止
    return {"status": "cancelled"}


@app.get("/api/experiment/checkpoint/{dataset_name}")
def get_checkpoint(dataset_name: str, configs_json: str = ""):
    """查询某数据集+配置组合是否有未完成的 checkpoint"""
    if not configs_json:
        return {"has_checkpoint": False}
    try:
        configs_list = json.loads(configs_json)
        fp = compute_fingerprint(configs_list)
        ckpt = load_tournament_checkpoint(dataset_name, fp)
        if ckpt:
            return {
                "has_checkpoint": True,
                "phase": ckpt["phase"],
                "current_round": ckpt["current_round"],
                "matches_in_round": ckpt["matches_in_round"],
                "total_rounds": ckpt["total_rounds"],
            }
    except Exception:
        pass
    return {"has_checkpoint": False}


@app.delete("/api/experiment/checkpoint/{dataset_name}")
def delete_checkpoint_api(dataset_name: str, configs_json: str = ""):
    """删除某数据集+配置的 checkpoint（重新开始）"""
    if not configs_json:
        return {"status": "no_match"}
    try:
        configs_list = json.loads(configs_json)
        fp = compute_fingerprint(configs_list)
        delete_tournament_checkpoint(dataset_name, fp)
    except Exception:
        pass
    return {"status": "deleted"}


@app.delete("/api/experiment/collections")
def cleanup_collections():
    """清理所有评测用的 Milvus 临时集合"""
    cleaned = []
    try:
        collections = milvus_client.list_collections()
        for coll in collections:
            if coll.startswith("rag_eval_"):
                milvus_client.drop_collection(coll)
                cleaned.append(coll)
                logger.info(f"已清理集合: {coll}")
    except Exception as e:
        logger.warning(f"清理集合失败: {e}")
    return {"cleaned": cleaned}


# ── 历史 API ──

@app.get("/api/history/dataset/{name}")
def get_history(name: str):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, timestamp, configs_json, rankings_json, rounds_json FROM tournaments WHERE dataset_name = ? ORDER BY timestamp DESC",
        (name,)
    ).fetchall()
    conn.close()
    return [{"id": r[0], "timestamp": r[1], "configs": json.loads(r[2]),
             "rankings": json.loads(r[3]), "rounds": json.loads(r[4])} for r in rows]

@app.get("/api/tasks")
def list_tasks():
    result = [{"id": tid, **_clean_task(t)} for tid, t in tasks.items()]
    result.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return result

@app.delete("/api/task/{task_id}")
def delete_task(task_id: str):
    if task_id in tasks:
        tasks[task_id]["stop_event"].set()  # 先通知后台线程停止
    tasks.pop(task_id, None)
    return {"status": "deleted"}


# ────────────────────── 启动 ──────────────────────

if __name__ == "__main__":
    # 屏蔽 uvicorn 的 access log（GET /api/tasks 等）
    class AccessLogFilter(logging.Filter):
        def filter(self, record):
            return "/api/tasks" not in record.getMessage()

    logging.getLogger("uvicorn.access").addFilter(AccessLogFilter())
    # 屏蔽 httpx 的 HTTP Request 日志
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    uvicorn.run(app, host="0.0.0.0", port=8006)
