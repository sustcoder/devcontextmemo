# devContextMemo（码上记忆）开发规范

## 项目级规范源路径

所有项目原始需求、调研、决策过程、参考源码均在：

> **`/Users/liyanzhao/WorkBuddy/devContextMemo`**

编码时优先查阅该路径下的文档，而非记忆中的内容。

---

## 上下文压缩自救（必读）

上下文丢失时，只读这 3 个文件即可恢复 90% 状态：

| 顺序 | 文件 | 作用 |
|:--:|------|------|
| 1 | `devContextMemo-编码索引-V1.0.md` | 文档体系全貌 + 模块对应的权威文档 |
| 2 | `devContextMemo-决策总账-V1.0.md` | D1-D76 全部技术决策最终状态 |
| 3 | `devContextMemo-项目知识系统-需求文档-V1.0.md` §一-§四 | 核心诉求 + 功能需求 |

额外恢复：`architecture.yaml`（架构地图）→ `knowledge-state-machine.yaml`（状态机）→ `domain/*.yaml`（领域聚合）。

---

## 文档冲突处理规则

| 优先级 | 文档 |
|:--:|------|
| 1 | `devContextMemo-项目知识系统-需求文档-V1.0.md`（最高优先级） |
| 2 | `devContextMemo-决策总账-V1.0.md` |
| 3 | `architecture.yaml`（机器可读架构权威） |
| 4 | `knowledge-state-machine.yaml`（状态机权威） |
| 5 | `domain/*.yaml`（领域聚合 Service Card） |
| 6 | `design/devContextMemo-系统架构设计-V1.0.md` |
| 7 | 各 Step 细化设计文档 |
| — | `archive/` 下所有文档（已过时，仅参考） |

---

## 工作规则

- **错误分析必须先报根因再执行**：发现错误日志时，先分析根因和解决方案，等待用户确认后再修改代码。禁止未确认直接动手。
- **E2E 优先于 mock**：mock 单元测试覆盖接口契约，E2E 覆盖数据流契约。跨多层的数据流必须用真实数据源验证。
- **状态机变更必配测试**：修改 `enums.py` 中的 `ALLOWED_TRANSITIONS` 或状态列表时，必须同步新增配套的状态机测试用例。

---

## 操作规范

### 必须遵守
- 函数/方法必须有 Google Style docstring
- snake_case 命名（Ruff 检查）
- UPPER_SNAKE 常量命名

### 强烈建议
- 每函数 ≤ 50 行
- 每文件 ≤ 500 行

### Commit 规范
```
<type>(<scope>): <subject>
```

---

## 技术栈

- **语言**：Python 3.13
- **框架**：FastAPI + FastMCP
- **CLI**：Typer（≥0.12.0）
- **数据库**：SQLite（WAL 模式）+ FTS5
- **LLM**：MiniMax + GLM
- **项目结构**：src-layout + setuptools（`src/devcontext/`）

---

## 项目结构

