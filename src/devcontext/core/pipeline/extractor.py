"""Step 2a: LLM 知识提炼 — 分类 + 时间提取。

职责：
1. 读取 batch JSONL（Step 1 输出）
2. 构造 Prompt → 调用 LLM → 解析 JSON 输出
3. 校验四轴分类（granularity L0-L5 / stability S1-S5 / depth KW-KH-KY / domain）
4. 提取 occurred_at 时间（显式/推断/无法推断为 null）
5. 输出 summary JSONL（Step 2b 输入）

设计原则（流水线设计 V1.0 §4.1）：
- LLM 只做 ADD-only 提取，不做去重/合并决策
- LLM 输出经严格校验，非法值重试（最多 3 次）
- 空数组 [] 允许（本次无知识可提炼）

输出格式（summary JSONL，每行一条）：
    {"session_id": "...", "knowledge_text": "...", "granularity": "L2",
     "stability": "S3", "depth": "KH", "domain": "order",
     "confidence": 0.88, "occurred_at": "2026-06-18T10:01:00Z",
     "source_messages": [2]}

设计依据：``docs/devContextMemo-数据写入流水线-详细设计-V1.0.md`` §四（Step 2）
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from devcontext.models.enums import is_valid_depth, is_valid_domain, is_valid_knowledge_type, is_valid_lx, is_valid_sy
from devcontext.utils.llm import LLMClient

logger = logging.getLogger(__name__)

# LLM 输出校验：必填字段
_REQUIRED_ITEM_FIELDS = (
    "content",
    "granularity",
    "stability",
    "depth",
    "domain",
    "knowledge_type",
    "confidence",
)

# 最大重试次数
_MAX_RETRIES = 3

# 置信度范围
_CONFIDENCE_MIN = 0.0
_CONFIDENCE_MAX = 1.0

# LLM 最大上下文 token（设计文档 §4.3：32K）
_MAX_CONTEXT_TOKENS = 32000

# 截断后保留的目标 token（留 4K 余量给 Prompt + 输出）
_TARGET_TOKENS_AFTER_TRUNCATION = 28000


class Extractor:
    """Step 2a 知识提炼器。

    通过 LLM 从对话 batch 中提取结构化知识条目，标注四轴分类 + 时间。

    Args:
        llm_client: LLM 客户端实例。
        domain_tree: 领域树 dict（如 ``{"order": {...}, "payment": {...}}``）。
        staging_dir: summary JSONL 输出目录。
        model: LLM 模型名（可选，用 llm_client 默认）。
    """

    def __init__(
        self,
        llm_client: LLMClient,
        domain_tree: dict[str, Any],
        staging_dir: str | Path,
        model: str | None = None,
    ) -> None:
        self.llm = llm_client
        self.domain_tree = domain_tree
        self.staging_dir = Path(staging_dir)
        self.model = model

    def process(self, batch_path: str | Path) -> Path:
        """处理 batch JSONL，输出 summary JSONL。

        Args:
            batch_path: batch JSONL 文件路径（Step 1 输出）。

        Returns:
            summary JSONL 文件路径。

        Raises:
            ValueError: batch 文件为空或 LLM 输出 3 次重试均失败。
            FileNotFoundError: batch 文件不存在。
        """
        batch_path = Path(batch_path)
        if not batch_path.exists():
            raise FileNotFoundError(f"Batch file not found: {batch_path}")

        messages = self._read_jsonl(batch_path)
        if not messages:
            raise ValueError(f"Batch file is empty: {batch_path}")

        session_id = messages[0].get("session_id", "unknown")

        # 构造 Prompt（含截断控制）
        truncated, user_prompt = self._build_prompt(messages)
        max_confidence = 0.80 if truncated else 1.0

        # 调用 LLM（含重试）
        extracted_items = self._call_llm_with_retry(user_prompt, max_confidence)

        # 构建输出记录
        summary_records: list[dict[str, Any]] = []
        for item in extracted_items:
            record = self._build_record(item, session_id, messages, max_confidence)
            if record is not None:
                summary_records.append(record)

        if not summary_records:
            logger.warning("LLM returned 0 extracted items for session %s", session_id)
            raise ValueError(f"No knowledge extracted from session {session_id}")

        # 写 summary JSONL
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.staging_dir / f"summary_{session_id}.jsonl"
        self._write_jsonl(output_path, summary_records)

        logger.info(
            "Extracted %d knowledge items from session %s → %s",
            len(summary_records),
            session_id,
            output_path,
        )
        return output_path

    # ------------------------------------------------------------------
    # Prompt 构建
    # ------------------------------------------------------------------

    def _build_prompt(self, messages: list[dict[str, Any]]) -> tuple[bool, str]:
        """构建 LLM User Prompt。

        包含对话记录 + 已有领域树（供 domain 分类参考）。
        若 token 超限则截断（保留最近消息 + 所有 tools）。

        Args:
            messages: batch 中的消息列表。

        Returns:
            (是否截断, user_prompt 字符串)。
        """
        # 格式化对话
        conversation = self._format_conversation(messages)

        # token 估算 + 截断
        estimated_tokens = len(conversation) // 2
        truncated = False
        if estimated_tokens > _MAX_CONTEXT_TOKENS:
            conversation = self._truncate_conversation(messages, _TARGET_TOKENS_AFTER_TRUNCATION)
            truncated = True

        # 领域列表
        if self.domain_tree:
            domain_list = "\n".join(
                f"- {d}" for d in sorted(self.domain_tree.keys())
            )
        else:
            domain_list = "- (自动检测，无预设领域)"

        prompt = f"""你是 devContextMemo 的知识提炼器。从以下对话中提取可复用的项目知识。

