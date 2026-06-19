"""内容签名 — SHA-256 哈希 + 语义签名（SimHash）。

提供：
- ``content_hash``：SHA-256 精确哈希（检测完全相同的内容）
- ``semantic_hash``：SimHash 语义签名（检测语义相似的内容）
- ``hamming_distance``：两个 SimHash 的汉明距离
- ``jaccard_similarity``：两个文本的 Jaccard 相似度
- ``normalize_text``：文本标准化（用于哈希前预处理）

SimHash 算法：
1. 文本分词（按字符 bigram，支持 CJK）
2. 每个 token 哈希为 64 位整数
3. 对每一位，token 哈希该位为 1 则 +1，为 0 则 -1
4. 最终每位 > 0 取 1，否则取 0 → 64 位指纹

设计依据：``docs/devContextMemo-数据写入流水线-详细设计-V1.0.md`` §六（Step 4）
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter

# SimHash 位数
_SIMHASH_BITS = 64


def normalize_text(text: str) -> str:
    """标准化文本（哈希前预处理）。

    移除标点、空白折叠、转小写，使内容差异不影响哈希比对。

    Args:
        text: 原始文本。

    Returns:
        标准化后的文本。

    Examples:
        >>> normalize_text("Hello,  World!")
        'hello world'
        >>> normalize_text("订单  幂等校验！")
        '订单 幂等校验'
    """
    # 转小写
    cleaned = text.lower()
    # 移除标点（保留 CJK 字符和字母数字）
    cleaned = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", cleaned)
    # 折叠空白
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def content_hash(text: str) -> str:
    """计算文本的 SHA-256 哈希（精确匹配用）。

    对标准化后的文本计算哈希，用于检测完全相同的内容。

    Args:
        text: 原始文本。

    Returns:
        64 字符的十六进制哈希字符串。

    Examples:
        >>> h1 = content_hash("hello world")
        >>> h2 = content_hash("Hello,  World!")
        >>> h1 == h2  # 标准化后相同
        True
        >>> len(h1)
        64
    """
    normalized = normalize_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def semantic_hash(text: str) -> str:
    """计算文本的 SimHash 语义签名（相似度检测用）。

    使用字符 bigram 分词（支持 CJK），生成 64 位指纹。
    分词前移除所有空白，使空白差异不影响签名。

    Args:
        text: 原始文本。

    Returns:
        16 字符的十六进制字符串（64 位）。

    Examples:
        >>> h1 = semantic_hash("订单幂等校验")
        >>> h2 = semantic_hash("订单 幂等 校验")
        >>> h1 == h2  # 空白不影响签名
        True
        >>> len(h1)
        16
    """
    normalized = normalize_text(text)
    # 移除所有空白，使 bigram 不受空格影响
    normalized = normalized.replace(" ", "")
    tokens = _tokenize_bigram(normalized)
    if not tokens:
        return "0" * 16

    # 统计 token 频率作为权重
    token_counts = Counter(tokens)

    # 逐位累加
    bits = [0] * _SIMHASH_BITS
    for token, weight in token_counts.items():
        token_hash = int(hashlib.md5(token.encode("utf-8"), usedforsecurity=False).hexdigest(), 16)
        for i in range(_SIMHASH_BITS):
            if token_hash & (1 << i):
                bits[i] += weight
            else:
                bits[i] -= weight

    # 生成指纹
    fingerprint = 0
    for i in range(_SIMHASH_BITS):
        if bits[i] > 0:
            fingerprint |= 1 << i

    return f"{fingerprint:016x}"


def hamming_distance(hash1: str, hash2: str) -> int:
    """计算两个 SimHash 的汉明距离。

    Args:
        hash1: 第一个 SimHash（16 字符 hex）。
        hash2: 第二个 SimHash（16 字符 hex）。

    Returns:
        汉明距离（0-64），0 表示完全相同。

    Examples:
        >>> h = semantic_hash("test")
        >>> hamming_distance(h, h)
        0
    """
    int1 = int(hash1, 16)
    int2 = int(hash2, 16)
    return bin(int1 ^ int2).count("1")


def jaccard_similarity(text1: str, text2: str) -> float:
    """计算两个文本的 Jaccard 相似度。

    使用字符 bigram 集合，``|A ∩ B| / |A ∪ B|``。

    Args:
        text1: 第一个文本。
        text2: 第二个文本。

    Returns:
        相似度（0.0-1.0），1.0 表示完全相同。

    Examples:
        >>> jaccard_similarity("hello world", "hello world")
        1.0
        >>> jaccard_similarity("abc", "xyz")
        0.0
    """
    norm1 = normalize_text(text1)
    norm2 = normalize_text(text2)
    set1 = set(_tokenize_bigram(norm1))
    set2 = set(_tokenize_bigram(norm2))

    if not set1 and not set2:
        return 1.0
    if not set1 or not set2:
        return 0.0

    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union


def _tokenize_bigram(text: str) -> list[str]:
    """字符 bigram 分词（支持 CJK）。

    Args:
        text: 标准化后的文本。

    Returns:
        bigram 列表。

    Examples:
        >>> _tokenize_bigram("hello")
        ['he', 'el', 'll', 'lo']
        >>> _tokenize_bigram("订单")
        ['订单']
    """
    if len(text) < 2:
        return [text] if text else []
    return [text[i : i + 2] for i in range(len(text) - 1)]
