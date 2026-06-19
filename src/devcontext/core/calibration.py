"""校准引擎 — 代码变更触发 + LLM 语义对比 + V6/V11/V12 修补。

职责：
1. 监听 8 种触发事件（E1-E8），最核心是 E1（git commit）
2. 检测到代码变更后，查找关联知识（通过 entities.file / entry_point）
3. 调用 LLM 做语义对比：知识描述 vs 当前代码 → CONSISTENT/INCONSISTENT/UNCERTAIN
4. V11：INCONSISTENT 时旧知识即时标记 suspected_stale
5. V6：UNCERTAIN 三级响应（即时警告 → 累积升级 → 长期未验证降级）
6. V12：suspected_stale 的 evidence_level 折扣
7. V18：certainty 分流（高确定度 INCONSISTENT → T18 直接废弃；低确定度 → T12 STALE）

触发事件矩阵（V1.7 §4.1）：
    E1: Git commit (P0)        E5: 架构评审通过 (P1)
    E2: 新服务/模块上线 (P0)    E6: Spec 接口变更 (P1)
    E3: 人肉修改 (P0)          E7: 依赖版本升级 (P1)
    E4: 需求文档变更 (P1)      E8: 故障复盘结论 (P2)

设计依据：``docs/devContextMemo-知识更新-冲突检测-冲突解决-深度设计-V1.0.md``
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any

from devcontext.storage.sqlite import SQLiteStore
from devcontext.utils.llm import LLMClient

logger = logging.getLogger(__name__)

# V18 certainty 分流阈值
HIGH_CERTAINTY_THRESHOLD = 0.80

# V6 UNCERTAIN 累积升级阈值
UNCERTAIN_ACCUMULATION_THRESHOLD = 3

# V6 长期未验证窗口（天）
SUSPECTED_STALE_LONG_TERM_DAYS = 30

# V6 长期未验证 confidence 惩罚
LONG_TERM_CONFIDENCE_PENALTY = 0.25

# V12 evidence 折扣系数（按 UNCERTAIN 次数）
EVIDENCE_DISCOUNT_BY_UNCERTAIN = {0: 1.0, 1: 1.0, 2: 0.80, 3: 0.60}

# 校准结果常量
CONSISTENT = "consistent"
INCONSISTENT = "inconsistent"
UNCERTAIN = "uncertain"


class CalibrationEvent:
    """校准触发事件。

    Attributes:
        event_type: 事件类型（E1-E8）。
        changed_files: 变更文件列表。
        git_diff: git diff 内容（可选）。
        triggered_at: 触发时间。
        metadata: 额外元数据。
    """

    def __init__(
        self,
        event_type: str,
        changed_files: list[str] | None = None,
        git_diff: str | None = None,
        triggered_at: dt.datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.event_type = event_type
        self.changed_files = changed_files or []
        self.git_diff = git_diff
        self.triggered_at = triggered_at or dt.datetime.now(dt.UTC)
        self.metadata = metadata or {}


class CalibrationResult:
    """单条知识的校准结果。

    Attributes:
        knowledge_id: 知识 ID。
        verdict: CONSISTENT / INCONSISTENT / UNCERTAIN。
        certainty: LLM 确定度 0.0-1.0。
        new_status: 校准后的新状态（可能不变）。
        new_confidence: 校准后的新 confidence（可能不变）。
        new_code_verified: 校准后的 code_verified。
        reason: 校准原因。
        evidence_discount: V12 evidence 折扣系数。
    """

    def __init__(
        self,
        knowledge_id: str,
        verdict: str,
        certainty: float = 0.5,
        new_status: str | None = None,
        new_confidence: float | None = None,
        new_code_verified: int | None = None,
        reason: str = "",
        evidence_discount: float = 1.0,
    ) -> None:
        self.knowledge_id = knowledge_id
        self.verdict = verdict
        self.certainty = certainty
        self.new_status = new_status
        self.new_confidence = new_confidence
        self.new_code_verified = new_code_verified
        self.reason = reason
        self.evidence_discount = evidence_discount

    def to_dict(self) -> dict[str, Any]:
        return {
            "knowledge_id": self.knowledge_id,
            "verdict": self.verdict,
            "certainty": self.certainty,
            "new_status": self.new_status,
            "new_confidence": self.new_confidence,
            "new_code_verified": self.new_code_verified,
            "reason": self.reason,
            "evidence_discount": self.evidence_discount,
        }


class CalibrationEngine:
    """校准引擎。

    监听触发事件，查找关联知识，执行 LLM 语义对比，应用 V6/V11/V12 修补。

    Args:
        sqlite_store: SQLiteStore 实例。
        llm_client: LLM 客户端实例。
        project_root: 项目根目录（用于读取代码文件）。
    """

    def __init__(
        self,
        sqlite_store: SQLiteStore,
        llm_client: LLMClient,
        project_root: str | Path | None = None,
    ) -> None:
        self.db = sqlite_store
        self.llm = llm_client
        self.project_root = Path(project_root) if project_root else None

    def trigger(self, event: CalibrationEvent) -> list[CalibrationResult]:
        """触发校准流程。

        Args:
            event: 校准触发事件。

        Returns:
            受影响知识的校准结果列表。
        """
        # 查找关联知识
        related = self.find_related_knowledge(event.changed_files)
        if not related:
            logger.info("No related knowledge for event %s", event.event_type)
            return []

        results: list[CalibrationResult] = []
        for record in related:
            try:
                result = self._calibrate_one(record, event)
                results.append(result)
            except Exception as e:
                logger.error("Calibration failed for %s: %s", record.get("id"), e)
                results.append(
                    CalibrationResult(
                        knowledge_id=record.get("id", ""),
                        verdict=UNCERTAIN,
                        reason=f"calibration error: {e}",
                    )
                )

        return results

    def find_related_knowledge(self, changed_files: list[str]) -> list[dict[str, Any]]:
        """查找与变更文件关联的知识。

        通过 concept_tags 中的 file 引用 + code_verified=1 的知识匹配。

        Args:
            changed_files: 变更文件路径列表。

        Returns:
            关联知识记录列表。
        """
        if not changed_files:
            return []
        conn = self.db.get_connection()
        # 查找 code_verified=1 的 ACTIVE/COLD/STALE 知识
        rows = conn.execute(
            "SELECT * FROM knowledge_index WHERE code_verified = 1 "
            "AND status IN ('active', 'cold', 'stale')"
        ).fetchall()
        columns = [d[0] for d in conn.execute("SELECT * FROM knowledge_index LIMIT 0").description]

        related: list[dict[str, Any]] = []
        for row in rows:
            record = dict(zip(columns, row, strict=False))
            # 检查 concept_tags 是否引用了变更文件
            tags_str = record.get("concept_tags", "")
            if tags_str:
                try:
                    tags = json.loads(tags_str)
                except (json.JSONDecodeError, TypeError):
                    tags = []
            else:
                tags = []
            # 简化匹配：concept_tags 中的 #名称 或文件名出现在变更文件中
            tag_names = [t.lstrip("#") for t in tags if isinstance(t, str)]
            for changed in changed_files:
                changed_basename = Path(changed).name
                changed_stem = Path(changed).stem
                if any(
                    t in changed or t == changed_stem or t == changed_basename for t in tag_names
                ):
                    related.append(record)
                    break

        return related

    def semantic_compare(
        self,
        knowledge_text: str,
        code_content: str,
        git_diff: str | None = None,
    ) -> dict[str, Any]:
        """LLM 语义对比：知识描述 vs 当前代码。

        Args:
            knowledge_text: 知识文本内容。
            code_content: 当前代码内容。
            git_diff: git diff（可选）。

        Returns:
            LLM 判断结果 dict：
            - ``verdict``: consistent / inconsistent / uncertain
            - ``certainty``: 0.0-1.0
            - ``explanation``: 判断依据
            - ``inconsistency_point``: 不一致点（INCONSISTENT 时）
        """
        diff_section = f"\n【代码变更 diff】\n{git_diff}\n" if git_diff else ""
        prompt = f"""你是代码-文档一致性检查器。判断知识描述是否仍然与代码现状一致。