提取标准：
- 用户明确陈述的约束/规范/决策（含关键词：always, never, must, 必须, 统一）
- 跨 session 重复出现的信息
- 代码变更中体现的模式（从 tools 字段提取）
- ⚠️ 不提取：AI 的建议/推荐（未经用户确认）、纯代码生成、简单问答

四轴分类说明：
- granularity (L0-L5): L0=单文件规范, L1=模块, L2=子系统, L3=系统, L4=跨系统, L5=领域
- stability (S1-S5): S1=极易变, S2=易变, S3=中等, S4=稳定, S5=极稳定
- depth (KW/KH/KY): KW=知道(Know-What), KH=理解(Know-How), KY=领悟(Know-Why)

可用领域：
{domain_list}

知识类型（knowledge_type）：
- fact: 事实描述（"端口是8080"、"数据库名是mydb"）
- decision: 显式选型/决策（"选了Redis而非Memcached"、"权衡后决定用方案A"）。关键词：选了、决定、权衡、考虑到、因为
- preference: 用户/团队的偏好或习惯（"我们习惯用vim"、"团队规范是用black格式化"、"我偏好函数式风格"）
- experience: 引用过去项目经验（"上次做X时"、"踩过坑"、"之前遇到过"、"教训是"）

输出 JSON 格式（严格遵循）：
{{
  "extracted_items": [
    {{
      "content": "知识内容描述",
      "granularity": "L2",
      "stability": "S3",
      "depth": "KH",
      "domain": "order",
      "knowledge_type": "fact",
      "confidence": 0.88,
      "occurred_at": "2026-06-18T10:01:00Z",
      "source_messages": [2]
    }}
  ]
}}

注意：
- occurred_at 无法从对话推断时设为 null
- source_messages 是消息的 seq 列表
- 空数组 [] 表示本次无知识可提炼（正常情况）
- confidence 范围 0.0-1.0

