"""
瑞士制锦标赛评测系统：使用 Elo 评分对多个 RAG 配置进行公平比较。
支持答案持久化和断点续跑。
"""

import json
import math
import logging
from typing import List, Dict, Tuple, Optional, Callable

logger = logging.getLogger(__name__)


# ────────────────────── Elo 评分 ──────────────────────

def calculate_elo(rating_a: float, rating_b: float, actual_score_a: float, k: int = 32) -> Tuple[float, float]:
    """
    计算新的 Elo 评分。
    actual_score_a: 1=A赢, 0=A输, 0.5=平局
    """
    expected_a = 1 / (1 + 10 ** ((rating_b - rating_a) / 400))
    expected_b = 1 - expected_a
    new_a = rating_a + k * (actual_score_a - expected_a)
    new_b = rating_b + k * ((1 - actual_score_a) - expected_b)
    return new_a, new_b


# ────────────────────── LLM 评判 ──────────────────────

JUDGE_PROMPT = """你是一个公正的 RAG 系统评测专家。请对比【系统A】和【系统B】针对问题的回答质量。

【问题】: {question}
【标准答案 (Ground Truth)】: {ground_truth}

--------------------------------------------------
【系统 A】
回答: {answer_a}
检索到的上下文: {context_a}

--------------------------------------------------
【系统 B】
回答: {answer_b}
检索到的上下文: {context_b}

--------------------------------------------------
【评判标准】
1. **准确性**：回答是否符合标准答案和事实？
2. **相关性**：回答是否直接解决了问题？
3. **检索质量**：检索到的上下文是否支持回答？
4. **幻觉检测**：如果检索内容为空或不相关，系统是否编造了答案？（编造者扣分）

请以 JSON 格式输出评判结果，格式如下：
{{"winner": "A" 或 "B" 或 "Tie", "reason": "简短理由(不超过50字)"}}
注意：
1. 不要输出 Markdown 格式，只输出纯 JSON 字符串
2. reason 必须简短，不超过 50 个字
3. 只输出一行 JSON，不要换行"""


def build_judge_prompt(question, ground_truth, answer_a, context_a, answer_b, context_b) -> str:
    return JUDGE_PROMPT.format(
        question=question,
        ground_truth=ground_truth,
        answer_a=answer_a,
        context_a=context_a[:1000] if context_a else "（无）",
        answer_b=answer_b,
        context_b=context_b[:1000] if context_b else "（无）",
    )


