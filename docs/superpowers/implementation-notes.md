# 实现细节记录

> 记录架构设计中的关键技术实现细节，说明「为什么这样设计」和「怎么工作的」。
> 与 `debugging-notes.md` 互补：那是 bug 和修复，这是设计和原理。

---

## #1: daemon 启动时如何发现待处理的 batch

**日期:** 2026-06-19
**关联:** `PipelineService._process_existing_batches`

**问题:** `devcontext serve` 启动后怎么知道 staging 里有哪些 batch 需要加工？

**设计:** 不依赖内存状态，不依赖数据库，纯靠文件系统上的 `_meta.yaml` 作为状态机。

**流程:**

```
devcontext serve
  → serve()
    → PipelineService.start()
        → _process_existing_batches()
            ↓
        遍历 staging/ 下所有 _meta.yaml  (rglob)
            ↓
        读 YAML，检查 status 字段
            ↓
        status == "ready"  → 调用 _on_batch_ready() 加工
        status == "done"   → 跳过
        status == "failed" → 跳过
```

**关键代码** (`services/pipeline.py`):

```python
for meta_file in sorted(staging.rglob("_meta.yaml")):  # 遍历所有 _meta.yaml
    meta = yaml.safe_load(meta_file.read_text())        # 读 YAML
    if meta.get("status") == "ready":                   # 只看 ready 的
        ready_batches.append(meta_file.parent)           # 加入处理队列
```

**为什么用文件系统而不是数据库:**

| 方案 | 优点 | 缺点 |
|------|------|------|
| 文件系统（当前） | daemon 重启自动恢复，无额外依赖，`devcontext status` 可直接读 | 文件遍历开销（119 个 batch 可忽略） |
| 数据库 | 查询快 | 引入额外依赖，staging 和 DB 状态可能不一致 |
| 内存 | 零 IO | 重启丢失，无法恢复 |

**设计意图:** `_meta.yaml` 是 Step 1 (BatchWriter) 的输出产物，也是 Steps 2-6 的输入契约。`status` 字段让这个文件既是数据容器，又是状态机——ready → done/failed。任何进程只要读到这个文件，就能知道 batch 的当前状态，无需查询其他系统。

---

## #2: 领域树（domain_tree）的加载与自动模式

**日期:** 2026-06-19
**关联:** `Extractor` 知识分类 + `is_valid_domain`

**问题:** LLM 提炼知识时需要把知识归入某个领域（如 `order`、`database`），但 `serve()` 中 `domain_tree = {}` 导致 LLM 返回任何领域都被 `is_valid_domain` 拦截报错：
```
ValueError: Item 0 invalid domain: 'general' (not in domain_tree)
```

**设计:**

| domain_tree 状态 | 行为 | 适用场景 |
|:-:|------|------|
| 空 `{}` | 自动模式：LLM 自由命名，`is_valid_domain` 放行 | 冷启动、未配置 |
| 有值 | 校验模式：LLM 只能选列表中的领域 | 项目有了明确的领域划分 |

**存储位置选择:**

| 方案 | 优缺点 |
|------|--------|
| `.env` | 已有 pydantic-settings / 但 JSON 一行难读、env 通常放密钥不放业务配置 |
| `AGENTS.md` | 已存在于项目 / 但 Markdown 解析脆弱、混用目的（AI 上下文 vs 程序配置） |
| **`.devContextMemo/domain-tree.yaml`（选用）** | YAML 结构化人机可读 / 需新增加载逻辑（~20行） |

选 YAML 文件的原因：领域树是**项目级配置**（该项目的业务领域固定），不是环境级（dev/staging 都一样），且 `.devContextMemo/` 目录已存在无需新建。

**加载流程** (`main.py:_load_domain_tree`):

```
serve() 启动
  → _load_domain_tree()
      → domain-tree.yaml 存在？
          ├─ 是 → yaml.safe_load() → 返回 dict
          └─ 否 → 返回 {}
  → Extractor(llm_client, domain_tree, staging_dir)
      → is_valid_domain(domain, tree)
          ├─ tree 为空 → return True（自动模式）
          └─ tree 有值 → return domain in tree（校验模式）
```
