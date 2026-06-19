"""原子写入与路径校验 — MD first → DB second 的基础设施。

提供：
- ``PathTraversalError``：路径穿越攻击异常
- ``validate_safe_path``：用户输入拼接路径的穿越校验
- ``sanitize_path_segment``：单段路径清理
- ``atomic_write_md``：tmp → fsync → rename 原子写入

设计依据：``docs/devContextMemo-原子写入与路径校验-设计-V1.0.md``
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class PathTraversalError(ValueError):
    """路径穿越攻击尝试。

    当用户输入拼接路径后逃逸出基目录时抛出。
    """

    pass


def sanitize_path_segment(segment: str) -> str:
    """清理单段路径输入。

    移除路径分隔符、空字节、控制字符，保留可读字符。
    用于单个目录名或文件名组件的预处理。

    Args:
        segment: 用户提供的单段路径输入（如 domain 或 title）。

    Returns:
        清理后的路径段。空输入返回空字符串。

    Examples:
        >>> sanitize_path_segment("order")
        'order'
        >>> sanitize_path_segment("order/../etc")
        'orderetc'
        >>> sanitize_path_segment("")
        ''
    """
    if not segment:
        return ""
    # 移除路径分隔符、空字节、控制字符（保留可打印字符和空格）
    cleaned = "".join(
        ch for ch in segment if ch not in ("/", "\\", "\x00") and (ch.isprintable() or ch.isspace())
    )
    # 移除 .. 序列（防止目录跳级）
    cleaned = cleaned.replace("..", "")
    return cleaned.strip()


def validate_safe_path(base_dir: Path, user_input: str) -> Path:
    """校验用户输入拼接后不会逃逸出 ``base_dir``。

    采用「直接 resolve + 前缀校验」策略（不预先清理 ``..``），
    这样 ``../../etc`` 会因 resolve 后逃逸被拒，而 ``order/../payment``
    resolve 后仍在 base 内则合法——与 §3.3 表格行为一致。

    Args:
        base_dir: 基目录（已存在的绝对路径）。
        user_input: 用户提供的相对路径输入（如 domain 或 filename）。

    Returns:
        归一化后的绝对路径。

    Raises:
        PathTraversalError: 如果检测到路径穿越，或输入为空。

    Examples:
        >>> from pathlib import Path
        >>> base = Path("/tmp/.devContextMemo/knowledge")
        >>> validate_safe_path(base, "order")
        PosixPath('/tmp/.devContextMemo/knowledge/order')
        >>> validate_safe_path(base, "../../etc")  # doctest: +SKIP
        Traceback (most recent call last):
            ...
        devcontext.storage.atomic.PathTraversalError: ...
    """
    if not user_input or not user_input.strip():
        raise PathTraversalError("Empty path input is not allowed")

    # 拼接并 resolve() 解析（resolve 会展开 .. 和符号链接）
    base_resolved = base_dir.resolve()
    candidate = (base_resolved / user_input).resolve()

    # 前缀校验——确保 realpath 后仍在 base_dir 内
    base_str = str(base_resolved)
    cand_str = str(candidate)
    if not (cand_str == base_str or cand_str.startswith(base_str + os.sep)):
        raise PathTraversalError(
            f"Path traversal detected: {user_input!r} → {candidate} " f"(outside {base_dir})"
        )

    return candidate


def atomic_write_md(
    path: Path,
    content: str,
    max_retries: int = 3,
) -> bool:
    """原子写入 MD 文件：tmp → fsync → rename。

    实现 §2.2 的原子写入协议：
    1. 确保父目录存在
    2. 写入临时文件（``.tmp`` 后缀）
    3. ``flush`` + ``fsync`` 确保落盘
    4. ``os.replace`` 原子替换（POSIX 保证原子性）

    失败时重试，最终失败返回 ``False``。临时文件残留会被清理。

    Args:
        path: 目标 MD 文件路径。
        content: 文件内容（UTF-8 字符串）。
        max_retries: 最大重试次数，默认 3。

    Returns:
        ``True`` 表示写入成功，``False`` 表示重试耗尽仍失败。

    Note:
        此函数只负责 MD 文件原子写入，不涉及 DB 操作。
        调用方应在 MD 成功后才写 DB（MD first → DB second）。
    """
    tmp_path = path.with_suffix(path.suffix + ".tmp")

    for attempt in range(max_retries):
        try:
            # 确保父目录存在
            path.parent.mkdir(parents=True, exist_ok=True)

            # 写入临时文件
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())

            # 原子替换（POSIX 保证 rename 原子性）
            os.replace(tmp_path, path)
            return True

        except OSError as e:
            logger.warning(
                "MD write attempt %d/%d failed for %s: %s",
                attempt + 1,
                max_retries,
                path,
                e,
            )
            # 清理可能残留的临时文件
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            if attempt == max_retries - 1:
                logger.error(
                    "MD write failed after %d attempts for %s",
                    max_retries,
                    path,
                )
                return False

    return False