def parse_judge_output(text: str) -> Tuple[str, str]:
    """解析 LLM 评判结果，支持多种输出格式"""
    import re

    clean = text.strip()

    # 清理 markdown 代码块
    if clean.startswith("```"):
        clean = re.sub(r'^```(?:json)?\s*', '', clean)
        clean = re.sub(r'\s*```$', '', clean)
    clean = clean.strip()

    # 清理 JSON 内部的换行符（reason 里的换行会破坏 JSON）
    clean_for_json = clean.replace('\n', ' ').replace('\r', '')

    # ── 方法1: 直接 JSON 解析 ──
    try:
        data = json.loads(clean_for_json)
        w = data.get("winner") or data.get("胜者") or data.get("Winner") or ""
        r = data.get("reason") or data.get("理由") or ""
        w = str(w).strip()
        if w.upper() in ("A", "B"):
            return w.upper(), r
        if w in ("Tie", "TIE", "tie", "平局", "一样", "相当", "不分胜负"):
            return "Tie", r
    except (json.JSONDecodeError, AttributeError):
        pass

    # ── 方法2: 从文本中提取完整或截断的 JSON ──
    # 先尝试匹配完整 JSON
    json_match = re.search(r'\{[^{}]*"winner"[^{}]*\}', clean_for_json, re.IGNORECASE)
    if not json_match:
        json_match = re.search(r'\{[^{}]*"胜者"[^{}]*\}', clean_for_json, re.IGNORECASE)

    # 如果没匹配到完整 JSON，可能是被截断了（reason 没写完），尝试匹配截断的 JSON
    if not json_match:
        json_match = re.search(r'\{[^{}]*"winner"\s*:\s*"(A|B|Tie|TIE|平局)"', clean_for_json, re.IGNORECASE)

    if json_match:
        try:
            data = json.loads(json_match.group())
            w = data.get("winner") or data.get("胜者") or ""
            r = data.get("reason") or data.get("理由") or ""
            w = str(w).strip()
            if w.upper() in ("A", "B"):
                return w.upper(), r
            if w in ("Tie", "TIE", "tie", "平局", "一样", "相当"):
                return "Tie", r
        except (json.JSONDecodeError, AttributeError):
            # 直接从匹配文本中提取 winner 值
            w_match = re.search(r'"winner"\s*:\s*"(A|B|Tie|TIE|平局)"', json_match.group(), re.IGNORECASE)
            if not w_match:
                w_match = re.search(r'"胜者"\s*:\s*"(A|B|Tie|TIE|平局)"', json_match.group(), re.IGNORECASE)
            if w_match:
                w = w_match.group(1)
                if w.upper() in ("A", "B"):
                    return w.upper(), clean
                return "Tie", clean

    # ── 方法3: 正则匹配 key-value 格式 ──
    kv_match = re.search(r'(?:winner|胜者|Winner)\s*[:：]\s*["\']?(A|B|Tie|TIE|平局)["\']?', clean, re.IGNORECASE)
    if kv_match:
        w = kv_match.group(1)
        if w.upper() in ("A", "B"):
            return w.upper(), clean
        return "Tie", clean

    # ── 方法4: 关键词匹配（最后兜底）──
    if re.search(r'系统\s*A.{0,10}?(?:更|稍|略|明[显确]).*?(?:好|优|胜|强|佳|准确|完整)', clean):
        return "A", clean
    if re.search(r'系统\s*B.{0,10}?(?:更|稍|略|明[显确]).*?(?:好|优|胜|强|佳|准确|完整)', clean):
        return "B", clean
    if re.search(r'(?:A|系统A).{0,10}?(?:胜出|获胜|赢|更好|更[准优佳]|略[胜优]|稍[好优])', clean):
        return "A", clean
    if re.search(r'(?:B|系统B).{0,10}?(?:胜出|获胜|赢|更好|更[准优佳]|略[胜优]|稍[好优])', clean):
        return "B", clean

    if re.search(r'(?:平局|不分[上下高]?低?|旗鼓相当|势均力敌|不相[上]?下|两者?[相]?当|一样好|同样好|难以区分)', clean):
        return "Tie", clean

    return "Tie", f"无法解析: {clean[:100]}"


def judge_match(question, ground_truth, answer_a, context_a, answer_b, context_b, llm_caller) -> Tuple[str, str]:
    """调用 LLM 评判一对回答"""
    prompt = build_judge_prompt(question, ground_truth, answer_a, context_a, answer_b, context_b)
    response = llm_caller([{"role": "user", "content": prompt}], temperature=0.1, max_tokens=1024)
    return parse_judge_output(response)


# ────────────────────── 锦标赛 ──────────────────────

class Player:
    """参赛配置（玩家）"""
    def __init__(self, name: str):
        self.name = name
        self.elo = 1500.0
        self.wins = 0
        self.losses = 0
        self.ties = 0
        self.history = set()
        self.matches_played = 0

    def to_dict(self):
        return {
            "name": self.name,
            "elo": round(self.elo, 1),
            "wins": self.wins,
            "losses": self.losses,
            "ties": self.ties,
            "matches_played": self.matches_played,
            "win_rate": round(self.wins / max(self.matches_played, 1) * 100, 1),
        }


def _sanitize_collection_name(name: str) -> str:
    """将 config name 转为合法的 Milvus 集合名（只保留字母数字下划线）"""
    import re
    return re.sub(r'[^a-zA-Z0-9_]', '_', name)