【对话记录】
{conversation}
"""
        return truncated, prompt

    @staticmethod
    def _format_conversation(messages: list[dict[str, Any]]) -> str:
        """格式化消息列表为对话文本。

        Args:
            messages: 消息列表。

        Returns:
            格式化的对话字符串。
        """
        lines: list[str] = []
        for msg in messages:
            seq = msg.get("seq", "?")
            role = msg.get("role", "user")
            content = msg.get("content", "")
            timestamp = msg.get("timestamp", "")
            tools = msg.get("tools", [])
            tool_summary = ""
            if tools:
                tool_parts = [
                    f"{t.get('tool', '?')}→{t.get('input', {}).get('file', '?')}" for t in tools
                ]
                tool_summary = f" [tools: {', '.join(tool_parts)}]"
            lines.append(f"{role}(seq={seq}, {timestamp}): {content}{tool_summary}")
        return "\n".join(lines)

    @staticmethod
    def _truncate_conversation(messages: list[dict[str, Any]], target_tokens: int) -> str:
        """截断对话（保留最近消息 + 所有 tools 字段）。

        Args:
            messages: 消息列表。
            target_tokens: 截断后目标 token 数。

        Returns:
            截断后的对话字符串（头部含截断提示）。
        """
        # 时间倒序，优先保留最近消息
        recent = list(reversed(messages))
        result_lines: list[str] = []
        current_tokens = 200  # 截断提示预留
        for msg in recent:
            line = Extractor._format_conversation([msg])
            line_tokens = len(line) // 2
            if current_tokens + line_tokens > target_tokens:
                break
            result_lines.insert(0, line)
            current_tokens += line_tokens

        return (
            "[注意：以下内容已截断，仅包含最近消息。"
            "如需完整上下文，请将本次标记为 needs_review]\n\n" + "\n".join(result_lines)
        )

    # ------------------------------------------------------------------
    # LLM 调用 + 解析
    # ------------------------------------------------------------------

    def _call_llm_with_retry(self, user_prompt: str, max_confidence: float) -> list[dict[str, Any]]:
        """调用 LLM 提炼知识（含重试 + 校验）。

        Args:
            user_prompt: User Prompt 文本。
            max_confidence: 置信度上限（截断时 0.80）。

        Returns:
            提炼的知识条目列表。

        Raises:
            ValueError: 3 次重试均失败。
        """
        system_prompt = "你是 devContextMemo 的知识提炼器，只输出 JSON。"
        last_error: str = ""

        for attempt in range(_MAX_RETRIES):
            try:
                response = self.llm.chat(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    model=self.model,
                    temperature=0.3,
                    response_format={"type": "json_object"},
                )

                content = response["choices"][0]["message"]["content"]
                items = self._parse_and_validate(content, max_confidence)
                return items

            except (json.JSONDecodeError, ValueError, KeyError) as e:
                last_error = str(e)
                logger.warning(
                    "LLM extraction attempt %d/%d failed: %s",
                    attempt + 1,
                    _MAX_RETRIES,
                    e,
                )
                if attempt < _MAX_RETRIES - 1:
                    user_prompt += (
                        "\n\n[上次输出格式错误，请严格按 JSON schema 返回。" f"错误：{last_error}]"
                    )

        raise ValueError(f"LLM extraction failed after {_MAX_RETRIES} attempts: {last_error}")

    def _parse_and_validate(self, content: str, max_confidence: float) -> list[dict[str, Any]]:
        """解析 + 校验 LLM 输出。

        Args:
            content: LLM 返回的 JSON 字符串。
            max_confidence: 置信度上限。

        Returns:
            校验通过的知识条目列表。

        Raises:
            json.JSONDecodeError: JSON 解析失败。
            ValueError: 字段缺失或值非法。
        """
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("LLM output must be a JSON object")
        items = data.get("extracted_items")
        if items is None:
            raise ValueError("Missing 'extracted_items' field")
        if not isinstance(items, list):
            raise ValueError("'extracted_items' must be a list")

        validated: list[dict[str, Any]] = []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"Item {i} is not a dict")
            self._validate_item(item, i)
            # 应用置信度上限
            confidence = float(item["confidence"])
            if confidence > max_confidence:
                confidence = max_confidence
                logger.info(
                    "Item %d confidence capped to %.2f (truncation penalty)",
                    i,
                    max_confidence,
                )
            validated.append({**item, "confidence": confidence})

        return validated

    def _validate_item(self, item: dict[str, Any], index: int) -> None:
        """校验单条知识条目。

        Args:
            item: 知识条目 dict。
            index: 条目序号（错误信息用）。

        Raises:
            ValueError: 字段缺失或值非法。
        """
        # 必填字段
        for field in _REQUIRED_ITEM_FIELDS:
            if field not in item:
                raise ValueError(f"Item {index} missing field: {field}")

        # content 非空
        if not str(item["content"]).strip():
            raise ValueError(f"Item {index} content is empty")

        # 四轴分类校验
        if not is_valid_lx(item["granularity"]):
            raise ValueError(f"Item {index} invalid granularity: {item['granularity']!r}")
        if not is_valid_sy(item["stability"]):
            raise ValueError(f"Item {index} invalid stability: {item['stability']!r}")
        if not is_valid_depth(item["depth"]):
            raise ValueError(f"Item {index} invalid depth: {item['depth']!r}")
        if not is_valid_domain(item["domain"], self.domain_tree):
            raise ValueError(
                f"Item {index} invalid domain: {item['domain']!r} " f"(not in domain_tree)"
            )

        # knowledge_type 校验
        if not is_valid_knowledge_type(item["knowledge_type"]):
            raise ValueError(
                f"Item {index} invalid knowledge_type: {item['knowledge_type']!r}"
            )

        # confidence 范围
        confidence = item["confidence"]
        if not isinstance(confidence, (int, float)):
            raise ValueError(f"Item {index} confidence must be number")
        if not (_CONFIDENCE_MIN <= confidence <= _CONFIDENCE_MAX):
            raise ValueError(f"Item {index} confidence out of range: {confidence}")

    # ------------------------------------------------------------------
    # 记录构建
    # ------------------------------------------------------------------

    @staticmethod
    def _build_record(
        item: dict[str, Any],
        session_id: str,
        messages: list[dict[str, Any]],
        max_confidence: float,
    ) -> dict[str, Any] | None:
        """构建 summary JSONL 记录。

        将 LLM 输出的 item 映射为 summary 格式：
        - ``content`` → ``knowledge_text``
        - 补充 ``session_id`` / ``source_messages``

        Args:
            item: 校验后的 LLM 输出条目。
            session_id: 会话 ID。
            messages: 原始消息列表（用于 source_messages 默认值）。
            max_confidence: 置信度上限。

        Returns:
            summary 记录 dict，或 None（如果 content 为空）。
        """
        content = str(item["content"]).strip()
        if not content:
            return None

        source_messages = item.get("source_messages")
        if not source_messages:
            # 默认所有消息 seq
            source_messages = [m.get("seq", 0) for m in messages]

        return {
            "session_id": session_id,
            "knowledge_text": content,
            "granularity": item["granularity"],
            "stability": item["stability"],
            "depth": item["depth"],
            "domain": item["domain"],
            "knowledge_type": item["knowledge_type"],
            "confidence": float(item["confidence"]),
            "occurred_at": item.get("occurred_at"),
            "source_messages": source_messages,
            "status": "staged",  # V1.1 小写状态
        }

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
