# devContextMemo（码上记忆）使用手册 V1.0

> **版本**：V1.0 | **日期**：2026-06-19 | **适用版本**：devcontext v0.1.0
> **一句话**：对话沉淀知识，编码随时唤醒

---

## 一、项目简介

devContextMemo 是一个项目知识管理工具，自动将 AI 编程工具（OpenCode、Comate、Cursor 等）的对话记录提炼为结构化知识，并通过 MCP Tool 按需注入 AI 上下文。

**核心价值**：让你和 AI 之间的每一次对话都变成可累积的项目知识资产。

**技术栈**：Python 3.13 + FastAPI + FastMCP + SQLite（WAL 模式）+ Typer CLI

---

## 二、安装

### 2.1 环境要求

- Python >= 3.13
- pip / uv（包管理器）

### 2.2 安装步骤

```bash
# 1. 进入项目目录
cd /path/to/devContextMemo

# 2. 创建虚拟环境
python3.13 -m venv .venv
source .venv/bin/activate

# 3. 安装依赖
pip install -e ".[dev]"

# 4. 验证安装
devcontext --help
```

**输出示例**：
```
Usage: devcontext [OPTIONS] COMMAND [ARGS]...
  码上记忆（devContextMemo）CLI 工具
```

---

## 三、快速开始

### 3.1 初始化项目

在目标项目根目录运行：

```bash
devcontext init
```

**效果**：创建 `.devContextMemo/` 目录结构 + 初始化 SQLite 数据库 + 生成 `AGENTS.knowledge.md` 骨架。

```
✓ 创建 .devContextMemo/knowledge
✓ 创建 .devContextMemo/staging
✓ 创建 .devContextMemo/deprecated
✓ 创建 .devContextMemo/quarantined
✓ 初始化数据库 (8 张表)
✓ 创建 .devContextMemo/AGENTS.knowledge.md...done!...done!

devContextMemo 初始化完成！
下一步：开始编码对话，系统会自动采集知识。
```

如需覆盖已有配置：`devcontext init --force`

---

## 四、CLI 命令详解

### 4.1 `devcontext status` — 查看知识库状态

```bash
devcontext status              # 查看全局统计
devcontext status --domain order  # 按领域过滤
```

**输出内容**：总知识数、按状态分布（active/cold/stale/...）、按领域分布（含平均置信度）、待审核提醒。

### 4.2 `devcontext review` — 审核待定知识

知识从写入到激活需要人工审核，这是系统的安全闸门。

#### 列出待审核知识

```bash
devcontext review list              # 列出所有待审核
devcontext review list --status draft  # 按状态过滤
```

**支持的过滤状态**：`draft` / `candidate` / `pending_review`

#### 审核操作

```bash
devcontext review approve <ID>      # 采纳知识 → 进入 active
devcontext review reject <ID>       # 拒绝知识 → 进入 deprecated
devcontext review reject <ID> --reason "信息过时"  # 带原因拒绝
devcontext review restore <ID>      # 恢复已废弃知识 → staged
```

**审核工作流**：
```
AI 写入知识 → DRAFT
   ↓ 人工审核 list
   ├─ approve  → ACTIVE（参与检索和注入）
   ├─ reject   → DEPRECATED（不参与检索）
   └─ 搁置     → 等待 dev dream 巩固评估
```

### 4.3 `devcontext dream` — 知识巩固

定期运行，对知识库进行维护：晋升 + 修剪 + 校准。

```bash
devcontext dream                    # 完整巩固（Phase 1: 晋升+修剪, Phase 2: 校准）
devcontext dream --dry-run          # 预览模式，不实际修改
devcontext dream --skip-calibrate   # 只做巩固，跳过校准
devcontext dream --scope order      # 限定领域范围
```

**巩固报告示例**：
```
Phase 1: 巩固评估
┌────────────┬──────┐
│ 指标       │ 数量 │
├────────────┼──────┤
│ 扫描总数   │  156 │
│ 晋升       │   12 │
│ 修剪       │    3 │
│ 标记 STALE │    5 │
│ 标记 COLD  │    8 │
│ 文件移动   │   12 │
│ 错误       │    0 │
└────────────┴──────┘

Phase 2: 校准检查
  检查 89 条，发现 3 条可能过时
```

**建议运行频率**：每天 1 次或每次编码会话结束后。

