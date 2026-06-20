"""Step 2b: 实体 + 关系提取。

职责：
1. 读取 summary JSONL（Step 2a 输出）
2. 对每条知识调用 LLM 提取实体（class/method/file 等）+ 关系（extends/uses 等）
3. 实体归一化（去重 + 大小写统一）
4. 输出 knowledge JSONL（Step 3 输入，在 summary 基础上添加 entities/relations）

实体类型（step2b 契约）：
    class, interface, method, function, module, file, config_file,
    pattern, concept, tool, service, database, api, other

关系类型（step2b 契约）：
    extends, implements, uses, depends_on, handles, configures,
    belongs_to, triggers, calls, references

输出格式（knowledge JSONL，每行一条）：
    {"session_id": "...", "knowledge_text": "...", "granularity": "L2",
     "stability": "S3", "depth": "KH", "domain": "order",
     "confidence": 0.88, "occurred_at": "...", "source_messages": [2],
     "status": "staged",
     "entities": [{"name": "OrderService", "type": "class", "file": "src/OrderService.java"}],
     "relations": [{"source": "OrderService", "target": "IdempotentChecker", "type": "uses"}]}

设计依据：``docs/devContextMemo-数据写入流水线-详细设计-V1.0.md`` §四
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from devcontext.utils.llm import LLMClient

logger = logging.getLogger(__name__)

# 合法实体类型
_VALID_ENTITY_TYPES = frozenset(
    {
        "class",
        "interface",
        "method",
        "function",
        "module",
        "file",
        "config_file",
        "pattern",
        "concept",
        "tool",
        "service",
        "database",
        "api",
        "library",
        "other",
    }
)

# 合法关系类型
_VALID_RELATION_TYPES = frozenset(
    {
        "extends",
        "implements",
        "uses",
        "depends_on",
        "handles",
        "configures",
        "belongs_to",
        "triggers",
        "calls",
        "references",
    }
)

# 最大重试次数
_MAX_RETRIES = 3


class EntityExtractor:
    """Step 2b 实体 + 关系提取器。

    对每条知识调用 LLM 提取结构化实体和关系，归一化后输出 knowledge JSONL。

    Args:
        llm_client: LLM 客户端实例。
        staging_dir: knowledge JSONL 输出目录。
        model: LLM 模型名（可选）。
    """

    def __init__(
        self,
        llm_client: LLMClient,
        staging_dir: str | Path,
        model: str | None = None,
    ) -> None:
        self.llm = llm_client
        self.staging_dir = Path(staging_dir)
        self.model = model

    def process(self, summary_path: str | Path) -> Path:
        """处理 summary JSONL，输出 knowledge JSONL。

        Args:
            summary_path: summary JSONL 文件路径（Step 2a 输出）。

        Returns:
            knowledge JSONL 文件路径。

        Raises:
            FileNotFoundError: summary 文件不存在。
            ValueError: LLM 输出 3 次重试均失败。
        """
        summary_path = Path(summary_path)
        if not summary_path.exists():
            raise FileNotFoundError(f"Summary file not found: {summary_path}")

        summaries = self._read_jsonl(summary_path)
        if not summaries:
            raise ValueError(f"Summary file is empty: {summary_path}")

        session_id = summaries[0].get("session_id", "unknown")
        knowledge_records: list[dict[str, Any]] = []

        for summary in summaries:
            entities, relations = self._extract_for_item(summary)
            decision_detail = self._extract_decision_detail(summary)
            record = {**summary, "entities": entities, "relations": relations}
            if decision_detail:
                record["decision_detail"] = decision_detail
            knowledge_records.append(record)

        # 写 knowledge JSONL
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.staging_dir / f"knowledge_{session_id}.jsonl"
        self._write_jsonl(output_path, knowledge_records)

        logger.info(
            "Extracted entities for %d items from session %s → %s",
            len(knowledge_records),
            session_id,
            output_path,
        )
        return output_path

    # ------------------------------------------------------------------
    # LLM 调用 + 解析
    # ------------------------------------------------------------------

    def _extract_for_item(
        self, summary: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """对单条知识提取实体 + 关系（含重试）。

        Args:
            summary: summary 记录。

        Returns:
            (entities, relations) 元组。
        """
        knowledge_text = summary.get("knowledge_text", "")
        prompt = self._build_prompt(knowledge_text)

        system_prompt = "你是 devContextMemo 的实体关系提取器，只输出 JSON。"
        last_error: str = ""

        for attempt in range(_MAX_RETRIES):
            try:
                response = self.llm.chat(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    model=self.model,
                    temperature=0.2,
                    response_format={"type": "json_object"},
                )
                content = response["choices"][0]["message"]["content"]
                entities, relations = self._parse_and_validate(content)
                return entities, relations

            except (json.JSONDecodeError, ValueError, KeyError) as e:
                last_error = str(e)
                logger.warning(
                    "Entity extraction attempt %d/%d failed: %s",
                    attempt + 1,
                    _MAX_RETRIES,
                    e,
                )
                if attempt < _MAX_RETRIES - 1:
                    prompt += (
                        "\n\n[上次输出格式错误，请严格按 JSON schema 返回。" f"错误：{last_error}]"
                    )

        # 3 次失败 → 返回空实体/关系（优雅降级，不阻断流水线）
        logger.error(
            "Entity extraction failed after %d attempts, using empty entities: %s",
            _MAX_RETRIES,
            last_error,
        )
        return [], []

    @staticmethod
    def _build_prompt(knowledge_text: str) -> str:
        """构建实体关系提取 Prompt。

        Args:
            knowledge_text: 知识文本。

        Returns:
            Prompt 字符串。
        """
        return f"""从以下知识条目中提取实体和关系。

