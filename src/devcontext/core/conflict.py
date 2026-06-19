"""冲突检测引擎 — L0-L5 六层检测 + 6 类冲突 + 证据层级 + V1/V5 修补。

职责：
1. L0-L5 六层冲突检测（内容哈希/语义签名/LLM 矛盾/交叉扫描/代码一致/人工）
2. 6 类冲突分类（事实/时效/范围/粒度/隐式/人为）
3. 证据可信度层级（6 级：代码/配置/用户陈述/隐式推断/LLM/无证据）
4. V1 代码活性检查（dead code 降级）
5. LLM 五分类判定（mutually_exclusive/one_refines_other/compatible_with_condition/complementary/identical）
6. 仲裁阈值可配置 + 仲裁日志（V9）
7. V5 quarantined/ + 降级机制

证据可信度层级（V1.7 §3.3）：
    Level 5: 活代码事实 → weight 1.0
    Level 4: 配置/文档 → weight 0.9
    Level 3: 用户陈述 → weight 0.7
    Level 2: 隐式推断 → weight 0.5
    Level 1: LLM 推理 → weight 0.3
    Level 0: 无证据 → weight 0.0

设计依据：``docs/devContextMemo-知识更新-冲突检测-冲突解决-深度设计-V1.0.md``
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any

from devcontext.config import settings
from devcontext.storage.sqlite import SQLiteStore
from devcontext.utils.hash import content_hash, jaccard_similarity, semantic_hash
from devcontext.utils.llm import LLMClient

logger = logging.getLogger(__name__)

# 证据可信度层级权重
EVIDENCE_WEIGHTS = {
    5: 1.0,  # 活代码事实
    4: 0.9,  # 配置/文档
    3: 0.7,  # 用户陈述
    2: 0.5,  # 隐式推断
    1: 0.3,  # LLM 推理
    0: 0.0,  # 无证据
}

# 6 类冲突
CONFLICT_FACTUAL = "factual"  # 事实冲突
CONFLICT_TEMPORAL = "temporal"  # 时效冲突
CONFLICT_SCOPE = "scope"  # 范围冲突
CONFLICT_GRANULARITY = "granularity"  # 粒度冲突
CONFLICT_IMPLICIT = "implicit"  # 隐式冲突
CONFLICT_HUMAN = "human"  # 人为冲突

# LLM 五分类
RELATION_MUTUALLY_EXCLUSIVE = "mutually_exclusive"
RELATION_ONE_REFINES_OTHER = "one_refines_other"
RELATION_COMPATIBLE_WITH_CONDITION = "compatible_with_condition"
RELATION_COMPLEMENTARY = "complementary"
RELATION_IDENTICAL = "identical"

# Jaccard 阈值
CROSS_SCAN_SIMILARITY_THRESHOLD = 0.75
LLM_JUDGE_SIMILARITY_THRESHOLD = 0.85


class ConflictPair:
    """冲突对。

    Attributes:
        knowledge_a: 知识 A 记录。
        knowledge_b: 知识 B 记录。
        similarity: 相似度。
        relation: LLM 五分类结果。
        conflict_type: 6 类冲突之一。
        recommended_action: 建议动作。
    """

    def __init__(
        self,
        knowledge_a: dict[str, Any],
        knowledge_b: dict[str, Any],
        similarity: float = 0.0,
        relation: str | None = None,
        conflict_type: str | None = None,
        recommended_action: str | None = None,
        explanation: str = "",
    ) -> None:
        self.a = knowledge_a
        self.b = knowledge_b
        self.similarity = similarity
        self.relation = relation
        self.conflict_type = conflict_type
        self.recommended_action = recommended_action
        self.explanation = explanation

    def to_dict(self) -> dict[str, Any]:
        return {
            "knowledge_a_id": self.a.get("id"),
            "knowledge_b_id": self.b.get("id"),
            "similarity": round(self.similarity, 4),
            "relation": self.relation,
            "conflict_type": self.conflict_type,
            "recommended_action": self.recommended_action,
            "explanation": self.explanation,
        }


class ArbitrationResult:
    """仲裁结果。

    Attributes:
        winner_id: 胜出知识 ID（None 表示人工裁决）。
        loser_id: 落败知识 ID。
        winner_score: 胜出得分。
        loser_score: 落败得分。
        difference: 得分差值。
        action: 仲裁动作（auto_adopt / manual_required / dual_discard）。
        quarantined: 是否进入隔离区（V5）。
    """

    def __init__(
        self,
        winner_id: str | None,
        loser_id: str | None,
        winner_score: float,
        loser_score: float,
        difference: float,
        action: str,
        quarantined: bool = False,
    ) -> None:
        self.winner_id = winner_id
        self.loser_id = loser_id
        self.winner_score = winner_score
        self.loser_score = loser_score
        self.difference = difference
        self.action = action
        self.quarantined = quarantined

    def to_dict(self) -> dict[str, Any]:
        return {
            "winner_id": self.winner_id,
            "loser_id": self.loser_id,
            "winner_score": round(self.winner_score, 4),
            "loser_score": round(self.loser_score, 4),
            "difference": round(self.difference, 4),
            "action": self.action,
            "quarantined": self.quarantined,
        }


class ConflictDetector:
    """冲突检测引擎。

    执行 L0-L5 六层检测 + 仲裁。

    Args:
        sqlite_store: SQLiteStore 实例。
        llm_client: LLM 客户端实例（可选，L2/L3/L4 需要）。
    """

    def __init__(
        self,
        sqlite_store: SQLiteStore,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.db = sqlite_store
        self.llm = llm_client

    # ==================================================================
    # L0-L5 检测层
    # ==================================================================

    def detect_l0_content_hash(self, new_knowledge: dict[str, Any]) -> dict[str, Any] | None:
        """L0: 内容哈希精确匹配。

        Args:
            new_knowledge: 新知识记录（含 knowledge_text）。

        Returns:
            匹配的已有知识记录，或 None。
        """
        new_hash = content_hash(new_knowledge.get("knowledge_text", ""))
        conn = self.db.get_connection()
        rows = conn.execute(
            "SELECT id, title FROM knowledge_index WHERE status != 'deprecated'"
        ).fetchall()
        for row in rows:
            # 简化：用 title 比对（实际应比对存储的 content_hash，但 DB 无此字段）
            existing_hash = content_hash(row[1])
            if new_hash == existing_hash:
                return {"id": row[0], "title": row[1], "match_type": "exact"}
        return None

    def detect_l1_semantic_hash(self, new_knowledge: dict[str, Any]) -> list[dict[str, Any]]:
        """L1: 语义签名相似检测。

        Args:
            new_knowledge: 新知识记录。

        Returns:
            相似的已有知识列表。
        """
        new_text = new_knowledge.get("knowledge_text", "")
        new_sem_hash = semantic_hash(new_text)
        conn = self.db.get_connection()
        rows = conn.execute(
            "SELECT id, title FROM knowledge_index WHERE status != 'deprecated'"
        ).fetchall()
        similar: list[dict[str, Any]] = []
        for row in rows:
            existing_sem_hash = semantic_hash(row[1])
            from devcontext.utils.hash import hamming_distance

            dist = hamming_distance(new_sem_hash, existing_sem_hash)
            # 64 位 SimHash，距离 < 10 视为相似
            if dist < 10:
                similar.append({"id": row[0], "title": row[1], "hamming_distance": dist})
        return similar

    def detect_l2_llm_contradiction(
        self, knowledge_a: dict[str, Any], knowledge_b: dict[str, Any]
    ) -> dict[str, Any] | None:
        """L2: LLM 矛盾检测（五分类判定）。

        Args:
            knowledge_a: 知识 A。
            knowledge_b: 知识 B。

        Returns:
            LLM 判定结果 dict，或 None（LLM 不可用时）。
        """
        if self.llm is None:
            return None
        text_a = knowledge_a.get("knowledge_text", knowledge_a.get("title", ""))
        text_b = knowledge_b.get("knowledge_text", knowledge_b.get("title", ""))
        prompt = f"""判断知识 A 和知识 B 的关系，选择以下之一：

