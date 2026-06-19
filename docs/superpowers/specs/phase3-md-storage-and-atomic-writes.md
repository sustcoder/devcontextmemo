---
name: phase3-md-storage-and-atomic-writes
overview: 实现 Phase 3：storage/atomic.py（路径穿越校验 + 原子写入 tmp→fsync→rename）与 storage/markdown.py（MarkdownStore 三目录设计 + frontmatter 14 字段 + to_db_dict 映射），建立 MD first → DB second 写入协议。决策：方案A纯 MD 作为 SSoT / 调用方决策 DB 同步时机 / 平衡字段（14 字段含 Phase 3 前瞻）。验收：能原子写入 staging/knowledge/deprecated 三目录 MD 文件，路径穿越被拒，pytest 测试通过。
todos:
  - id: implement-atomic
    content: 实现 storage/atomic.py：PathTraversalError 异常 + sanitize_path_segment（清理单段路径） + validate_safe_path（resolve+前缀校验，不预清理 ..） + atomic_write_md（tmp→fsync→os.replace，max_retries=3）
    status: completed
  - id: implement-markdown-store
    content: 实现 storage/markdown.py MarkdownStore：三目录（staging/YYYYMMDD-{title}.md, knowledge/{domain}/{title}.md, deprecated/） + write_to_staging/write_to_knowledge/read/to_db_dict + 14 字段 frontmatter + _safe_filename_segment + _parse_frontmatter
    status: completed
    dependencies:
      - implement-atomic
  - id: implement-utils-placeholders
    content: 实现 utils/path.py 和 utils/security.py 占位模块（docstring 声明职责，具体实现延后到后续 Phase）
    status: completed
    dependencies:
      - implement-atomic
  - id: write-tests
    content: 编写 tests/unit/test_atomic.py（路径穿越拒绝/合法路径通过/原子写入重试） + tests/unit/test_markdown_store.py（三目录写入/frontmatter 解析/to_db_dict 映射/文件名安全化）
    status: completed
    dependencies:
      - implement-markdown-store
---

## 产品概述

Phase 3 是 devContextMemo 知识系统的文件存储基础层实现，目标是建立以 MD 文件为权威存储（SSoT）的写入与读取能力，确保数据落盘的原子性与安全性，为 Phase 4 流水线 Writer 提供 MD first → DB second 的写入协议。

## 核心功能

- **原子写入协议**：tmp 文件写入 → flush → fsync → os.replace 原子替换（POSIX 保证），失败重试 3 次
- **路径穿越防护**：resolve + 前缀校验策略，`../../etc` 逃逸被拒，`order/../payment` resolve 后仍在 base 内则合法
- **三目录设计**：
  - `staging/` ← 待审核知识，`YYYYMMDD-{title}.md` 日期前缀命名
  - `knowledge/{domain}/` ← 已采纳知识，按领域子目录
  - `deprecated/` ← 已废弃知识
- **Frontmatter 14 字段**：id, title, domain, sub_domain, granularity, stability, depth, status, confidence, code_verified, concept_tags, source_session, created_at, updated_at（+ uri 运行时填充）
- **MD first → DB second**：MD 写成功后才写 DB，MD 失败不写 DB；DB 失败时 MD 完整保留，下次 mtime 检测重建索引
- **to_db_dict 映射**：将 MD record 转换为 knowledge_index 表 INSERT 参数，供 Phase 4 Writer 调用

## 技术栈

- Python 3.13+（pathlib / os / re 标准库）
- PyYAML（frontmatter 序列化/反序列化）
- pytest（单元测试 + fixture）

## 实现方案

### 整体策略

采用「MD 文件作为 SSoT，DB 作为派生索引」策略（Q1 决策：方案A纯 MD）。MD 文件是知识的权威来源，DB 索引从 MD 派生，可随时重建。写入顺序严格 MD first → DB second，保证崩溃恢复时 MD 完整。

### 路径校验策略（Q2 调用方决策）

`validate_safe_path` 采用「直接 resolve + 前缀校验」而非「预清理 ..」：

- 不预先清理 `..`，这样 `../../etc` 会因 resolve 后逃逸被拒
- `order/../payment` resolve 后仍在 base 内则合法——与 §3.3 表格行为一致
- 空输入直接拒绝

### Frontmatter 字段设计（Q3 平衡字段）

14 字段 = 基础必填（9）+ Phase 3 前瞻（5）：

- **必填**：id, title, granularity, stability, depth, status, confidence, created_at, updated_at
- **可选**：domain, sub_domain, code_verified, concept_tags, source_session
- **运行时**：uri（由实际写入路径决定，不存入 record）

### 原子写入协议

