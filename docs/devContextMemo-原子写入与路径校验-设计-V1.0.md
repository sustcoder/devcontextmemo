# devContextMemo 原子写入与路径校验 — 设计文档 V1.0

> **触发**：宪法式批判 CC2（原子性断裂）+ MA3（路径穿越风险）
> **日期**：2026-06-17
> **版本**：V1.0
> **关联**：`devContextMemo-流水线-Step5-写入层-细化设计-V1.3.md`

---

## 一、问题概述

### CC2：MD 写入无事务保护

Step 5 当前的 `write_one()` 调用顺序：
```
_write_db_index() → _write_md_file()
```
如果 MD 写入失败（磁盘满/权限拒绝/网络文件系统断开），DB 已提交但 MD 不存在——**DB 索引指向一个不存在的文件**。进程崩溃重启后，DB 中的索引行成为永久脏数据。

### MA3：文件路径缺少穿越校验

`_determine_domain()` 和 `_build_md_filename()` 使用用户提供的 domain/title 拼接路径。恶意输入可能导致路径穿越（如 domain = `../../etc`）。

---

## 二、原子写入协议

### 2.1 写入顺序（修正）

```
旧顺序（有问题）：
  _write_db_index() → _write_md_file()  ❌ DB 先写，MD 失败后 DB 脏

新顺序（修正）：
  _write_md_file() → _write_db_index()  ✅ MD 成功后才写 DB
```

### 2.2 原子写入伪代码

```python
async def write_one(self, candidate: DedupedCandidate) -> WriteResult:
    knowledge_id = self._generate_knowledge_id()
    domain = self._validate_domain(candidate.domain)        # ← 路径校验
    filename = self._validate_filename(candidate.title)     # ← 路径校验
    status = self._determine_initial_status(candidate)

    # Step 1: 生成 MD 内容（纯内存操作，失败无副作用）
    yaml = self._build_yaml_frontmatter(knowledge_id, candidate, status)
    md_content = yaml + "\n" + candidate.content

    # Step 2: 原子写入 MD 文件
    md_path = self._resolve_md_path(domain, filename)
    try:
        written = await self._atomic_write_md(md_path, md_content)
        if not written:
            return WriteResult(knowledge_id, md_path, False, False, "failed",
                              "MD write failed: disk full or permission denied")
    except PathTraversalError as e:
        return WriteResult(knowledge_id, md_path, False, False, "failed", str(e))

    # Step 3: MD 成功后，写 DB 索引
    db_ok = await self._write_db_index(knowledge_id, candidate, md_path, status)
    if not db_ok:
        # DB 写入失败：MD 文件是干净的（已成功写入），仅记录错误日志
        # 下次 mtime 漂移检测会重建 DB 索引（§8.1 三道防线）
        logger.error(f"DB write failed for {knowledge_id}, MD is intact at {md_path}")
        return WriteResult(knowledge_id, md_path, False, True, status,
                          "DB write failed, MD is intact - will recover via mtime check")

    return WriteResult(knowledge_id, md_path, True, True, status, "")


async def _atomic_write_md(self, path: Path, content: str) -> bool:
    """原子写入：先写 .tmp → fsync → rename"""
    tmp_path = path.with_suffix(path.suffix + ".tmp")

    for attempt in range(self.config.max_retries):
        try:
            # 确保父目录存在
            path.parent.mkdir(parents=True, exist_ok=True)

            # 写入临时文件
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())  # 确保落盘

            # 原子替换
            os.replace(tmp_path, path)  # = rename(), POSIX 保证原子性
            return True

        except (OSError, IOError) as e:
            logger.warning(f"MD write attempt {attempt+1} failed: {e}")
            if attempt == self.config.max_retries - 1:
                return False

    return False
```

### 2.3 恢复策略

| 故障场景 | DB 状态 | MD 状态 | 恢复方式 |
|---------|:--:|:--:|------|
| MD 写入失败 | 未写入 | 不存在 | 管道重试（Step 6 重新触发） |
| MD 成功，DB 失败 | 未写入 | ✅ 存在 | mtime 漂移检测自动重建 DB 索引 |
| MD 成功，DB 成功，进程崩溃 | ✅ 已提交 | ✅ 存在 | 无影响（DB 事务已 commit） |
| MySQL/Java/MD 写入 | MD 成功但 DB 索引指向旧内容 | ✅ 存在 | mtime 漂移检测发现不一致 → 重建索引 |