实体类型：class, interface, method, function, module, file, config_file, pattern, concept, tool, service, database, api, other

关系类型：extends, implements, uses, depends_on, handles, configures, belongs_to, triggers, calls, references

输出 JSON 格式：
{{
  "entities": [
    {{"name": "OrderService", "type": "class", "file": "src/OrderService.java"}}
  ],
  "relations": [
    {{"source": "OrderService", "target": "IdempotentChecker", "type": "uses"}}
  ]
}}

注意：
- entities 和 relations 可以为空数组 []
- 每个实体必须有 name 和 type，file 可选
- 关系的 source 必须是 entities 中已定义的实体名
- 实体名需归一化（同一实体只出现一次）

【知识条目】
{knowledge_text}
"""

    def _parse_and_validate(
        self, content: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """解析 + 校验 LLM 输出。

        Args:
            content: LLM 返回的 JSON 字符串。

        Returns:
            (entities, relations) 元组。

        Raises:
            json.JSONDecodeError: JSON 解析失败。
            ValueError: 字段缺失或值非法。
        """
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("LLM output must be a JSON object")

        raw_entities = data.get("entities", [])
        if not isinstance(raw_entities, list):
            raise ValueError("'entities' must be a list")

        raw_relations = data.get("relations", [])
        if not isinstance(raw_relations, list):
            raise ValueError("'relations' must be a list")

        # 校验 + 归一化实体
        entities: list[dict[str, Any]] = []
        entity_names: set[str] = set()
        for i, ent in enumerate(raw_entities):
            if not isinstance(ent, dict):
                raise ValueError(f"Entity {i} is not a dict")
            name = str(ent.get("name", "")).strip()
            if not name:
                raise ValueError(f"Entity {i} name is empty")
            ent_type = str(ent.get("type", "")).strip()
            if ent_type not in _VALID_ENTITY_TYPES:
                raise ValueError(
                    f"Entity {i} invalid type: {ent_type!r} "
                    f"(must be one of {sorted(_VALID_ENTITY_TYPES)})"
                )
            # 归一化：去重（同名实体保留第一个）
            if name in entity_names:
                continue
            entity_names.add(name)
            entity: dict[str, Any] = {"name": name, "type": ent_type}
            if "file" in ent and ent["file"]:
                entity["file"] = str(ent["file"])
            entities.append(entity)

        # 校验关系
        relations: list[dict[str, Any]] = []
        for i, rel in enumerate(raw_relations):
            if not isinstance(rel, dict):
                raise ValueError(f"Relation {i} is not a dict")
            source = str(rel.get("source", "")).strip()
            if not source:
                raise ValueError(f"Relation {i} source is empty")
            if source not in entity_names:
                raise ValueError(f"Relation {i} source {source!r} not in entities")
            target = str(rel.get("target", "")).strip()
            if not target:
                raise ValueError(f"Relation {i} target is empty")
            rel_type = str(rel.get("type", "")).strip()
            if rel_type not in _VALID_RELATION_TYPES:
                raise ValueError(
                    f"Relation {i} invalid type: {rel_type!r} "
                    f"(must be one of {sorted(_VALID_RELATION_TYPES)})"
                )
            relations.append({"source": source, "target": target, "type": rel_type})

        return entities, relations

    # ------------------------------------------------------------------
    # 决策详情提取
    # ------------------------------------------------------------------

    def _extract_decision_detail(
        self, summary: dict[str, Any]
    ) -> dict[str, Any] | None:
        """对 decision 类型条目提取 4 个决策详情字段。

        仅 knowledge_type=decision 时触发，非 decision 返回 None（零增量）。

        Args:
            summary: summary 记录（含 knowledge_type 字段）。

        Returns:
            含 decision_context/options/rationale/consequence 的 dict，或 None。
        """
        knowledge_type = summary.get("knowledge_type", "")
        if knowledge_type != "decision":
            return None

        knowledge_text = summary.get("knowledge_text", "")
        prompt = self._build_decision_prompt(knowledge_text)
        system_prompt = "你是 devContextMemo 的决策详情提取器，只输出 JSON。"

        for attempt in range(_MAX_RETRIES):
            try:
                response = self.llm.chat(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    model=self.model,
                    temperature=0.2,
                    response_format={"type": "json_object"},
                )
                content = response["choices"][0]["message"]["content"]
                detail = json.loads(content)
                self._validate_decision_detail(detail)
                return detail

            except (json.JSONDecodeError, ValueError, KeyError) as e:
                logger.warning(
                    "Decision extraction attempt %d/%d failed: %s",
                    attempt + 1,
                    _MAX_RETRIES,
                    e,
                )
                if attempt < _MAX_RETRIES - 1:
                    prompt += (
                        f"\n\n[上次输出格式错误，请严格按 JSON schema 返回。错误：{e}]"
                    )

        logger.error("Decision extraction failed after %d attempts", _MAX_RETRIES)
        return None

    @staticmethod
    def _build_decision_prompt(knowledge_text: str) -> str:
        """构建决策详情提取 Prompt。

        Args:
            knowledge_text: 知识文本。

        Returns:
            Prompt 字符串。
        """
        return f"""从以下决策知识中提取 4 个结构化字段。

