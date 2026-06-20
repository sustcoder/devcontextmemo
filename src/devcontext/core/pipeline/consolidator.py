"""Step 6: 晋升 + 修剪 + 巩固（dev dream）。

职责：
1. 扫描 knowledge_index 全表
2. 对每条知识：
   - 计算 V2.1 晋升评分
   - 评估 promotion（T3/T4/T5/T6）+ pruning（T11/T14/T16/T19/T25）
   - 校验状态迁移合法性（is_valid_transition）
   - 更新 DB status + 相关字段
   - 物理文件移动（staging→knowledge→deprecated）
3. 输出巩固报告

触发方式：
    - dev dream（手动）
    - auto-dream（每 7 天）
    - 事件驱动（每次提炼完成后异步）

设计依据：``docs/devContextMemo-晋升生命周期-设计-V2.0.md``
"""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import Any

from devcontext.core.promotion import (
    calculate_base_score,
    compute_anchor_bonus,
    compute_calibration_recency,
    evaluate_promotion,
    evaluate_stale_transition,
    restore_from_stale,
)
from devcontext.core.pruning import (
    check_capacity,
    evaluate_layer1,
    evaluate_layer2,
    evaluate_layer3,
)
from devcontext.models.enums import is_valid_transition
from devcontext.storage.markdown import MarkdownStore
from devcontext.storage.sqlite import SQLiteStore

logger = logging.getLogger(__name__)


_BATCH_SIZE = 500  # 分页大小，防止全表加载 OOM


class ConsolidationReport:
    """巩固报告。

    Attributes:
        total_scanned: 扫描总数。
        promotions: 晋升数（staged→candidate/pending_review/draft, candidate→active）。
        pruned: 修剪数（→deprecated）。
        stale_marked: 标记 STALE 数。
        cold_marked: 标记 COLD 数。
        moved_files: 移动文件数。
        errors: 错误数。
        details: 每条知识的决策详情。
    """

    def __init__(self) -> None:
        self.total_scanned = 0
        self.promotions = 0
        self.pruned = 0
        self.stale_marked = 0
        self.cold_marked = 0
        self.moved_files = 0
        self.errors = 0
        self.details: list[dict[str, Any]] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_scanned": self.total_scanned,
            "promotions": self.promotions,
            "pruned": self.pruned,
            "stale_marked": self.stale_marked,
            "cold_marked": self.cold_marked,
            "moved_files": self.moved_files,
            "errors": self.errors,
            "details": self.details,
        }

    def __repr__(self) -> str:
        return (
            f"ConsolidationReport(scanned={self.total_scanned}, "
            f"promotions={self.promotions}, pruned={self.pruned}, "
            f"stale={self.stale_marked}, cold={self.cold_marked}, "
            f"moved={self.moved_files}, errors={self.errors})"
        )


