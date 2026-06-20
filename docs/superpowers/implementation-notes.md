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

---

## #3: 知识状态机与绿色通道（T2）

**日期:** 2026-06-19
**关联:** `ALLOWED_TRANSITIONS` + `Writer` + `Consolidator`

**状态机设计:**

```
                     ┌───────── T3 ──────────┐
                     ▼                       │
staged ─────────► candidate ──► active ──► cold ──► stale ──► deprecated ──┐
   │                  │           │          │         │                    │
   │  T4              │  T5       │ T9       │ T12     │ T15               │ T20
   ▼                  ▼           ▼          ▼         ▼                    │
pending_review ──► active     draft ──► active  （复活）                    │
   │                                                    ▲                  │
   └──────────────────── T6 ───────────────────────────┘                  │
                                                                          │
                     └──────────────── T2 绿色通道 ────────────────────────┘
                    staged + confidence ≥ 0.95 → active（直接飞跃）
```

**两条晋升路径:**

| 场景 | 起始状态 | 晋升路径 | 哪层触发 |
|------|:--:|------|------|
| 管道自动采集 | `candidate` | Writer 写入 → Consolidator `candidate → active` | Step 5 + Step 6 |
| MCP 手动写入 | `staged` | T2 绿色通道 `staged → active`（confidence ≥ 0.95） | Step 6 |
| MCP 手动写入 | `staged` | T3 `staged → candidate → ...`（confidence < 0.95） | Step 6 |

**关键决策（why Writer 写 candidate 而非 staged）:**

历史上一度 `ALLOWED_TRANSITIONS` 缺少 `staged → active`，导致 T2 绿色通道被阻断（`Invalid transition staged→active`）。修复时发现了更深层的问题：

- `staged` 是给 **MCP 手动写入** 的知识起点（未经 verify/dedup）
- 管道知识已经过 **Step 3 验证 + Step 4 去重**，不应再退回 `staged`
- 所以 Writer 改为写 `candidate`，表示「已通过质量检查，等待晋升评估」

**测试覆盖:** 68 个状态机测试（`tests/unit/test_state_machine.py`），包括：
- 28 条 ALLOWED_TRANSITIONS 全量参数化验证
- 26 条明确禁止的跨级跳跃
- 6 条关键生命周期路径（绿色通道、审核、冷却、复活、草稿晋升等）
- 防御性测试（同状态、未知状态、deprecated 循环）

---

## #4: 双轨制（记忆轨 + 资源轨）检索层架构

**日期:** 2026-06-19
**关联:** Phase 1 资源轨设计，`ContextQueryEngine`

**背景:** 方案要求新增资源轨（独立存储需求/Spec/设计文档），与已有记忆轨（对话提炼知识）并行存储、交叉检索、显式链接。

**架构决策 — Facade + 双 Service:**

```
MCP Tool / CLI / API（统一入口）
         │
         ▼
  ContextQueryEngine   ← 新建 facade 层（合并去重 + 三级回退排序）
    │         │
    ├─────────┤
    ▼         ▼
KnowledgeService  ResourceService     ← 各自独立，零改动知识侧
    │              │
    ▼              ▼
SQLiteStore    ResourceStore          ← 存储层
```

**为什么不重构 KnowledgeService 为统一引擎:**

| 方案 | 问题 |
|------|------|
| 重构为统一引擎 | 破坏已有 275 行 KnowledgeService 和测试；两轨查询逻辑差异被揉在一起 |
| 两轨独立 + 上层合并 | 合并逻辑散落在 MCP/API/CLI 三层，重复 |
| **Facade + 双 Service** | 各自独立可测，合并集中一处，知识侧零改动 |

**模块结构:**

```
src/devcontext/
├── services/
│   ├── knowledge.py          # KnowledgeService（已有，不动）
│   ├── resource.py           # ResourceService（新建）
│   └── context_engine.py     # ContextQueryEngine（新建 facade）
├── models/
│   ├── knowledge.py          # KnowledgeIndex（已有）
│   └── resource.py           # Resource + ResourceBlock + ResourceLink（新建）
├── storage/
│   └── resource_store.py     # ResourceStore（新建）
```

**相关决策（from 设计方案 review）:**

| # | 问题 | 决策 |
|---|------|------|
| Q2 | MCP Tool 扩展方式 | 扩展现有 `mcp/tools.py`，不新建 module |
| Q3 | DB schema 变更 | 研发阶段可删历史数据，不依赖 migration |
| Q4 | Markdown 块解析 | 使用 `markdown-it-py` 库 |
| Q5 | 检索层架构 | 上述 Facade + 双 Service |
| Q7 | 资源变更检测 | 使用现有 `utils/diff.py`（git diff），不做 post-commit hook |