```
src/devcontext/                  # Python 包（46 个 .py 文件）
├── api/                         # REST 路由层 (FastAPI)
│   ├── deps.py                  # 依赖注入
│   └── routes/
│       ├── health.py            # /health 端点
│       └── knowledge.py         # 知识 CRUD API
├── cli/                         # CLI 命令 (Typer)
│   ├── app.py                   # CLI 入口
│   ├── config.py                # dev config
│   ├── dream.py                 # dev dream 巩固命令
│   ├── init.py                  # dev init 冷启动
│   ├── review.py                # dev review 审核
│   └── status.py                # dev status 状态
├── core/                        # 核心业务逻辑
│   ├── adapters/
│   │   ├── base.py              # 适配器基类
│   │   ├── opencode.py          # OpenCode 适配器
│   │   ├── comate.py            # Comate 适配器
│   │   └── cursor.py            # Cursor 适配器
│   ├── pipeline/
│   │   ├── receiver.py          # Step 0: 接收
│   │   ├── batcher.py           # Step 1: 攒批
│   │   ├── extractor.py         # Step 2a: 提炼+分类
│   │   ├── entity_extractor.py  # Step 2b: 实体+关系提取
│   │   ├── validator.py         # Step 3: 验证
│   │   ├── deduplicator.py      # Step 4: 去重
│   │   ├── writer.py            # Step 5: 写入
│   │   └── consolidator.py      # Step 6: 巩固
│   ├── calibration.py           # 校准引擎（8 种触发事件）
│   ├── conflict.py              # 冲突检测（L0-L5）
│   ├── health.py                # 数据健康引擎（7 类校正）
│   ├── init.py                  # 冷启动引擎
│   ├── promotion.py             # 晋升评估（V2.1 公式）
│   └── pruning.py               # 修剪规则（3 层体系 + 25 跃迁）
├── mcp/                         # MCP Server (FastMCP)
│   ├── server.py                # MCPServer 主类
│   ├── tools.py                 # 3 tools: query/write/calibrate
│   └── resources.py             # 2 resources
├── models/                      # SQLModel 数据模型
│   ├── knowledge.py             # KnowledgeIndex 等表模型
│   ├── category.py              # 分类模型
│   ├── source.py                # 数据源模型
│   └── enums.py                 # 状态枚举 + 状态机校验
├── schemas/                     # Pydantic API Schema
│   ├── knowledge.py             # 知识请求/响应 Schema
│   └── search.py                # 搜索请求/响应 Schema
├── services/                    # 业务编排层
│   ├── knowledge.py             # 知识检索 + 五操作
│   ├── pipeline.py              # 流水线编排
│   ├── review.py                # 审核流程
│   ├── dream.py                 # 巩固编排
│   └── injection.py             # 三层注入（AGENTS.md 生成）
├── storage/                     # 存储层
│   ├── markdown.py              # MarkdownStore（MD 权威源）
│   ├── sqlite.py                # SQLiteStore（DB 索引层）
│   ├── search.py                # FTS5 全文搜索
│   └── atomic.py                # 原子写入工具
└── utils/                       # 工具层
    ├── llm.py                   # LLM 调用（MiniMax + GLM）
    ├── hash.py                  # 哈希工具（SHA-256 / SimHash）
    ├── diff.py                  # Git diff 解析
    ├── security.py              # 三层安全扫描（L1/L2/L3）
    └── path.py                  # 路径校验（realpath 防遍历）

tests/
├── unit/                        # 15 个单元测试
├── module/                      # 8 个模块测试（Step 0-6）
├── integration/                 # 3 个集成测试（engine/opencode/contracts）
├── e2e/                         # 2 个端到端测试
├── contracts/                   # 8 个契约 YAML
└── fixtures/                    # 4 个测试数据 JSON

domain/
├── knowledge-lifecycle.yaml     # 生命周期领域聚合
├── knowledge-quality.yaml       # 质量保障领域聚合
└── knowledge-delivery.yaml      # 交付领域聚合

docs/                            # 16 份设计文档（详见编码索引）
```

---

## 打包分发

构建 wheel + sdist 到 `dist/` 目录：

```bash
# 清理旧产物 + 构建
rm -rf build/ src/devcontext.egg-info/ && python -m build --wheel --sdist
```

产物：
| 文件 | 用途 |
|------|------|
| `dist/devcontext-0.1.0-py3-none-any.whl` | 二进制 wheel（推荐分发） |
| `dist/devcontext-0.1.0.tar.gz` | 源码 sdist |

安装：
```bash
pip install dist/devcontext-0.1.0-py3-none-any.whl
devcontext --help
```

构建配置：`pyproject.toml`（`[build-system]` + `[project]` + `[tool.setuptools]`）

**注意：** 
- 不要手动放 sdist 到项目根目录，统一放 `dist/`
- 升级版本号时同步修改 `pyproject.toml` 中的 `version` 和 `src/devcontext/__init__.py` 中的 `__version__`

---

## Graphify

本项目可能包含 graphify-out/ 知识图谱。

规则：
- 回答架构或代码库问题前，先读 graphify-out/GRAPH_REPORT.md
- 跨模块「X 和 Y 的关系」问题优先用 `graphify query` / `graphify path` / `graphify explain`
- 修改代码文件后运行 `graphify update .`

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **devContextMemo** (2707 symbols, 6678 relationships, 103 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/devContextMemo/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool | When to use | Command |
|------|-------------|---------|
| `query` | Find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})` |
| `impact` | Blast radius before editing | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | Pre-commit scope check | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | Safe multi-file rename | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher` | Custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

## Impact Risk Levels

| Depth | Meaning | Action |
|-------|---------|--------|
| d=1 | WILL BREAK — direct callers/importers | MUST update these |
| d=2 | LIKELY AFFECTED — indirect deps | Should test |
| d=3 | MAY NEED TESTING — transitive | Test if critical path |

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/devContextMemo/context` | Codebase overview, check index freshness |
| `gitnexus://repo/devContextMemo/clusters` | All functional areas |
| `gitnexus://repo/devContextMemo/processes` | All execution flows |
| `gitnexus://repo/devContextMemo/process/{name}` | Step-by-step execution trace |

## Self-Check Before Finishing

Before completing any code modification task, verify:
1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npx gitnexus analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
npx gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