class Consolidator:
    """Step 6 巩固器。

    批量评估知识库中所有知识，执行晋升/修剪/状态迁移。

    Args:
        sqlite_store: SQLiteStore 实例。
        markdown_store: MarkdownStore 实例（用于文件移动）。
        dry_run: True 表示只评估不实际修改（预览模式）。
    """

    def __init__(
        self,
        sqlite_store: SQLiteStore,
        markdown_store: MarkdownStore | None = None,
        dry_run: bool = False,
    ) -> None:
        self.db = sqlite_store
        self.md_store = markdown_store
        self.dry_run = dry_run

    def process(self) -> ConsolidationReport:
        """执行巩固流程。

        Returns:
            ConsolidationReport 巩固报告。
        """
        report = ConsolidationReport()
        conn = self.db.get_connection()

        # 扫描全表 — 分页处理防止大量数据 OOM
        columns = [
            desc[0] for desc in conn.execute("SELECT * FROM knowledge_index LIMIT 0").description
        ]
        offset = 0
        while True:
            rows = conn.execute(
                "SELECT * FROM knowledge_index ORDER BY created_at LIMIT ? OFFSET ?",
                (_BATCH_SIZE, offset),
            ).fetchall()
            if not rows:
                break
            report.total_scanned += len(rows)

            # 容量检查（首次批次）
            if offset == 0:
                check_capacity(len(rows))

            for row in rows:
                record = dict(zip(columns, row, strict=False))
                try:
                    detail = self._process_record(record, report)
                    report.details.append(detail)
                except Exception as e:
                    logger.warning("Skipping record %s: %s", record.get("id"), e)
                    report.errors += 1

            offset += _BATCH_SIZE

        logger.info("Consolidation complete: %s", report)
        return report

    def _process_record(
        self, record: dict[str, Any], report: ConsolidationReport
    ) -> dict[str, Any]:
        """处理单条知识。

        Args:
            record: knowledge_index 记录。
            report: 巩固报告（用于累加统计）。

        Returns:
            决策详情 dict。
        """
        kid = record["id"]
        current_status = record["status"]
        confidence = record.get("confidence", 0.0)
        code_verified = record.get("code_verified", 0)
        last_calibrated = record.get("last_calibrated_at")
        locked_score = record.get("locked_promotion_score")
        record.get("stale_check_count", 0)

        detail: dict[str, Any] = {
            "id": kid,
            "old_status": current_status,
            "confidence": confidence,
        }

        # 1. 计算 V2.1 评分
        anchor_bonus = compute_anchor_bonus(code_verified)
        cal_recency = compute_calibration_recency(last_calibrated)
        base_score = calculate_base_score(confidence, anchor_bonus, cal_recency)
        detail["base_score"] = round(base_score, 4)

        # 2. 评估修剪（优先于晋升，V2.0 §6.6）
        prune_action = self._evaluate_pruning(record, report)
        if prune_action is not None:
            detail.update(prune_action)
            if not self.dry_run:
                self._apply_pruning(record, prune_action, report)
            return detail

        # 3. 评估晋升
        promo = evaluate_promotion(
            base_score=base_score,
            current_status=current_status,
            confidence=confidence,
            locked_score=locked_score,
        )
        detail["promotion"] = promo

        new_status = promo["new_status"]
        if new_status != current_status:
            if is_valid_transition(current_status, new_status):
                report.promotions += 1
                detail["new_status"] = new_status
                detail["transition"] = promo.get("transition")
                if not self.dry_run:
                    self._apply_promotion(record, promo, base_score, report)
            else:
                logger.warning(
                    "Invalid transition %s→%s for %s, skipping",
                    current_status,
                    new_status,
                    kid,
                )
                detail["new_status"] = current_status
                detail["transition"] = None
                detail["reason"] = "invalid transition blocked"
        else:
            detail["new_status"] = current_status

        return detail

    def _evaluate_pruning(
        self, record: dict[str, Any], report: ConsolidationReport
    ) -> dict[str, Any] | None:
        """评估修剪规则。

        优先级：Layer1 > Layer2 > Layer3（V2.0 §6.6）。

        Args:
            record: knowledge_index 记录。
            report: 巩固报告。

        Returns:
            修剪决策 dict（有动作时），或 None（无修剪动作）。
        """
        status = record["status"]
        now = dt.datetime.now(dt.UTC)

        # 计算天数
        created_at = self._parse_dt(record.get("created_at"))
        last_used = record.get("last_used_at")
        days_since_created = (now - created_at).days if created_at else 0
        days_since_last_used = None
        if last_used:
            last_used_dt = self._parse_dt(last_used)
            if last_used_dt:
                days_since_last_used = (now - last_used_dt).days

        confidence = record.get("confidence", 0.0)
        prune_priority = record.get("prune_priority", 0.0)
        code_verified = record.get("code_verified", 0)
        stale_count = record.get("stale_check_count", 0)

        # Layer 1: DRAFT 质量下限 (T19)
        l1 = evaluate_layer1(status, days_since_created, confidence)
        if l1["action"] == "DEPRECATE":
            report.pruned += 1
            return {
                "prune_action": "DEPRECATE",
                "prune_reason": l1["reason"],
                "deprecation_reason": l1["deprecation_reason"],
                "new_status": "deprecated",
            }

        # Layer 2: 使用频率 (T11/T13)
        l2 = evaluate_layer2(
            status,
            days_since_last_used,
            prune_priority,
            code_verified,
        )
        if l2["action"] == "MARK_COLD":
            report.cold_marked += 1
            return {
                "prune_action": "MARK_COLD",
                "prune_reason": l2["reason"],
                "new_status": "cold",
            }
        if l2["action"] == "MARK_STALE":
            report.stale_marked += 1
            return {
                "prune_action": "MARK_STALE",
                "prune_reason": l2["reason"],
                "new_status": "stale",
                "sub_phase": l2.get("sub_stage", "suspicious"),
            }

        # Layer 3: 代码锚点 (T14/T25)
        l3 = evaluate_layer3(
            status,
            has_anchor=bool(code_verified),
            days_unchanged=days_since_created,
            age_days=days_since_created,
            prune_priority=prune_priority,
            used_count=record.get("used_count", 0),
        )
        if l3["action"] == "MARK_STALE":
            report.stale_marked += 1
            return {
                "prune_action": "MARK_STALE",
                "prune_reason": l3["reason"],
                "new_status": "stale",
                "sub_phase": l3.get("sub_stage", "suspicious"),
                "flag": l3.get("flag"),
            }

        # STALE(deep) → DEPRECATED (T16)
        if status == "stale" and stale_count >= 3:
            report.pruned += 1
            return {
                "prune_action": "DEPRECATE",
                "prune_reason": f"T16: stale_check_count {stale_count} >= 3",
                "deprecation_reason": "verification_failed",
                "new_status": "deprecated",
            }

        return None

    def _apply_promotion(
        self,
        record: dict[str, Any],
        promo: dict[str, Any],
        base_score: float,
        report: ConsolidationReport,
    ) -> None:
        """应用晋升决策到 DB + 文件移动。"""
        kid = record["id"]
        new_status = promo["new_status"]
        self.db.get_connection()
        now = dt.datetime.now(dt.UTC).isoformat()

        updates: dict[str, Any] = {"status": new_status, "updated_at": now}

        # CANDIDATE 进入时锁定 score（T3）
        if new_status == "candidate" and record.get("locked_promotion_score") is None:
            updates["locked_promotion_score"] = base_score

        # ACTIVE 恢复时重置 STALE 字段
        if new_status == "active" and record["status"] == "stale":
            restore_from_stale(record.get("confidence", 0.0))
            updates["stale_check_count"] = 0
            updates["stale_sub_phase"] = None
            updates["stale_entered_at"] = None

        self._update_db(kid, updates)

        # 文件移动
        if promo.get("should_move_file") and self.md_store:
            self._move_file(record, new_status, report)

    def _apply_pruning(
        self,
        record: dict[str, Any],
        prune_action: dict[str, Any],
        report: ConsolidationReport,
    ) -> None:
        """应用修剪决策到 DB + 文件移动。"""
        kid = record["id"]
        new_status = prune_action["new_status"]
        self.db.get_connection()
        now = dt.datetime.now(dt.UTC).isoformat()

        updates: dict[str, Any] = {"status": new_status, "updated_at": now}

        if new_status == "deprecated":
            updates["deprecation_reason"] = prune_action.get("deprecation_reason", "unknown")
        elif new_status == "stale":
            stale_count = record.get("stale_check_count", 0) + 1
            updates["stale_check_count"] = stale_count
            updates["stale_sub_phase"] = prune_action.get("sub_phase", "suspicious")
            updates["stale_entered_at"] = now
            if prune_action.get("flag"):
                updates["flag"] = prune_action["flag"]
            # STALE 置信度折扣
            original_conf = record.get("confidence", 0.0)
            stale_eval = evaluate_stale_transition(
                stale_count - 1,
                original_conf,
                original_conf,
            )
            updates["confidence"] = stale_eval["new_confidence"]
        elif new_status == "cold":
            pass  # 仅状态变更

        self._update_db(kid, updates)

        # 文件移动到 deprecated/
        if new_status == "deprecated" and self.md_store:
            self._move_file(record, new_status, report)

    def _move_file(
        self,
        record: dict[str, Any],
        new_status: str,
        report: ConsolidationReport,
    ) -> None:
        """物理移动 MD 文件。"""
        uri = record.get("uri", "")
        if not uri:
            return
        src = Path(uri)
        if not src.exists():
            logger.warning("MD file not found for move: %s", src)
            return

        # 根据新状态决定目标目录
        if new_status in ("active", "cold", "stale"):
            # staging → knowledge/{domain}/
            domain = record.get("domain", "uncategorized")
            dest_dir = self.md_store.knowledge_dir / domain
        elif new_status == "deprecated":
            dest_dir = self.md_store.deprecated_dir
        else:
            return  # staging 内部状态不移动

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name

        try:
            src.rename(dest)
            # 更新 DB 中的 uri
            self._update_db(record["id"], {"uri": str(dest)})
            report.moved_files += 1
            logger.info("Moved %s → %s", src, dest)
        except OSError as e:
            logger.error("Failed to move %s: %s", src, e)

    def _update_db(self, kid: str, updates: dict[str, Any]) -> None:
        """更新 knowledge_index 记录。"""
        if not updates:
            return
        conn = self.db.get_connection()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE knowledge_index SET {set_clause} WHERE id = ?",
            [*updates.values(), kid],
        )
        conn.commit()

    @staticmethod
    def _parse_dt(dt_str: str | None) -> dt.datetime | None:
        """解析 ISO 8601 时间字符串。"""
        if not dt_str:
            return None
        try:
            parsed = dt.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.UTC)
            return parsed
        except (ValueError, TypeError):
            return None