```
1. 确保父目录存在 (mkdir parents=True, exist_ok=True)
2. 写入临时文件 (.tmp 后缀)
3. flush + fsync 确保落盘
4. os.replace 原子替换 (POSIX 保证原子性)
5. 失败时清理临时文件，重试 (max_retries=3)
```

### 文件名安全化

`_safe_filename_segment` 流程：
1. sanitize_path_segment 去掉路径分隔符和控制字符
2. 替换文件名非法字符（`<>:"/\|?*` + 控制字符）为下划线
3. 折叠连续空白为单下划线
4. 空结果 → `untitled`
5. 截断至 60 字符

## 架构设计

```mermaid
graph TD
    A[storage/atomic.py<br/>PathTraversalError<br/>validate_safe_path<br/>atomic_write_md] --> B[storage/markdown.py<br/>MarkdownStore]
    B --> C[staging/<br/>YYYYMMDD-{title}.md]
    B --> D[knowledge/{domain}/<br/>{title}.md]
    B --> E[deprecated/<br/>{title}.md]
    B --> F[to_db_dict<br/>MD record → DB dict]
    F --> G[Phase 4 Writer<br/>DB second]
```

### 数据所有权

- MarkdownStore 是 MD 文件的唯一 owner（architecture.yaml data_ownership 约束）
- 上层（Writer/Service）通过 MarkdownStore 接口访问，不直接操作文件系统
- DB 索引派生自 MD，可随时从 MD 重建（P2 原则）

## 目录结构

```
src/devcontext/
├── storage/
│   ├── __init__.py          # [MODIFY] 导出 MarkdownStore + atomic 函数
│   ├── atomic.py            # [NEW] 路径校验 + 原子写入
│   └── markdown.py          # [NEW] MarkdownStore 三目录 + frontmatter
├── utils/
│   ├── path.py              # [NEW] 占位：realpath + 遍历防护（后续 Phase 实现）
│   └── security.py          # [NEW] 占位：三层安全扫描（后续 Phase 实现）

tests/
├── unit/
│   ├── test_atomic.py       # [NEW] 路径穿越/原子写入测试
│   └── test_markdown_store.py # [NEW] 三目录写入/frontmatter/映射测试
```

## 关键代码结构

### 路径校验（storage/atomic.py 核心）

```python
def validate_safe_path(base_dir: Path, user_input: str) -> Path:
    """校验用户输入拼接后不会逃逸出 base_dir。
    采用直接 resolve + 前缀校验（不预清理 ..）。
    """
    if not user_input or not user_input.strip():
        raise PathTraversalError("Empty path input is not allowed")
    base_resolved = base_dir.resolve()
    candidate = (base_resolved / user_input).resolve()
    if not (cand_str == base_str or cand_str.startswith(base_str + os.sep)):
        raise PathTraversalError(...)
    return candidate
```

### 原子写入（storage/atomic.py 核心）

```python
def atomic_write_md(path: Path, content: str, max_retries: int = 3) -> bool:
    """原子写入 MD 文件：tmp → fsync → rename。"""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    for attempt in range(max_retries):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
            return True
        except OSError:
            # 清理临时文件，重试
            ...
    return False
```

### MarkdownStore 接口签名（storage/markdown.py 核心）

```python
class MarkdownStore:
    def __init__(self, staging_dir, knowledge_dir, deprecated_dir) -> None: ...
    def write_to_staging(self, record: dict) -> Path: ...
    def write_to_knowledge(self, record: dict) -> Path: ...
    def read(self, md_path: str | Path) -> dict: ...
    def to_db_dict(self, record: dict, md_path: str | Path) -> dict: ...
```

## 实现注意事项

- **不预清理 `..`**：`validate_safe_path` 如果先清理 `..`，会把 `../../etc` 变成 `etc`（合法），失去防护意义。必须直接 resolve 后做前缀校验
- **os.replace 而非 os.rename**：`os.replace` 在目标已存在时原子覆盖，`os.rename` 在 Windows 上目标存在会失败
- **fsync 的必要性**：仅 flush 不保证数据落盘（可能在 OS page cache），fsync 强制刷盘确保崩溃恢复
- **to_db_dict 不含后续字段**：`used_count`/`last_used_at`/`last_calibrated_at`/`calibration_status`/`embedding`/`prune_priority`/`certainty`/`freshness` 等字段由后续 Phase 按需填充，Phase 3 只映射 frontmatter 14 字段
- **concept_tags 序列化**：frontmatter 中以 YAML list 形式存储（可读），to_db_dict 时转为 JSON 字符串（DB 存储）
- **FTS5 同步延后**：Phase 3 不涉及 FTS5 同步，由 Phase 4 Writer 在 DB 写入后调用 `SQLiteStore._sync_fts`
