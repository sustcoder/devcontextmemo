"""Step 4: Jaccard + 语义去重。

职责：
1. 读取 knowledge JSONL（Step 3 输出，含 content_hash/semantic_hash/code_verified）
2. 对每条新知识与已有知识库比对：
   - content_hash 精确匹配 → 重复（skip）
   - jaccard_similarity ≥ 0.90 → 高度相似（标记 top_similar_id）
   - jaccard_similarity ≤ 0.30 → 足够不同（top_similar_id = null）
3. 预留 embedding/cosine 接口（Phase 5/6 接入 embedding 模型后实现）
4. 输出更新后的 knowledge JSONL（添加 top_similar_id/jaccard_score 字段）

设计决策（Phase 4 Q4）：
- 使用 SimHash + Jaccard（纯确定性算法，无需 embedding 模型）
- embedding/cosine 预留接口，后续 Phase 接入

输出格式（knowledge JSONL，每行一条，新增字段）：
    {..., "top_similar_id": "kw-001" | null, "jaccard_score": 0.85}

设计依据：``docs/devContextMemo-数据写入流水线-详细设计-V1.0.md`` §六（Step 4）
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from devcontext.utils.hash import content_hash, jaccard_similarity

logger = logging.getLogger(__name__)

# Jaccard 阈值
_DUPLICATE_THRESHOLD = 0.90  # ≥ 0.90 → 高度相似
_DIFFERENT_THRESHOLD = 0.30  # ≤ 0.30 → 足够不同


class Deduplicator:
    """Step 4 去重器。

    对新知识与已有知识库比对，标记重复/相似/全新。

    Args:
        staging_dir: 输出目录。
        existing_records: 已有知识记录列表（含 id + knowledge_text）。
                         若为空则所有新知识都是全新的。
    """

    def __init__(
        self,
        staging_dir: str | Path,
        existing_records: list[dict[str, Any]] | None = None,
    ) -> None:
        self.staging_dir = Path(staging_dir)
        self.existing_records = existing_records or []
        # 预计算已有知识的 content_hash 用于精确匹配
        self._existing_hashes: dict[str, str] = {
            rec.get("id", ""): rec.get("content_hash")
            or content_hash(rec.get("knowledge_text", ""))
            for rec in self.existing_records
        }

    def process(self, knowledge_path: str | Path) -> Path:
        """处理 knowledge JSONL，添加去重字段。

        Args:
            knowledge_path: knowledge JSONL 文件路径（Step 3 输出）。

        Returns:
            更新后的 knowledge JSONL 文件路径。

        Raises:
            FileNotFoundError: 文件不存在。
            ValueError: 文件为空。
        """
        knowledge_path = Path(knowledge_path)
        if not knowledge_path.exists():
            raise FileNotFoundError(f"Knowledge file not found: {knowledge_path}")

        records = self._read_jsonl(knowledge_path)
        if not records:
            raise ValueError(f"Knowledge file is empty: {knowledge_path}")

        deduplicated: list[dict[str, Any]] = []
        for rec in records:
            dedup_rec = self._deduplicate_record(rec)
            deduplicated.append(dedup_rec)

        self.staging_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.staging_dir / knowledge_path.name
        self._write_jsonl(output_path, deduplicated)

        logger.info("Deduplicated %d items → %s", len(deduplicated), output_path)
        return output_path

    def _deduplicate_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """对单条记录去重。

        Args:
            record: knowledge 记录（含 content_hash/semantic_hash）。

        Returns:
            添加了 top_similar_id/jaccard_score 的记录。
        """
        result = dict(record)
        new_hash = record.get("content_hash", "")
        new_text = record.get("knowledge_text", "")

        # ① content_hash 精确匹配 → 重复
        for existing_id, existing_hash in self._existing_hashes.items():
            if new_hash == existing_hash and new_hash:
                result["top_similar_id"] = existing_id
                result["jaccard_score"] = 1.0
                result["is_duplicate"] = True
                return result

        # ② Jaccard 相似度比对
        best_id: str | None = None
        best_score = 0.0
        for existing in self.existing_records:
            existing_text = existing.get("knowledge_text", "")
            if not existing_text:
                continue
            score = jaccard_similarity(new_text, existing_text)
            if score > best_score:
                best_score = score
                best_id = existing.get("id")

        result["jaccard_score"] = round(best_score, 4)
        if best_score >= _DUPLICATE_THRESHOLD and best_id:
            result["top_similar_id"] = best_id
            result["is_duplicate"] = True
        elif best_score <= _DIFFERENT_THRESHOLD or best_id is None:
            result["top_similar_id"] = None
            result["is_duplicate"] = False
        else:
            # 中间区间：标记相似但不视为重复
            result["top_similar_id"] = best_id
            result["is_duplicate"] = False

        return result

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        """读取 JSONL 文件。"""
        records: list[dict[str, Any]] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    @staticmethod
    def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
        """写入 JSONL 文件。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