### 4.4 `devcontext config` — 配置管理

```bash
devcontext config                  # 查看全部配置项
devcontext config get db_path      # 查看单项配置
devcontext config set llm_model "MiniMax-Text-01"  # 设置配置
```

**可配置项**：
| 配置项 | 说明 | 默认值 |
|-------|------|--------|
| `db_path` | SQLite 数据库路径 | `.devContextMemo/devcontextmemo.db` |
| `knowledge_dir` | 活跃知识目录 | `.devContextMemo/knowledge` |
| `staging_dir` | 待审核目录 | `.devContextMemo/staging` |
| `deprecated_dir` | 已废弃目录 | `.devContextMemo/deprecated` |
| `quarantined_dir` | 隔离目录 | `.devContextMemo/quarantined` |
| `llm_provider` | LLM 供应商 | `openai` |
| `llm_model` | LLM 模型 | `MiniMax-Text-01` |
| `llm_base_url` | LLM API 地址 | `https://api.minimax.chat/v1` |
| `host` | 服务绑定地址 | `127.0.0.1` |
| `port` | 服务端口 | `9020` |

---

## 五、MCP Tool 接口（供 AI 编程工具调用）

devContextMemo 通过 MCP（Model Context Protocol）暴露 3 个 Tool 给 AI 编程工具（OpenCode 等），实现知识检索、写入和校准。

### 5.1 `query_knowledge` — 检索知识

**参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `query` | string | * | 自然语言查询（与 `id` 互斥） |
| `id` | string | * | 知识 ID 精确查询（与 `query` 互斥） |
| `domain` | string | | 领域过滤（如 `order`） |
| `depth` | string | | 深度过滤（`KW` / `KH` / `KY`） |
| `stability_min` | string | | 最低稳定性（`S1`-`S5`） |
| `limit` | int | | 返回条数（默认 5，最大 20） |
| `offset` | int | | 翻页偏移（默认 0） |
| `include_full` | bool | | 是否返回完整正文（默认 false） |

**分层返回策略**：
- `include_full=false`：返回摘要 + 元数据（L0 层，~200 tokens/条）
- `include_full=true`：返回完整 MD 正文（从文件系统读取，不在 DB 中）

**调用示例**：
```json
{
  "tool": "query_knowledge",
  "params": {
    "query": "支付流程怎么处理超时",
    "domain": "payment",
    "depth": "KH",
    "limit": 5,
    "include_full": false
  }
}
```

**响应示例**：
```json
{
  "items": [
    {
      "id": "kw-abc123",
      "title": "支付超时处理",
      "domain": "payment",
      "granularity": "L3",
      "stability": "S3",
      "depth": "KH",
      "summary": "支付超时 60s，使用定时任务轮询...",
      "confidence": 0.92,
      "code_verified": 1,
      "concept_tags": ["payment", "timeout", "scheduler"]
    }
  ],
  "total": 1,
  "has_more": false,
  "next_action": {
    "tool": "query_knowledge",
    "hint": "use id + include_full=true for full content",
    "params_example": {"id": "kw-abc123", "include_full": true}
  }
}
```

### 5.2 `write_knowledge` — 写入知识

**参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `content` | string | ✓ | 知识正文（最大 10000 字符） |
| `session_id` | string | ✓ | 来源会话 ID |
| `granularity` | string | | 粒度 L0-L3（可选，系统推断） |
| `stability` | string | | 稳定性 S1-S5（可选） |
| `depth` | string | | 深度 KW/KH/KY（可选） |
| `priority` | string | | 优先级 normal/high |

**调用示例**：
```json
{
  "tool": "write_knowledge",
  "params": {
    "content": "订单服务使用状态机模式管理订单生命周期的 7 个状态：PENDING → PAID → SHIPPING → DELIVERED → CANCELLED / REFUNDED / RETURNED。关键不变量：CANCELLED 只能从 PENDING 进入。",
    "session_id": "session-123",
    "granularity": "L3",
    "stability": "S2",
    "depth": "KW"
  }
}
```

**响应示例**：
```json
{
  "task_id": "write-kw-def456",
  "status": "accepted",
  "message": "已入队，将在异步提炼后自动确认。",
  "estimated_time": "pending (typically 30-120s, depends on LLM latency)"
}
```

### 5.3 `calibrate_knowledge` — 校准知识

