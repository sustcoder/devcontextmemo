# devContextMemo Python 项目结构调研报告 V1.0

> **日期**：2026-06-17
> **目的**：调研 FastAPI + FastMCP 项目结构最佳实践，为 devContextMemo 项目编码实现做准备
> **适用范围**：本文档仅用于项目结构决策，不涉及功能设计

---

## 一、调研背景

devContextMemo 项目技术栈：
- **Web 框架**：FastAPI（Python 3.12+，推荐 3.13）
- **MCP Server**：FastMCP（挂载到 FastAPI 应用下）
- **数据库**：SQLite（Phase 1），PostgreSQL（Phase 2）
- **CLI 工具**：待选定（Typer / Click）
- **测试**：pytest
- **代码质量**：Black + Ruff + mypy

---

## 二、FastAPI 官方推荐项目结构

### 2.1 FastAPI 官方「Bigger Applications」指南

来源：https://fastapi.tiangolo.com/tutorial/bigger-applications/

官方推荐的目录结构：

```
app/
├── __init__.py
├── main.py                 # FastAPI 应用入口
├── dependencies.py          # 全局依赖注入
├── routers/                 # API 路由模块
│   ├── __init__.py
│   ├── items.py
│   └── users.py
├── models/                  # SQLAlchemy / SQLModel 数据模型
│   ├── __init__.py
│   └── models.py
├── schemas/                 # Pydantic 请求/响应模型
│   ├── __init__.py
│   ├── item.py
│   └── user.py
├── crud/                    # 数据库 CRUD 操作
│   ├── __init__.py
│   ├── item.py
│   └── user.py
└── internal/                # 内部辅助模块
    ├── __init__.py
    └── admin.py
```

**核心设计原则**：
1. **路由分离**：每个 `APIRouter` 聚合相关的端点
2. **模型分层**：数据模型（DB）与 Schema（API）分离
3. **依赖注入**：通过 FastAPI 的 `Depends()` 实现松耦合
4. **业务逻辑外置**：CRUD / Services 层独立于路由

### 2.2 FastAPI Full Stack Template（社区最佳实践）

来源：https://github.com/fastapi/full-stack-fastapi-template

更适用于中大型项目的结构：

```
app/
├── api/                     # API 路由层
│   ├── deps.py              # 依赖注入
│   └── routes/
│       ├── items.py
│       └── users.py
├── core/                    # 核心配置
│   ├── config.py            # Settings（pydantic-settings）
│   ├── security.py          # 认证/授权
│   └── db.py                # 数据库连接
├── models/                  # SQLAlchemy/SQLModel 模型
├── schemas/                 # Pydantic 请求/响应模型
├── services/                # 业务逻辑层
├── crud/                    # 数据库操作层
├── workers/                 # 后台任务（Celery / APScheduler）
├── tests/                   # 测试
└── main.py                  # 应用入口
```

**关键选型**：
- `core/config.py` 使用 `pydantic-settings` 管理配置
- `api/deps.py` 集中管理依赖注入
- `services/` 与 `crud/` 分离：业务逻辑 vs 数据访问

---

## 三、FastMCP 项目组织方式

### 3.1 FastMCP 核心概念

来源：https://github.com/jlowin/fastmcp

FastMCP 是一个用于构建 MCP (Model Context Protocol) 服务器的 Python 框架，可以：
- 独立运行（`mcp run`）
- 挂载到 FastAPI 应用下（`mcp.mount("/mcp", app)`）

**推荐组织方式**：

```
mcp/
├── __init__.py
├── server.py       # MCP Server 实例创建 + 挂载
├── tools.py        # Tool 函数定义
└── resources.py    # Resource 模板定义
```

### 3.2 与 FastAPI 的集成方式

```python
# src/coderecall/main.py
from fastapi import FastAPI
from fastmcp import FastMCP

app = FastAPI(title="devContextMemo")
mcp = FastMCP("devContextMemo MCP Server")

# 注册 tools
from src.coderecall.mcp.tools import search, dream, review
mcp.tool(search)
mcp.tool(dream)
mcp.tool(review)

# 注册 resources
from src.coderecall.mcp.resources import knowledge_item
mcp.resource("knowledge://{id}", knowledge_item)

# 挂载到 FastAPI
mcp.mount("/mcp", app)
```

### 3.3 关键约束

- **Tool 函数必须是 async def 或普通 def**
- **Resource 支持 URI 模板（如 `knowledge://{id}`）**
- **MCP Server 可通过 SSE 或 stdio 传输**

---

## 四、Python 打包规范（pyproject.toml）

### 4.1 PEP 621 标准化元数据