def run_tournament(
    dataset: Dict,
    rag_engine,
    configs: list,
    full_text: str,
    llm_caller,
    collection_prefix: str = "rag_eval",
    dataset_name: str = "",
    cancel_check=None,
    progress_callback=None,
    checkpoint_data: Optional[Dict] = None,
    save_checkpoint_callback: Optional[Callable] = None,
    save_answer_callback: Optional[Callable] = None,
    load_answers_callback: Optional[Callable] = None,
) -> Tuple[List[Dict], List[Dict]]:
    """
    运行瑞士制锦标赛，支持答案持久化和断点续跑。

    Args:
        dataset: {"qa_pairs": [...]} 数据集
        rag_engine: RAGEngine 实例
        configs: ExperimentConfig 列表
        full_text: 源文档完整文本
        llm_caller: LLM 调用函数
        collection_prefix: Milvus 集合名前缀（每个 config 用独立集合）
        dataset_name: 数据集名（用于 DB 存储）
        cancel_check: 取消检查函数
        progress_callback: 进度回调
        checkpoint_data: 已加载的比赛进度 checkpoint（可为 None）
        save_checkpoint_callback: 保存比赛进度的回调 fn(players, rounds, current_round, total_rounds)
        save_answer_callback: 保存单条答案的回调 fn(config_name, q_idx, question, answer, context)
        load_answers_callback: 加载某配置已生成答案的回调 fn(config_name) -> {q_idx: {answer, context}}

    Returns:
        (rankings, rounds_history)
    """
    qa_pairs = dataset["qa_pairs"]
    if not qa_pairs or len(configs) < 2:
        return [], []

    # ── Phase 1: 预生成所有答案（支持断点续跑）──
    answers_map = {}
    total_steps = len(configs) * len(qa_pairs)
    step = 0

    for config in configs:
        if cancel_check and cancel_check():
            logger.info("锦标赛在预生成答案阶段被取消")
            return [], []

        # 从 DB 加载已有答案
        existing_answers = {}
        if load_answers_callback:
            existing_answers = load_answers_callback(config.name)
        existing_count = len(existing_answers)

        if existing_count >= len(qa_pairs):
            # 该配置的答案已全部生成，直接复用
            answers_map[config.name] = [
                existing_answers[i] for i in range(len(qa_pairs))
            ]
            step += len(qa_pairs)
            logger.info(f"[{config.name}] 答案已全部存在（{existing_count}条），跳过生成")
            if progress_callback:
                pct = int((step / total_steps) * 40)
                progress_callback(pct, f"[{config.name}] 答案已缓存，跳过")
            continue

        # 需要生成答案（部分或全部缺失）
        answers_map[config.name] = [None] * len(qa_pairs)
        # 先填入已有的
        for q_idx, ans in existing_answers.items():
            answers_map[config.name][q_idx] = ans
            step += 1

        missing_indices = [i for i in range(len(qa_pairs)) if answers_map[config.name][i] is None]
        logger.info(f"[{config.name}] 已有 {existing_count} 条答案，需生成 {len(missing_indices)} 条")

        # 构建索引（per-config 集合名，已有则跳过）
        coll_name = f"{collection_prefix}_{_sanitize_collection_name(config.name)}"
        result = rag_engine.build_index(
            full_text, config, coll_name,
            cancel_check=cancel_check, skip_if_exists=True
        )
        if result is None:
            return [], []

        # 只生成缺失的答案
        for q_idx in missing_indices:
            if cancel_check and cancel_check():
                logger.info("锦标赛在预生成答案阶段被取消")
                return [], []

            qa = qa_pairs[q_idx]
            step += 1
            if progress_callback:
                pct = int((step / total_steps) * 40)
                progress_callback(pct, f"[{config.name}] 正在回答: {qa['question'][:30]}...")

            try:
                docs = rag_engine.retrieve(qa["question"], config, coll_name)
                context = "\n".join(docs) if docs else ""
                answer = rag_engine.generate_answer(qa["question"], context)
            except Exception as e:
                logger.warning(f"生成答案失败 [{config.name}] Q{q_idx}: {e}")
                answer = "（生成失败）"
                context = ""

            answers_map[config.name][q_idx] = {"answer": answer, "context": context}

            # 立即存入 DB
            if save_answer_callback:
                save_answer_callback(config.name, q_idx, qa["question"], answer, context)

    # ── 过滤生成失败的题目 ──
    fail_indices = set()
    for cname, answers in answers_map.items():
        for i, ans in enumerate(answers):
            if ans and (ans["answer"] == "（生成失败）" or "生成失败" in ans["answer"]):
                fail_indices.add(i)

    if fail_indices:
        logger.info(f"检测到 {len(fail_indices)} 道题有生成失败，自动过滤: {sorted(fail_indices)}")
        qa_pairs = [qa for i, qa in enumerate(qa_pairs) if i not in fail_indices]
        for cname in answers_map:
            answers_map[cname] = [ans for i, ans in enumerate(answers_map[cname]) if i not in fail_indices]
        logger.info(f"过滤后剩余 {len(qa_pairs)} 道题")

    if len(qa_pairs) < 1:
        logger.warning("过滤后无有效题目，跳过比赛")
        return [], []

    # ── Phase 2: 初始化玩家（支持从 checkpoint 恢复）──
    num_rounds = max(1, math.ceil(math.log2(len(configs))) + 1) if len(configs) > 2 else 1

    if checkpoint_data and checkpoint_data.get("phase") == "tournament":
        # 从 checkpoint 恢复玩家状态
        players_data = checkpoint_data["players_data"]
        players = []
        for pd in players_data:
            p = Player(pd["name"])
            p.elo = pd["elo"]
            p.wins = pd["wins"]
            p.losses = pd["losses"]
            p.ties = pd["ties"]
            p.matches_played = pd["matches_played"]
            p.history = set(pd.get("history", []))
            players.append(p)
        rounds_history = checkpoint_data.get("rounds_history", [])
        start_round = checkpoint_data.get("current_round", 0)
        start_match = checkpoint_data.get("matches_in_round", 0)

        # 如果是半轮恢复（matches_in_round > 0），最后一轮是未完成的
        # 需要把它从 rounds_history 中取出，继续往里追加比赛结果
        resume_round_matches = []
        if start_match > 0 and rounds_history and rounds_history[-1]["round"] == start_round + 1:
            resume_round_matches = rounds_history.pop()["matches"]

        logger.info(f"从 checkpoint 恢复比赛: 第 {start_round + 1} 轮, 第 {start_match + 1} 场比赛开始，共 {num_rounds} 轮")
    else:
        players = [Player(c.name) for c in configs]
        rounds_history = []
        start_round = 0
        start_match = 0
        resume_round_matches = []

    # 从 checkpoint 恢复的配对方案（仅用于恢复半轮）
    saved_pairings = checkpoint_data.get("pairings") if checkpoint_data else None

    for round_num in range(start_round, num_rounds):
        if cancel_check and cancel_check():
            logger.info(f"锦标赛在第 {round_num + 1} 轮被取消")
            break

        # 恢复时使用保存的配对方案，否则按 Elo 重新配对
        if saved_pairings and round_num == start_round and start_match > 0:
            pairings = [tuple(p) for p in saved_pairings]
            saved_pairings = None  # 只用一次
        else:
            # 按 Elo 降序排列
            players.sort(key=lambda p: p.elo, reverse=True)

            # 配对
            pairings = []
            used = set()
            for i, p_a in enumerate(players):
                if i in used:
                    continue
                best_opponent = None
                for j, p_b in enumerate(players):
                    if j <= i or j in used:
                        continue
                    if p_b.name not in p_a.history:
                        best_opponent = j
                        break
                if best_opponent is not None:
                    pairings.append((i, best_opponent))
                    used.add(i)
                    used.add(best_opponent)
                else:
                    for j, p_b in enumerate(players):
                        if j > i and j not in used:
                            pairings.append((i, j))
                            used.add(i)
                            used.add(j)
                            break

        # 恢复时使用已有比赛结果；之后每轮重置
        round_matches = resume_round_matches if resume_round_matches else []
        resume_round_matches = []  # 只在第一轮恢复用，之后清空

        for match_idx, (idx_a, idx_b) in enumerate(pairings):
            # 跳过本轮已完成的比赛（从 checkpoint 恢复时）
            if match_idx < start_match:
                continue

            if cancel_check and cancel_check():
                break

            p_a, p_b = players[idx_a], players[idx_b]
            a_answers = answers_map[p_a.name]
            b_answers = answers_map[p_b.name]

            wins_a, wins_b, ties = 0, 0, 0
            question_details = []

            for qi, qa in enumerate(qa_pairs):
                if cancel_check and cancel_check():
                    break

                if progress_callback:
                    pct = 40 + int(((round_num * len(qa_pairs) + qi) / (num_rounds * len(qa_pairs))) * 55)
                    progress_callback(pct, f"第{round_num+1}轮: {p_a.name} vs {p_b.name} - Q{qi+1}")

                try:
                    winner, reason = judge_match(
                        qa["question"], qa["answer"],
                        a_answers[qi]["answer"], a_answers[qi]["context"],
                        b_answers[qi]["answer"], b_answers[qi]["context"],
                        llm_caller,
                    )
                except Exception as e:
                    logger.warning(f"评判失败: {e}")
                    winner, reason = "Tie", "评判异常"

                if winner == "A":
                    wins_a += 1
                elif winner == "B":
                    wins_b += 1
                else:
                    ties += 1

                question_details.append({
                    "question": qa["question"],
                    "winner": winner,
                    "reason": reason,
                    "answer_a": a_answers[qi]["answer"][:200],
                    "answer_b": b_answers[qi]["answer"][:200],
                })

            if wins_a > wins_b:
                match_winner = "A"
                score_a, score_b = 1, 0
            elif wins_b > wins_a:
                match_winner = "B"
                score_a, score_b = 0, 1
            else:
                match_winner = "Tie"
                score_a, score_b = 0.5, 0.5

            old_elo_a, old_elo_b = p_a.elo, p_b.elo
            p_a.elo, p_b.elo = calculate_elo(p_a.elo, p_b.elo, score_a)

            if match_winner == "A":
                p_a.wins += 1
                p_b.losses += 1
            elif match_winner == "B":
                p_b.wins += 1
                p_a.losses += 1
            else:
                p_a.ties += 1
                p_b.ties += 1

            p_a.matches_played += 1
            p_b.matches_played += 1
            p_a.history.add(p_b.name)
            p_b.history.add(p_a.name)

            round_matches.append({
                "player_a": p_a.name,
                "player_b": p_b.name,
                "winner": match_winner,
                "score_a": wins_a,
                "score_b": wins_b,
                "ties": ties,
                "elo_change_a": round(p_a.elo - old_elo_a, 1),
                "elo_change_b": round(p_b.elo - old_elo_b, 1),
                "question_details": question_details,
            })

            # 每场比赛完成后保存 checkpoint（含本轮已完成的比赛数）
            if save_checkpoint_callback:
                players_data = []
                for p in players:
                    d = p.to_dict()
                    d["history"] = list(p.history)
                    players_data.append(d)
                # 把当前轮的已完成比赛也加入 rounds_history
                partial_rounds = rounds_history + [{
                    "round": round_num + 1,
                    "matches": round_matches,
                }]
                save_checkpoint_callback(
                    players_data, partial_rounds,
                    round_num, num_rounds,
                    matches_in_round=match_idx + 1,
                    pairings=pairings,
                )

        rounds_history.append({
            "round": round_num + 1,
            "matches": round_matches,
        })
        # 本轮结束，重置 start_match（下一轮从头开始）
        start_match = 0

        logger.info(f"第 {round_num + 1}/{num_rounds} 轮完成")

    # ── Phase 4: 最终排名 ──
    players.sort(key=lambda p: p.elo, reverse=True)
    rankings = []
    for rank, p in enumerate(players, 1):
        d = p.to_dict()
        d["rank"] = rank
        rankings.append(d)

    if progress_callback:
        progress_callback(100, "锦标赛完成")

    return rankings, rounds_history