【知识内容】
{knowledge_text}

【关联代码】
{code_content}
{diff_section}
请判断：知识描述是否仍然与代码现状一致？

输出 JSON：
{{
  "verdict": "consistent" | "inconsistent" | "uncertain",
  "certainty": 0.0-1.0,
  "explanation": "判断依据",
  "inconsistency_point": "不一致点（仅 inconsistent 时填）"
}}

注意：
- consistent: 代码重构但行为不变，知识仍正确
- inconsistent: 代码行为已改变，知识描述不再正确
- uncertain: 无法确定（逻辑太分散）
"""
        response = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        content = response["choices"][0]["message"]["content"]
        try:
            result: dict[str, Any] = json.loads(content)
        except json.JSONDecodeError:
            return {
                "verdict": UNCERTAIN,
                "certainty": 0.0,
                "explanation": "LLM output parse failed",
            }
        return result

    def _calibrate_one(self, record: dict[str, Any], event: CalibrationEvent) -> CalibrationResult:
        """校准单条知识。

        应用 V6/V11/V12/V18 修补。

        Args:
            record: 知识记录。
            event: 触发事件。

        Returns:
            校准结果。
        """
        kid = record["id"]
        current_status = record["status"]
        current_confidence = record.get("confidence", 0.0)
        uncertain_count = record.get("stale_check_count", 0)

        # 读取知识内容（从 uri 指向的 MD 文件）
        knowledge_text = self._read_knowledge_content(record)
        if not knowledge_text:
            return CalibrationResult(kid, UNCERTAIN, reason="knowledge content unreadable")

        # 读取关联代码内容
        code_content = self._read_code_content(record, event)
        if not code_content:
            return CalibrationResult(kid, UNCERTAIN, reason="code content unreadable")

        # LLM 语义对比
        judgment = self.semantic_compare(knowledge_text, code_content, event.git_diff)
        verdict = judgment.get("verdict", UNCERTAIN)
        certainty = float(judgment.get("certainty", 0.5))

        result = CalibrationResult(
            knowledge_id=kid,
            verdict=verdict,
            certainty=certainty,
            reason=judgment.get("explanation", ""),
        )

        # V18 certainty 分流
        if verdict == INCONSISTENT:
            if certainty >= HIGH_CERTAINTY_THRESHOLD:
                # T18: 高确定度 INCONSISTENT → 直接废弃
                result.new_status = "deprecated"
                result.reason = f"T18: high certainty ({certainty:.2f}) inconsistency → deprecated"
                self._apply_calibration(
                    kid,
                    {
                        "status": "deprecated",
                        "deprecation_reason": "direct_contradiction",
                        "code_verified": 0,
                        "calibration_status": "conflict",
                        "last_calibrated_at": dt.datetime.now(dt.UTC).isoformat(),
                    },
                )
            else:
                # T12: 低确定度 INCONSISTENT → STALE(suspicious) + V11 即时标记
                result.new_status = "stale"
                result.new_code_verified = 0
                result.reason = (
                    f"T12+V11: low certainty ({certainty:.2f}) inconsistency → stale(suspicious)"
                )
                new_count = uncertain_count + 1
                new_confidence = current_confidence * 0.80  # V19 累积折扣
                self._apply_calibration(
                    kid,
                    {
                        "status": "stale",
                        "code_verified": 0,
                        "stale_check_count": new_count,
                        "stale_sub_phase": "suspicious",
                        "stale_entered_at": dt.datetime.now(dt.UTC).isoformat(),
                        "confidence": new_confidence,
                        "calibration_status": "stale",
                        "last_calibrated_at": dt.datetime.now(dt.UTC).isoformat(),
                    },
                )
                result.new_confidence = new_confidence

        elif verdict == UNCERTAIN:
            # V6 三级响应
            new_count = uncertain_count + 1
            result.evidence_discount = EVIDENCE_DISCOUNT_BY_UNCERTAIN.get(new_count, 0.40)

            if new_count >= UNCERTAIN_ACCUMULATION_THRESHOLD:
                # V6 级 2：累积升级 → 移到 staging
                result.new_status = "staged"
                result.reason = f"V6: uncertain accumulated {new_count} times → staging"
                self._apply_calibration(
                    kid,
                    {
                        "status": "staged",
                        "stale_check_count": new_count,
                        "flag": "uncertain_accumulated",
                        "calibration_status": "uncertain",
                        "last_calibrated_at": dt.datetime.now(dt.UTC).isoformat(),
                    },
                )
            else:
                # V6 级 1：即时警告 → suspected_stale（保留 knowledge/ 但状态可疑）
                result.new_status = "stale"
                result.reason = f"V6: uncertain #{new_count} → suspected_stale"
                self._apply_calibration(
                    kid,
                    {
                        "status": "stale",
                        "stale_check_count": new_count,
                        "stale_sub_phase": "suspicious",
                        "stale_entered_at": dt.datetime.now(dt.UTC).isoformat(),
                        "flag": "suspected_stale",
                        "calibration_status": "uncertain",
                        "last_calibrated_at": dt.datetime.now(dt.UTC).isoformat(),
                    },
                )

        elif verdict == CONSISTENT:
            # 校准通过 → 更新 last_calibrated_at + code_verified=1
            result.reason = "consistent: knowledge still valid"
            self._apply_calibration(
                kid,
                {
                    "code_verified": 1,
                    "calibration_status": "verified",
                    "last_calibrated_at": dt.datetime.now(dt.UTC).isoformat(),
                },
            )
            # 如果之前是 STALE，恢复到 ACTIVE（T15）
            if current_status == "stale":
                result.new_status = "active"
                result.reason = "T15: stale→active (re-verified)"
                self._apply_calibration(
                    kid,
                    {
                        "status": "active",
                        "stale_check_count": 0,
                        "stale_sub_phase": None,
                        "stale_entered_at": None,
                        "flag": None,
                    },
                )

        return result

    def _read_knowledge_content(self, record: dict[str, Any]) -> str:
        """从 MD 文件读取知识内容。"""
        uri = record.get("uri", "")
        if not uri:
            return ""
        path = Path(uri)
        if not path.exists():
            return ""
        content = path.read_text(encoding="utf-8")
        # 提取 frontmatter 之后的正文
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                return parts[2].strip()
        return content

    def _read_code_content(self, record: dict[str, Any], event: CalibrationEvent) -> str:
        """读取关联代码内容。"""
        if not self.project_root or not event.changed_files:
            return ""
        # 读取第一个匹配的变更文件
        for changed in event.changed_files:
            path = self.project_root / changed
            if path.exists():
                try:
                    return path.read_text(encoding="utf-8")[:8000]  # 截断防止 token 超限
                except OSError:
                    continue
        return ""

    def _apply_calibration(self, kid: str, updates: dict[str, Any]) -> None:
        """应用校准结果到 DB。"""
        if not updates:
            return
        conn = self.db.get_connection()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE knowledge_index SET {set_clause} WHERE id = ?",
            [*updates.values(), kid],
        )
        conn.commit()