检测已有知识是否因代码变更而过时。

**参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `scope` | string | | 校准范围（默认 `all`） |
| `mode` | string | | 校准模式（`quick` / `full`，默认 `quick`） |
| `since` | string | | 仅校准该时间后未校验的知识 |

**调用示例**：
```json
{
  "tool": "calibrate_knowledge",
  "params": {
    "scope": "domain:payment",
    "mode": "quick"
  }
}
```

---

## 六、REST API

### 6.1 健康检查

```bash
GET /api/health
```

### 6.2 知识 CRUD

```bash
GET    /api/knowledge?domain=order&limit=20    # 搜索知识
GET    /api/knowledge/{id}                      # 获取单条知识
POST   /api/knowledge                           # 写入知识
PUT    /api/knowledge/{id}                      # 更新知识
DELETE /api/knowledge/{id}                      # 废弃知识
```

---

## 七、配置说明

### 7.1 环境变量（`.env`）

所有配置以 `DEVCONTEXT_` 为前缀：

```bash
# LLM 配置
DEVCONTEXT_LLM_PROVIDER=openai
DEVCONTEXT_LLM_API_KEY=your-api-key
DEVCONTEXT_LLM_BASE_URL=https://api.minimax.chat/v1
DEVCONTEXT_LLM_MODEL=MiniMax-Text-01

# 服务配置
DEVCONTEXT_HOST=127.0.0.1
DEVCONTEXT_PORT=9020

# 路径配置（相对路径自动基于项目根目录）
DEVCONTEXT_DB_PATH=.devContextMemo/devcontextmemo.db
DEVCONTEXT_KNOWLEDGE_DIR=.devContextMemo/knowledge
DEVCONTEXT_STAGING_DIR=.devContextMemo/staging
DEVCONTEXT_DEPRECATED_DIR=.devContextMemo/deprecated
DEVCONTEXT_QUARANTINED_DIR=.devContextMemo/quarantined

# 冲突仲裁阈值
DEVCONTEXT_ARBITRATION_AUTO_ADOPT_THRESHOLD=0.30
DEVCONTEXT_ARBITRATION_MANUAL_REVIEW_THRESHOLD=0.10
```

### 7.2 CLI 动态配置

也可通过 `devcontext config set` 命令动态修改（写入 `.env` 文件），无需手动编辑。

---

## 八、目录结构

### 8.1 数据目录（`.devContextMemo/`）

```
.devContextMemo/
├── knowledge/             # 活跃知识 MD 文件（按领域分目录）
│   ├── order/
│   ├── payment/
│   ├── architecture/
│   └── standards/
├── staging/               # 待审核知识（draft/candidate/pending_review）
├── deprecated/            # 已废弃知识
├── quarantined/           # 安全隔离（提示注入/凭据泄露等）
├── AGENTS.knowledge.md    # 自动维护的 L1 恒常注入文件
└── devcontextmemo.db      # SQLite 索引数据库（可随时从 MD 重建）
```

### 8.2 原始数据目录（`~/.devcontext/`）

```
~/.devcontext/
└── raw/<project>/         # 原始会话存储（统一 JSONL 格式，永久保留）
    ├── session_<uuid>.jsonl    # OpenCode 适配器输出
    └── session_<uuid>.jsonl    # Comate/Cursor 适配器输出
```

---

## 九、知识生命周期

知识从写入到废弃经历 8 个阶段：

```
DRAFT → STAGED → CANDIDATE → ACTIVE → COLD → STALE → DEPRECATED
  │        ↑         │          │                 │
  │   PENDING_REVIEW  │          │                 │
  └───────────────────┴──────────┴─────────────────┘
```

| 阶段 | 位置 | 说明 |
|:--:|------|------|
| DRAFT | staging/ | LLM 提炼的初稿，待审查 |
| STAGED | staging/ | 已审查通过，待晋升评估 |
| PENDING_REVIEW | staging/ | 异常/低置信度，需人工审核 |
| CANDIDATE | staging/ | 评分达标，等待二次确认 |
| ACTIVE | knowledge/ | 活跃使用中，参与检索和注入 |
| COLD | knowledge/ | 长期未使用但保留 |
| STALE | knowledge/ | 可能过期（suspicious/confirmed/deep 3 子阶段） |
| DEPRECATED | deprecated/ | 已失效，不参与检索 |