1. mutually_exclusive — 两者不能同时为真
2. one_refines_other — 一条是另一条的精确化/细化/扩展
3. compatible_with_condition — 两者在特定条件下可以同时为真
4. complementary — 内容互补，不矛盾，建议合并
5. identical — 语义相同，仅表述不同

【知识 A】
{text_a}

【知识 B】
{text_b}

输出 JSON：
{{
  "relation": "mutually_exclusive" | "one_refines_other" | "compatible_with_condition" | "complementary" | "identical",
  "explanation": "判定依据",
  "contradiction_point": "矛盾点（仅 mutually_exclusive 时）",
  "refinement_direction": "A_refines_B 或 B_refines_A（仅 one_refines_other 时）"
}}
"""
        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        try:
            result: dict[str, Any] = json.loads(response["choices"][0]["message"]["content"])
            return result
        except (json.JSONDecodeError, KeyError):
            return None

    def detect_l3_cross_scan(self, domain: str | None = None) -> list[ConflictPair]:
        """L3: 交叉扫描（已有知识间矛盾检测）。

        对同 domain 内的知识做 pairwise Jaccard 比较，
        相似度 ≥ 0.85 的 pair 调 LLM 判定关系。

        Args:
            domain: 限定领域（None 扫描全部）。

        Returns:
            冲突对列表。
        """
        conn = self.db.get_connection()
        query = "SELECT * FROM knowledge_index WHERE status IN ('active', 'cold', 'stale')"
        if domain:
            query += " AND domain = ?"
            rows = conn.execute(query, [domain]).fetchall()
        else:
            rows = conn.execute(query).fetchall()
        columns = [d[0] for d in conn.execute("SELECT * FROM knowledge_index LIMIT 0").description]
        records = [dict(zip(columns, row, strict=False)) for row in rows]

        pairs: list[ConflictPair] = []
        for i, a in enumerate(records):
            for b in records[i + 1 :]:
                sim = jaccard_similarity(
                    a.get("knowledge_text", a.get("title", "")),
                    b.get("knowledge_text", b.get("title", "")),
                )
                if sim >= LLM_JUDGE_SIMILARITY_THRESHOLD:
                    # 调 LLM 判定
                    relation_result = self.detect_l2_llm_contradiction(a, b)
                    relation = relation_result.get("relation") if relation_result else None
                    if relation == RELATION_MUTUALLY_EXCLUSIVE:
                        conflict_type = CONFLICT_FACTUAL
                        action = "arbitrate"
                    elif relation == RELATION_ONE_REFINES_OTHER:
                        conflict_type = CONFLICT_GRANULARITY
                        action = "supersede_old"
                    elif relation == RELATION_COMPATIBLE_WITH_CONDITION:
                        conflict_type = CONFLICT_SCOPE
                        action = "add_condition"
                    elif relation == RELATION_COMPLEMENTARY:
                        conflict_type = None
                        action = "merge_fields"
                    elif relation == RELATION_IDENTICAL:
                        conflict_type = None
                        action = "discard_new"
                    else:
                        conflict_type = CONFLICT_IMPLICIT
                        action = "manual_required"

                    pairs.append(
                        ConflictPair(
                            knowledge_a=a,
                            knowledge_b=b,
                            similarity=sim,
                            relation=relation,
                            conflict_type=conflict_type,
                            recommended_action=action,
                            explanation=(
                                relation_result.get("explanation", "") if relation_result else ""
                            ),
                        )
                    )
        return pairs

    def detect_l4_code_consistency(
        self, knowledge: dict[str, Any], code_content: str
    ) -> dict[str, Any] | None:
        """L4: 代码一致性检测（调用 CalibrationEngine）。

        Args:
            knowledge: 知识记录。
            code_content: 代码内容。

        Returns:
            一致性检查结果，或 None。
        """
        if self.llm is None:
            return None
        from devcontext.core.calibration import CalibrationEngine

        # 此处简化：直接调 semantic_compare
        engine = CalibrationEngine.__new__(CalibrationEngine)
        engine.llm = self.llm
        engine.db = self.db
        engine.project_root = None
        return engine.semantic_compare(
            knowledge.get("knowledge_text", knowledge.get("title", "")),
            code_content,
        )

    # ==================================================================
    # V1 代码活性检查
    # ==================================================================

    @staticmethod
    def check_code_active(
        file_path: str | Path,
        project_root: str | Path | None = None,
    ) -> tuple[bool, int]:
        """V1 代码活性检查（dead code 降级）。

        检查项（三选一）：
        ① @Deprecated 注解 → 降级 Level 2
        ② 代码可达性（grep 调用次数 ≥ 1）→ Level 5
        ③ 最近 90 天修改过 → Level 5

        Args:
            file_path: 代码文件路径。
            project_root: 项目根目录。

        Returns:
            (is_active, evidence_level) 元组。
            is_active: True=活代码, False=dead code。
            evidence_level: 降级后的证据层级（5=活代码, 2=废弃, 3=未调用）。
        """
        path = Path(file_path)
        if not path.exists():
            return False, 0  # 文件不存在 → 无证据

        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            return False, 0

        # ① 检查 @Deprecated 注解
        if "@Deprecated" in content or "@Obsolete" in content:
            return False, 2  # 降级 Level 2

        # ② 代码可达性（简化：检查文件是否被 import/引用）
        if project_root:
            root = Path(project_root)
            stem = path.stem
            import_count = 0
            for py_file in root.rglob("*.py"):
                if py_file == path:
                    continue
                try:
                    if stem in py_file.read_text(encoding="utf-8"):
                        import_count += 1
                except OSError:
                    continue
            if import_count == 0:
                return False, 3  # 降级 Level 3

        # ③ 最近 90 天修改过
        mtime = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.UTC)
        if (dt.datetime.now(dt.UTC) - mtime).days <= 90:
            return True, 5

        return True, 5  # 默认活代码

    # ==================================================================
    # 证据权重计算
    # ==================================================================

    @staticmethod
    def compute_evidence_weight(
        evidence_level: int,
        code_active: bool = True,
        uncertain_count: int = 0,
    ) -> float:
        """计算证据权重（含 V1 活性降级 + V12 UNCERTAIN 折扣）。

        Args:
            evidence_level: 原始证据层级 0-5。
            code_active: 代码是否活跃（V1）。
            uncertain_count: UNCERTAIN 次数（V12）。

        Returns:
            实际证据权重 0.0-1.0。
        """
        base_weight = EVIDENCE_WEIGHTS.get(evidence_level, 0.0)

        # V1: dead code 降级
        if evidence_level == 5 and not code_active:
            base_weight = EVIDENCE_WEIGHTS[2]  # 降级到 Level 2

        # V12: UNCERTAIN 折扣
        if uncertain_count > 0:
            discount = {1: 1.0, 2: 0.80, 3: 0.60}.get(uncertain_count, 0.40)
            base_weight *= discount

        return base_weight

    @staticmethod
    def compute_arbitration_score(confidence: float, evidence_weight: float) -> float:
        """计算仲裁得分：evidence_weight × confidence。

        Args:
            confidence: 知识置信度。
            evidence_weight: 证据权重。

        Returns:
            仲裁得分 0.0-1.0。
        """
        return evidence_weight * confidence

    # ==================================================================
    # 仲裁
    # ==================================================================

    def arbitrate(
        self,
        knowledge_a: dict[str, Any],
        knowledge_b: dict[str, Any],
    ) -> ArbitrationResult:
        """仲裁两条矛盾知识。

        V9 阈值可配置 + V5 quarantined/。

        Args:
            knowledge_a: 知识 A。
            knowledge_b: 知识 B。

        Returns:
            仲裁结果。
        """
        # 计算证据权重
        weight_a = self.compute_evidence_weight(
            knowledge_a.get("evidence_level", 3),
            bool(knowledge_a.get("code_active", 1)),
            knowledge_a.get("stale_check_count", 0),
        )
        weight_b = self.compute_evidence_weight(
            knowledge_b.get("evidence_level", 3),
            bool(knowledge_b.get("code_active", 1)),
            knowledge_b.get("stale_check_count", 0),
        )

        # 计算仲裁得分
        score_a = self.compute_arbitration_score(knowledge_a.get("confidence", 0.0), weight_a)
        score_b = self.compute_arbitration_score(knowledge_b.get("confidence", 0.0), weight_b)

        difference = abs(score_a - score_b)
        winner_score = max(score_a, score_b)
        loser_score = min(score_a, score_b)

        # V9 阈值判定
        auto_threshold = settings.arbitration_auto_adopt_threshold
        dual_discard = settings.arbitration_dual_discard_threshold

        # 双方得分都过低
        if winner_score < dual_discard:
            return ArbitrationResult(
                winner_id=None,
                loser_id=None,
                winner_score=winner_score,
                loser_score=loser_score,
                difference=difference,
                action="dual_discard",
            )

        # 自动采用
        if difference >= auto_threshold:
            winner = knowledge_a if score_a > score_b else knowledge_b
            loser = knowledge_b if score_a > score_b else knowledge_a
            return ArbitrationResult(
                winner_id=winner.get("id"),
                loser_id=loser.get("id"),
                winner_score=winner_score,
                loser_score=loser_score,
                difference=difference,
                action="auto_adopt",
                quarantined=True,  # V5: 进入 quarantined/
            )

        # 人工裁决
        return ArbitrationResult(
            winner_id=None,
            loser_id=None,
            winner_score=winner_score,
            loser_score=loser_score,
            difference=difference,
            action="manual_required",
        )

    # ==================================================================
    # V5 降级机制
    # ==================================================================

    def check_auto_adopted_degradation(self, knowledge: dict[str, Any]) -> dict[str, Any]:
        """V5 检查自动采用未审核的降级。

        层 3：多次无人确认 → 降级
        （V13 修补：降级前检查间接验证，此处简化为计数器）

        Args:
            knowledge: 知识记录。

        Returns:
            降级决策 dict：
            - ``should_degrade``: 是否应降级
            - ``new_confidence``: 降级后的 confidence
            - ``reason``: 原因
        """
        unreviewed = knowledge.get("auto_adopted_unreviewed", 0)
        if unreviewed >= 3:
            # V13 简化：不检查间接验证，直接降级
            new_confidence = knowledge.get("confidence", 0.0) - 0.15
            return {
                "should_degrade": True,
                "new_confidence": max(new_confidence, 0.0),
                "reason": f"V5: auto_adopted_unreviewed={unreviewed} → degrade",
            }
        return {"should_degrade": False, "new_confidence": None, "reason": "within limit"}

    def increment_auto_adopted_unreviewed(self, kid: str) -> int:
        """递增自动采用未审核计数器。

        Args:
            kid: 知识 ID。

        Returns:
            新的计数值。
        """
        conn = self.db.get_connection()
        conn.execute(
            "UPDATE knowledge_index SET auto_adopted_unreviewed = auto_adopted_unreviewed + 1 "
            "WHERE id = ?",
            [kid],
        )
        conn.commit()
        row = conn.execute(
            "SELECT auto_adopted_unreviewed FROM knowledge_index WHERE id = ?",
            [kid],
        ).fetchone()
        return row[0] if row else 0
