# devContextMemo 编码规范 V1.0

> **日期**：2026-06-17
> **状态**：编码实现前最后一套设计交付物
> **适用范围**：devContextMemo 项目所有 Python 代码

---

## 一、代码格式化（Black）

### 配置

```toml
[tool.black]
line-length = 100
target-version = ["py313"]
include = '\.pyi?$'
extend-exclude = '''
/(
  \.git
  | \.venv
  | \.mypy_cache
  | build
  | dist
)/
'''
```

### 关键规则

- 行宽上限 100 字符（PEP 8 建议 79，现代化项目可放宽）
- 使用双引号
- 目标 Python 版本：3.13
- 每个文件末尾保留一个空行

---

## 二、代码检查（Ruff）

### 配置文件: `.ruff.toml`

```toml
target-version = "py313"

line-length = 100

exclude = [
    ".git",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    ".mypy_cache",
    ".pytest_cache",
]

[lint]
select = [
    # pycodestyle 错误
    "E",
    # pycodestyle 警告
    "W",
    # Pyflakes
    "F",
    # isort
    "I",
    # 命名规范
    "N",
    # pandas 向量化检查
    "PD",
    # pyupgrade
    "UP",
    # flake8-bugbear
    "B",
    # flake8-simplify
    "SIM",
    # flake8-comprehensions
    "C4",
    # flake8-print
    "T20",
    # flake8-quotes
    "Q",
    # pylint
    "PL",
]

ignore = [
    # 允许较长的函数体（本项目业务逻辑复杂）
    "PLR0913",  # too-many-arguments
    "PLR0912",  # too-many-branches
    "PLR0915",  # too-many-statements
    # 允许未使用的变量以 _ 开头
    "F841",
]

# isort 配置
[lint.isort]
known-first-party = ["coderecall"]
force-single-line = true

# 命名规范
[lint.flake8_quotes]
docstring-quotes = "double"

[format]
quote-style = "double"
indent-style = "space"
docstring-code-format = true
```

### 关键检查项

| 规则组 | 说明 | 级别 |
|--------|------|:--:|
| F (Pyflakes) | 未使用导入、未定义变量等 | 错误 |
| E/W (pycodestyle) | 缩进、空行、行宽等 | 错误/警告 |
| I (isort) | 导入顺序 | 警告 |
| N (pep8-naming) | 变量名、类名、函数名 | 警告 |
| B (bugbear) | 常见陷阱（mutable defaults 等） | 警告 |
| SIM (flake8-simplify) | 简化代码 | 建议 |

---

## 三、类型检查（mypy）

### 配置

```toml
[tool.mypy]
python_version = "3.13"
strict = false
warn_return_any = true
warn_unused_configs = true
warn_redundant_casts = true
disallow_untyped_defs = false
disallow_incomplete_defs = true
check_untyped_defs = true
no_implicit_optional = true
warn_unused_ignores = true

[[tool.mypy.overrides]]
module = [
    "fastmcp.*",
    "typer.*",
    "rich.*",
]
ignore_missing_imports = true
```

### 关键规则

- 所有公共 API 必须标注类型
- 使用 `Optional[X]` 代替 `X | None`（保持代码风格统一）
- 禁止隐式 Optional（`def f(x: str = None)` 需要 `Optional[str]`）

---

## 四、命名规范

### Python 标准命名约定

| 类型 | 约定 | 示例 |
|------|------|------|
| 模块 | snake_case | `deduplicator.py`, `knowledge_service.py` |
| 类 | PascalCase | `KnowledgeItem`, `CalibrationEngine` |
| 函数/方法 | snake_case | `extract_knowledge()`, `validate_signature()` |
| 变量 | snake_case | `knowledge_count`, `batch_size` |
| 常量 | UPPER_SNAKE_CASE | `MAX_RETRY_COUNT`, `DEFAULT_TIMEOUT` |
| 私有成员 | _leading_underscore | `_hash_content()`, `_db_connection` |
| 类型变量 | PascalCase | `T`, `K`, `V` |

### 项目特定约定

| 类型 | 约定 | 示例 |
|------|------|------|
| 流水线步骤文件 | `step_N_name.py` | `step_0_collector.py` → 简化为 `collector.py` |
| 引擎文件 | `引擎名.py` | `calibration.py`, `promotion.py` |
| CLI 命令 | `命令名.py` | `review.py`, `dream.py` |
| 测试文件 | `test_模块名.py` | `test_collector.py` |

---

## 五、注释规范（Google Style Docstrings）

### 模块级注释

```python
"""
模块：知识采集层

负责从 OpenCode 对话日志中采集原始交互数据，
支持 crash-recovery 和水位线机制。

主要类：
    Collector: 采集器主类，管理采集生命周期
    SessionReader: 会话日志读取器

使用示例：
    collector = Collector(config)
    await collector.collect(since=watermark)
"""
```

### 函数/方法注释