**晋升公式**：
```
base_score = confidence × 0.70 + anchor_bonus × 0.15 + calibration_recency × 0.15
```
- ≥ 0.95：绿色通道直接进入 knowledge/
- ≥ 0.82：进入 CANDIDATE
- < 0.80：退回 PENDING_REVIEW

---

## 十、知识分类体系（三元组 + 领域）

每条知识在 4 个维度上标注：

### Lx 粒度（空间定位）
| L0 全局 | L1 领域 | L2 子域 | L3 代码入口 |
|---------|---------|---------|-------------|

### Sy 稳定性（时间定位）
| S1 原则 | S2 架构 | S3 规范 | S4 实现 | S5 经验 |
|---------|---------|---------|---------|---------|

### Depth 认知深度
| KW Know-What | KH Know-How | KY Know-Why |
|:--:|:--:|:--:|
| "是什么" | "怎么做" | "为什么" |

### Domain 业务领域
决定文件存储目录（order / payment / architecture / standards 等）。

---

## 十一、三层注入机制

知识通过三层机制注入 AI 上下文：

| 层 | 内容 | 触发方式 | Token 预算 |
|:--:|------|---------|:--:|
| L1 恒常注入 | S1/S2 + KW 知识 | 每次会话自动加载到 AGENTS.md | ≤ 4K |
| L2 按需检索 | S3/S4 规范+实现 | AI 调用 `query_knowledge` | ~1-3K/call |
| L3 经验检索 | S5 经验/踩坑 | 排障时触发 | ~0.5-1.5K |

---

## 十二、常见工作流

### 12.1 新项目上手

```bash
devcontext init                    # 1. 初始化
devcontext status                  # 2. 查看状态（空库）
# ... 开始编码，AI 会自动采集知识 ...
devcontext review list             # 3. 审核第一批自动提炼的知识
devcontext review approve <ID>     # 4. 采纳靠谱的知识
devcontext dream                   # 5. 运行巩固
```

### 12.2 日常维护

```bash
devcontext status                  # 1. 查看知识库
devcontext review list             # 2. 审核新知识
devcontext dream                   # 3. 巩固维护
```

### 12.3 灾难恢复

```bash
# 如果 DB 文件损坏或丢失
devcontext config set db_path ".devContextMemo/devcontextmemo.db"  # 确认路径
# DB 可随时从 .devContextMemo/knowledge/ 下的 MD 文件重建
```

---

## 十三、测试

```bash
# 运行全部测试
pytest

# 按层级运行
pytest -m unit          # 单元测试
pytest -m module        # 模块测试
pytest -m integration   # 集成测试

# 按门禁运行
pytest -m l1_gate       # L1 快速门禁（pre-commit）
pytest -m l2_gate       # L2 标准门禁（pre-merge）
pytest -m l3_gate       # L3 强化门禁（nightly）

# 覆盖率报告
pytest --cov=src --cov-report=html
open .devcontext/test-evidence/coverage/index.html
```

---

## 十四、安全机制

写入知识库的内容在持久化前经过三层扫描：

| 层级 | 检测内容 | 处理方式 |
|:--:|------|------|
| L1 | 提示注入（模式匹配） | 拒绝写入 + 记录安全事件 |
| L2 | 凭据泄露（API Key / Token 正则） | 拒绝写入（高置信度）/ 标记疑似（低置信度） |
| L3 | Unicode 不可见字符 | 拒绝写入 |

---

## 十五、故障排查

| 问题 | 可能原因 | 解决方案 |
|------|---------|---------|
| `devcontext` 命令不存在 | 未安装或虚拟环境未激活 | `source .venv/bin/activate` 后重试 |
| `.devContextMemo/` 已存在 | 已初始化过 | 使用 `--force` 覆盖或手动删除后重试 |
| DB 为空但 MD 文件存在 | 索引未同步 | 删除 `.devContextMemo/devcontextmemo.db` 后重新初始化 |
| 检索结果不完整 | FTS5 索引过时 | 运行 `devcontext dream` 触发重建 |
| LLM 调用失败 | API Key 未配置 | `devcontext config set llm_api_key "your-key"` |

---

## 十六、版本历史

| 版本 | 日期 | 变更 |
|:--|------|------|
| V1.0 | 2026-06-19 | 初始版本，覆盖 CLI + MCP + 配置 + 生命周期 |
