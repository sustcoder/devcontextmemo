# devContextMemo（码上记忆）

> **一句话**：对话沉淀知识，编码随时唤醒
> **版本**：v0.1.0 | **许可证**：MIT

---

## 简介

devContextMemo 是一个项目知识管理工具，自动将 AI 编程工具（OpenCode、Comate、Cursor 等）的对话记录提炼为结构化知识，并通过 MCP Tool 按需注入 AI 上下文。

**核心价值**：让你和 AI 之间的每一次对话都变成可累积的项目知识资产。

**技术栈**：Python 3.13 + FastAPI + FastMCP + SQLite（WAL 模式）+ Typer CLI

---

## 安装

### 环境要求

- Python >= 3.13

### 本地使用（在devContextMemo中使用）
```bash
cd /Users/liyanzhao/soft/code/devContextMemo
source .venv/bin/activate
devcontext --help
```

### 源码安装（开发用）

```bash
git clone <repo-url> && cd devContextMemo
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
devcontext --help
```

### wheel 安装（分发用）

```bash
pip install dist/devcontext-0.1.0-py3-none-any.whl
devcontext --help
```

---

## 快速开始

在目标项目根目录运行：

```bash
devcontext init     # 创建 .devContextMemo/ 目录 + 初始化 SQLite 数据库
```

---

## CLI 命令

| 命令 | 说明 |
|------|------|
| `devcontext status` | 查看知识库状态（按状态/领域统计） |
| `devcontext review list` | 列出待审核知识 |
| `devcontext review approve <ID>` | 采纳知识 → active |
| `devcontext review reject <ID>` | 拒绝知识 → deprecated |
| `devcontext review restore <ID>` | 恢复已废弃知识 |
| `devcontext dream` | 知识巩固（晋升 + 修剪 + 校准） |
| `devcontext dream --dry-run` | 预览模式 |
| `devcontext config` | 查看全部配置 |
| `devcontext config set <KEY> <VALUE>` | 修改配置 |

---

## MCP Tool 接口

| Tool | 说明 |
|------|------|
| `query_knowledge` | 检索知识（FTS5 全文搜索 + 分层返回） |
| `write_knowledge` | 写入知识（异步入队，LLM 异步提炼） |
| `calibrate_knowledge` | 校准知识（检测过时条目） |

---

## 知识生命周期

```
DRAFT → CANDIDATE → ACTIVE → COLD → STALE → DEPRECATED
```

每条知识在 4 个维度上标注：**Lx**（粒度 L0-L3）× **Sy**（稳定性 S1-S5）× **Depth**（认知深度 KW/KH/KY）+ **Domain**（业务领域）。

晋升公式：`base_score = confidence×0.70 + anchor_bonus×0.15 + calibration_recency×0.15`

---

## 配置

环境变量（`DEVCONTEXT_` 前缀）：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_PROVIDER` | LLM 供应商 | `openai` |
| `LLM_MODEL` | LLM 模型 | `MiniMax-Text-01` |
| `LLM_BASE_URL` | LLM API 地址 | `https://api.minimax.chat/v1` |
| `DB_PATH` | 数据库路径 | `.devContextMemo/devcontextmemo.db` |
| `HOST` | 服务地址 | `127.0.0.1` |
| `PORT` | 服务端口 | `9020` |

---

## 测试

```bash
pytest                         # 全部测试
pytest -m unit                 # 单元测试
pytest -m integration          # 集成测试
pytest --cov=src --cov-report=html  # 覆盖率
```

---

## 目录结构

```
.devContextMemo/                         # 数据目录
├── knowledge/<domain>/        # 活跃知识（MD 权威源）
├── staging/                   # 待审核知识
├── deprecated/                # 已废弃知识
├── quarantined/               # 安全隔离
├── AGENTS.knowledge.md        # L1 恒常注入
└── devcontextmemo.db          # SQLite 索引（可重建）

~/.devcontext/raw/<project>/   # 原始会话存储（JSONL）
```