```python
async def extract_knowledge(
    self,
    conversation: Conversation,
    domain: str,
    *,
    max_retries: int = 3,
) -> KnowledgeItem:
    """从对话中提炼知识条目。

    使用 LLM 从原始对话中提取结构化领域知识，
    返回 DRAFT 状态的知识条目。

    Args:
        conversation: 原始对话对象，包含完整消息历史。
        domain: 目标业务领域（如 "payment"、"auth"）。
        max_retries: LLM 调用最大重试次数。

    Returns:
        提炼后的知识条目，状态为 DRAFT。

    Raises:
        LLMTimeoutError: LLM API 调用超时。
        ExtractionError: 知识提炼失败（内容质量不足）。

    Note:
        本方法内部会自动添加渐进截断惩罚，
        详见设计文档 Step2-提炼层-细化设计 V1.0 §3.4。
    """
    ...
```

### 类注释

```python
class CalibrationEngine:
    """类级别代码校准引擎。

    当检测到代码文件变更时，查找关联的知识条目，
    并通过 LLM 语义对比判断知识的有效性。

    核心约束：
        - 仅作为辅助信号，不直接改变知识状态
        - 精度需 ≥ L2（可对比的语义粒度）
        - 多文件关联时聚合判断

    Attributes:
        config: 全局配置实例。
        llm_client: LLM API 客户端。
        threshold: 校准置信度阈值（默认 0.75）。

    使用示例：
        engine = CalibrationEngine(config)
        results = await engine.calibrate(git_diff)
    """
```

---

## 六、Git 提交规范（Conventional Commits）

### 提交消息格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

### 类型定义

| Type | 说明 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat(pipeline): 实现 Step 0 采集层 crash-recovery` |
| `fix` | 修复 bug | `fix(storage): 修复 MD→DB 写入顺序导致的原子性断裂` |
| `refactor` | 重构（不改功能） | `refactor(calibration): 抽取 LLM 对比逻辑为独立方法` |
| `docs` | 文档更新 | `docs(design): 创建系统架构设计 V1.0` |
| `test` | 测试 | `test(pipeline): 添加 Step 3 签名验证单元测试` |
| `chore` | 构建/工具 | `chore: 配置 ruff + pre-commit hooks` |
| `style` | 代码格式 | `style: 应用 Black 格式化` |
| `perf` | 性能优化 | `perf(search): FTS5 全文搜索索引优化` |

### Scope 定义

| Scope | 对应模块 |
|-------|---------|
| `pipeline` | 6 Step 写入流水线 |
| `calibration` | 校准引擎 |
| `conflict` | 冲突检测引擎 |
| `promotion` | 晋升评估引擎 |
| `pruning` | 修剪规则引擎 |
| `init` | 冷启动引擎（dev init） |
| `health` | 数据健康引擎 |
| `injection` | 知识注入服务（AGENTS.md 生成 + 三层路由） |
| `security` | 安全扫描器 |
| `storage` | 存储层（MD + DB） |
| `mcp` | MCP Server |
| `api` | REST API |
| `cli` | CLI 命令 |
| `models` | 数据模型 |
| `utils` | 工具函数 |

### 提交频率要求

- 每个模块独立提交（不跨模块混合改动）
- 每个提交 ≤ 200 行代码变更（便于 review）
- 禁止包含 TODO 注释的提交（TODO 需要关联 Issue）

---

## 七、项目配置文件模板

### pyproject.toml 关键配置

```toml
[project]
name = "coderecall"
version = "0.1.0"
description = "对话沉淀知识，编码随时唤醒"
readme = "README.md"
requires-python = ">=3.12"
license = { text = "MIT" }

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

[tool.black]
line-length = 100
target-version = ["py313"]

[tool.ruff]
target-version = "py313"
line-length = 100

[tool.mypy]
python_version = "3.13"
```

### .pre-commit-config.yaml 模板

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-toml
      - id: check-added-large-files
        args: ['--maxkb=500']
      - id: detect-private-key

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.4
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        additional_dependencies:
          - pydantic>=2.7.0
          - sqlmodel>=0.0.22
        args: [--ignore-missing-imports]
```

> **注**：ruff-format 已覆盖代码格式化（替代 Black），避免两个工具规则冲突。

### .gitignore 模板

```gitignore
# Python
__pycache__/
*.py[cod]
*.so
*.egg-info/
dist/
build/
.eggs/

# Virtual environment
.venv/
venv/
env/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# MyPy
.mypy_cache/

# Pytest
.pytest_cache/
.coverage
htmlcov/

# OS
.DS_Store
Thumbs.db

# Project
*.db
*.db-journal
*.db-wal
*.db-shm

# Logs
*.log
logs/

# Environment
.env
.env.local
```

---

## 八、检视清单

编码完成后，每个 PR 必须通过以下检查：

| 检查项 | 工具 | 必须通过 |
|--------|------|:--:|
| 代码格式化 | `black --check .` | ✅ |
| Lint 检查 | `ruff check .` | ✅ |
| 类型检查 | `mypy src/` | ✅ |
| 单元测试 | `pytest tests/` | ✅ |
| 无未使用的导入 | `ruff check --select F401` | ✅ |
| 无 debug 代码 | `ruff check --select T20` | ✅ |
| 文档字符串完整 | 人工 Review | ⚠️ |