输出 JSON 格式：
{{
  "decision_context": "为什么需要做这个决策（背景描述）",
  "decision_options": ["选项A", "选项B", "选项C"],
  "decision_rationale": "选择理由（为什么选这个而不是别的）",
  "decision_consequence": "预期后果/影响"
}}

注意：
- decision_options 必须包含至少 2 个选项
- 如果无法推断某个字段，设为空字符串或空数组
- decision_context/rationale/consequence 为字符串，options 为字符串数组

【决策知识】
{knowledge_text}
"""

    @staticmethod
    def _validate_decision_detail(detail: dict[str, Any]) -> None:
        """校验决策详情结构。

        Args:
            detail: LLM 输出的决策详情 dict。

        Raises:
            ValueError: 字段缺失或类型错误。
        """
        required = {"decision_context", "decision_options", "decision_rationale", "decision_consequence"}
        missing = required - set(detail.keys())
        if missing:
            raise ValueError(f"Missing decision detail fields: {missing}")
        if not isinstance(detail["decision_options"], list):
            raise ValueError("decision_options must be a list")
        if len(detail["decision_options"]) < 2:
            raise ValueError("decision_options must have at least 2 options")

    # ------------------------------------------------------------------
    # IO 工具
    # ------------------------------------------------------------------

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