```toml
[project]
name = "coderecall"
version = "0.1.0"
description = "对话沉淀知识，编码随时唤醒 — 把对话与代码熔炼成永不腐烂的项目知识"
readme = "README.md"
requires-python = ">=3.12"
license = { text = "MIT" }
authors = [
    { name = "Your Name", email = "your@email.com" }
]
keywords = ["knowledge-management", "ai-coding", "mcp"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "Programming Language :: Python :: 3.13",
]

[project.scripts]
devContextMemo = "coderecall.cli.app:app"

[project.dependencies]
fastapi = ">=0.110.0"
fastmcp = ">=2.0.0"
uvicorn = { version = ">=0.29.0", extras = ["standard"] }
sqlmodel = ">=0.0.22"
aiosqlite = ">=0.20.0"
httpx = ">=0.27.0"
typer = ">=0.12.0"
rich = ">=13.7.0"
pydantic-settings = ">=2.2.0"
openai = ">=1.30.0"

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23.0",
    "ruff>=0.4.0",
    "black>=24.0",
    "mypy>=1.10",
    "pre-commit>=3.7.0",
]

[build-system]
requires = ["setuptools>=69.0", "wheel"]
build-backend = "setuptools.build_meta"
```

### 4.2 构建后端选型建议

| 后端 | 优势 | 劣势 | 建议 |
|------|------|------|:--:|
| setuptools | 最成熟，兼容性最好 | 配置略繁琐 | ✅ 推荐（Phase 1） |
| hatch | 现代，无需 setup.py | 生态较新 | ⏸️ Phase 2 迁移 |
| pdm | 类 npm 体验 | 团队接受度待验证 | ❌ |
| flit | 纯 Python 项目极简 | 无 binary 支持 | ❌ |

---

## 五、CLI 工具选型

### 5.1 候选方案对比

| 特性 | Typer | Click | argparse |
|------|-------|-------|----------|
| 与 FastAPI 集成 | ✅ 同作者（tiangolo） | ⚠️ 独立 | ❌ |
| 类型提示 | ✅ 原生支持 | ⚠️ 需手动 | ❌ |
| 自动生成帮助 | ✅ | ✅ | ⚠️ 需手动 |
| 异步支持 | ✅ | ⚠️ 有限 | ❌ |
| 嵌套命令 | ✅ | ✅ | ⚠️ 有限 |
| 社区活性 | ★★★★★ | ★★★★ | ★★ |

### 5.2 建议：Typer

devContextMemo 需要以下 CLI 命令：
- `dev review` — 知识审核交互
- `dev dream` — 知识主动扫描
- `devContextMemo config` — 配置管理
- `dev status` — 知识库状态

Typer 是 FastAPI 作者开发的，天然支持类型提示和异步，且与 FastAPI 项目风格统一。

---

## 六、最终推荐项目结构

基于以上调研，推荐 devContextMemo 项目结构：

