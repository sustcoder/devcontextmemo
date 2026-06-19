"""Step 3: 签名 + 语义验证 + code_verified 设置。

职责：
1. 读取 knowledge JSONL（Step 2b 输出）
2. 对每条知识计算 content_hash（SHA-256 精确哈希）+ semantic_hash（SimHash 语义签名）
3. 设置 code_verified：entities 中含至少一个 file 字段 → 1，否则 → 0
4. 输出更新后的 knowledge JSONL（添加 hash + code_verified 字段）

设计决策（Phase 4 Q3）：
- content_hash/semantic_hash 仅作 JSONL 中间态（Step 3→4 流转用）
- DB 的 knowledge_index 表无 content_hash 字段（Phase 2 Q2 严格按 schema）

输出格式（knowledge JSONL，每行一条，新增字段）：
    {..., "content_hash": "abc123...", "semantic_hash": "a1b2c3...",
     "code_verified": 1}

设计依据：``docs/devContextMemo-数据写入流水线-详细设计-V1.0.md`` §五（Step 3）
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from devcontext.utils.hash import content_hash, semantic_hash

logger = logging.getLogger(__name__)


class Validator:
    """Step 3 验证器。

    计算内容签名 + 设置 code_verified 标志。

    Args:
        staging_dir: 输出目录（与输入同目录，输出文件名加 _validated 后缀）。
    """

    def __init__(self, staging_dir: str | Path) -> None:
        self.staging_dir = Path(staging_dir)

    def process(self, knowledge_path: str | Path) -> Path:
        """处理 knowledge JSONL，添加 hash + code_verified 字段。

        Args:
            knowledge_path: knowledge JSONL 文件路径（Step 2b 输出）。

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

        validated: list[dict[str, Any]] = []
        for rec in records:
            validated_rec = self._validate_record(rec)
            validated.append(validated_rec)

        # 输出文件（覆盖原文件或写新文件）
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.staging_dir / knowledge_path.name
        self._write_jsonl(output_path, validated)

        logger.info(
            "Validated %d knowledge items → %s",
            len(validated),
            output_path,
        )
        return output_path

    @staticmethod
    def _validate_record(record: dict[str, Any]) -> dict[str, Any]:
        """验证单条记录：计算 hash + 设置 code_verified。

        Args:
            record: knowledge 记录。

        Returns:
            添加了 content_hash/semantic_hash/code_verified 的记录。
        """
        result = dict(record)
        knowledge_text = record.get("knowledge_text", "")

        # 计算 hash
        result["content_hash"] = content_hash(knowledge_text)
        result["semantic_hash"] = semantic_hash(knowledge_text)

        # 设置 code_verified：entities 含至少一个 file 字段
        entities = record.get("entities", [])
        has_file = any(isinstance(e, dict) and e.get("file") for e in entities)
        result["code_verified"] = 1 if has_file else 0

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