> **原则**：MD 文件是 SSoT。只要 MD 文件完整，DB 索引可以恢复。因此写入顺序必须是「先 MD 后 DB」——MD 写入失败时 DB 尚未写入，不会产生脏数据。

### 2.4 与 Step 6 巩固层的协调

Step 6 的晋升评估触发时，如果发现 DB 中 status=active 但 MD 缺失，说明存在数据不一致。此时：
1. 检查 staging/ 中是否有该知识的新版本 → 有则重新晋升
2. 没有则标记 DB 行为 orphaned → 下次 `dev dream` 清理

---

## 三、路径穿越校验

### 3.1 校验函数

```python
import os
from pathlib import Path

class PathTraversalError(ValueError):
    """路径穿越攻击尝试"""
    pass

def validate_safe_path(base_dir: Path, user_input: str) -> Path:
    """
    校验用户输入拼接后不会逃逸出 base_dir。

    返回：归一化后的绝对路径
    抛出：PathTraversalError 如果检测到穿越
    """
    # Step 1: 清理输入——移除 .. 和空段
    cleaned = "/".join(
        seg for seg in user_input.split("/")
        if seg and seg != ".." and seg != "."
    )
    if not cleaned:
        raise PathTraversalError(f"Invalid path after sanitization: {user_input!r}")

    # Step 2: 拼接并 realpath() 解析
    candidate = (base_dir / cleaned).resolve()

    # Step 3: 二次校验——确保 realpath 后仍在 base_dir 内
    if not str(candidate).startswith(str(base_dir.resolve()) + os.sep) \
       and str(candidate) != str(base_dir.resolve()):
        raise PathTraversalError(
            f"Path traversal detected: {user_input!r} → {candidate} "
            f"(outside {base_dir})"
        )

    return candidate
```

### 3.2 集成点

在 Step 5 的 `write_one()` 中，所有涉及用户输入拼接路径的位置：

| 位置 | 用户输入 | 基目录 | 校验 |
|------|---------|--------|------|
| domain 目录名 | candidate.domain | `.devContextMemo/knowledge/` | `validate_safe_path(knowledge_dir, domain)` |
| MD 文件名 | candidate.title (截断后) | `.devContextMemo/knowledge/<domain>/` | `validate_safe_path(domain_dir, filename)` |
| staging 路径 | 同上 | `.devContextMemo/staging/` | 同上 |
| source 文件路径 | source.file_path | 项目根目录 | `validate_safe_path(project_root, file_path)` |

### 3.3 非法输入示例

| 输入 | 检测结果 |
|------|------|
| `domain = "../../etc"` | ❌ PathTraversalError |
| `domain = "order"` | ✅ `.devContextMemo/knowledge/order/` |
| `domain = "order/../payment"` | ✅ `.devContextMemo/knowledge/payment/` (清理 ..) |
| `title = "../../../passwd.md"` | ❌ PathTraversalError |
| `domain = ""` | ❌ ValueError (空路径) |

---

## 四、集成检查清单

对 Step 5 `KnowledgeWriter` 需要修改的位置：

| # | 修改点 | 当前状态 | 需要改为 |
|:--:|------|------|------|
| 1 | `write_one()` 写入顺序 | DB → MD | **MD → DB** |
| 2 | `_write_md_file()` | 可能缺少 fsync | **tmp → fsync → rename** |
| 3 | `_determine_domain()` | 无路径校验 | **添加 validate_safe_path()** |
| 4 | `_build_md_filename()` | 无路径校验 | **添加 validate_safe_path()** |
| 5 | `WriteResult` 恢复语义 | 未定义 DB 失败时 MD 状态 | **MD 成功时 db_success=False 仍标记 md_success=True** |

---

## 五、与现有设计的兼容性

| 现有机制 | 影响 | 处理 |
|---------|------|------|
| mtime 漂移检测（三道防线） | 无冲突 | DB 写入失败后 mtime 检测自动补建索引 |
| Git hook 兜底 | 无冲突 | MD 成功、Git 正常追踪 |
| Step 6 巩固层 | 无冲突 | Step 6 只读 MD 文件，不依赖 DB 写入状态 |
| 并发写入（多 OpenCode 会话） | SQLite WAL 模式已覆盖 | 串行写入 MD + 事务性 DB 写入无竞态 |

---

> **本文档应在编码 Step 5 前执行**。实现时直接参考 §2.2 的伪代码。