```
coderecall/
├── pyproject.toml                   # 项目元数据 + 依赖（PEP 621）
├── .ruff.toml                       # Ruff 代码质量配置
├── .pre-commit-config.yaml           # pre-commit hooks
├── README.md
├── .gitignore
│
├── src/
│   └── coderecall/
│       ├── __init__.py              # 版本号
│       ├── main.py                  # FastAPI 应用 + FastMCP 挂载
│       ├── config.py                # 全局配置（pydantic-settings）
│       │
│       ├── core/                    # 核心业务逻辑
│       │   ├── __init__.py
│       │   ├── pipeline/            # 6 Step 写入流水线
│       │   │   ├── __init__.py
│       │   │   ├── collector.py     # Step 0: 采集
│       │   │   ├── batcher.py       # Step 1: 攒批
│       │   │   ├── extractor.py     # Step 2: 提炼
│       │   │   ├── validator.py     # Step 3: 验证
│       │   │   ├── deduplicator.py  # Step 4: 去重
│       │   │   ├── writer.py        # Step 5: 写入
│       │   │   └── consolidator.py  # Step 6: 巩固
│       │   ├── calibration.py       # 校准引擎（类级别代码校准 + 触发事件匹配）
│       │   ├── conflict.py          # 冲突检测引擎（L0-L5）
│       │   ├── promotion.py         # 晋升评估（V2.1 公式）
│       │   ├── pruning.py           # 修剪规则（三层体系）
│       │   ├── versioning.py        # 版本链管理（快照生命周期 + 追溯）
│       │   ├── health.py            # 数据健康引擎（9 类数据校正 H1-H9）
│       │   └── init.py              # 冷启动引擎（项目扫描 → LLM 骨架生成）
│       │
│       ├── models/                  # 数据模型层
│       │   ├── __init__.py
│       │   ├── knowledge.py         # KnowledgeItem（SQLModel）
│       │   ├── source.py            # Source（SQLModel）
│       │   ├── category.py          # Category（SQLModel）
│       │   └── enums.py            # 状态枚举（Depth, Status, etc.）
│       │
│       ├── schemas/                 # API 请求/响应模型
│       │   ├── __init__.py
│       │   ├── knowledge.py         # KnowledgeCreate/Update/Response
│       │   └── search.py           # SearchRequest/SearchResponse
│       │
│       ├── services/                # 业务逻辑层
│       │   ├── __init__.py
│       │   ├── knowledge.py         # 知识 CRUD + 检索
│       │   ├── pipeline.py          # 流水线编排
│       │   ├── review.py            # 审核流程
│       │   ├── dream.py             # 主动扫描
│       │   └── injection.py         # 知识注入服务（AGENTS.md 生成 + 三层路由）
│       │
│       ├── storage/                 # 存储层
│       │   ├── __init__.py
│       │   ├── markdown.py          # MD 文件操作（读/写/解析）
│       │   ├── sqlite.py            # SQLite 操作（连接/WAL/事务）
│       │   ├── search.py            # FTS5 全文搜索 + 语义重排
│       │   └── atomic.py          # 原子写入（MD→DB 顺序校验）
│       │
│       ├── mcp/                     # MCP Server 层
│       │   ├── __init__.py
│       │   ├── server.py            # MCP Server 实例 + 挂载
│       │   ├── tools.py             # Tool 函数定义（search/review/dream）
│       │   └── resources.py         # Resource 模板定义
│       │
│       ├── api/                     # REST API 路由层
│       │   ├── __init__.py
│       │   ├── deps.py              # 依赖注入（get_db, get_config）
│       │   └── routes/
│       │       ├── __init__.py
│       │       ├── knowledge.py     # /api/knowledge/...
│       │       └── health.py        # /api/health
│       │
│       ├── cli/                     # CLI 命令层
│       │   ├── __init__.py
│       │   ├── app.py               # Typer 应用入口
│       │   ├── init.py              # dev init（冷启动）
│       │   ├── review.py            # dev review
│       │   ├── dream.py             # dev dream
│       │   ├── config.py            # devContextMemo config
│       │   └── status.py            # dev status
│       │
│       └── utils/                   # 工具函数
│           ├── __init__.py
│           ├── hash.py              # 哈希（内容签名 + 语义签名）
│           ├── diff.py              # 差异比较（文件级 + AST 级）
│           ├── llm.py               # LLM API 封装（MiniMax + GLM）
│           ├── security.py          # 安全扫描器（提示注入/凭据/Unicode）
│           └── path.py             # 路径校验（realpath + 遍历防护）
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                  # pytest fixtures
│   ├── test_pipeline/              # 流水线测试
│   ├── test_calibration/           # 校准引擎测试
│   ├── test_conflict/              # 冲突检测测试
│   ├── test_mcp/                   # MCP Tool 测试
│   ├── test_storage/               # 存储层测试
│   └── test_api/                   # API 路由测试
│
└── scripts/
    ├── init_db.py                  # 初始化数据库
    ├── migrate.py                  # 数据库迁移（Phase 2）
    └── seed_data.py                # 测试数据生成
```

---

## 七、调研结论

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 项目根目录 | `src/coderecall/`（src-layout） | 遵循 PEP 517/621 标准，避免导入歧义 |
| 构建后端 | setuptools | 最成熟，社区支持最好 |
| 配置管理 | pydantic-settings | FastAPI 生态原生，类型安全 |
| CLI 框架 | Typer | FastAPI 同作者，类型提示原生支持 |
| 代码格式化 | Black | Python 社区标准 |
| 代码检查 | Ruff | 速度最快，功能最全 |
| 类型检查 | mypy | 社区标准，FastAPI 官方推荐 |
| HTTP 服务 | uvicorn | FastAPI 推荐 ASGI 服务器 |
| SQLite ORM | SQLModel（基于 SQLAlchemy） | 与 FastAPI 深度集成，支持 Pydantic |
| 依赖注入 | FastAPI Depends | 框架原生，无需第三方 |

---

## 八、参考资料

1. FastAPI Bigger Applications: https://fastapi.tiangolo.com/tutorial/bigger-applications/
2. Full Stack FastAPI Template: https://github.com/fastapi/full-stack-fastapi-template
3. FastMCP: https://github.com/jlowin/fastmcp
4. PEP 621: https://peps.python.org/pep-0621/
5. Typer: https://typer.tiangolo.com/
6. Ruff: https://docs.astral.sh/ruff/
