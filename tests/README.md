# devContextMemo 测试套件

本目录包含 devContextMemo 的完整测试体系，设计基于 AQE 质量门禁左移思想。

## 测试分层

```
tests/
├── unit/           # 单元测试 (~55 条) — 纯函数，零外部依赖
├── module/         # 模块测试 (~42 条) — 单 Step，mock 上游数据
├── integration/    # 集成测试 (~15 条) — Step 间数据契约兼容性
├── e2e/            # E2E 测试 (~12 条) — 全链路真实运行
├── contracts/      # YAML 契约文件 (8 个 Step)
└── fixtures/       # 共享测试数据 (JSON)
```

## 运行测试

```bash
# 全部单元测试 (pre-commit)
pytest tests/unit/ -v -m unit

# 模块测试 (pre-merge, L2 gate)
pytest tests/module/ -v -m module

# 集成测试 (pre-merge, L2 gate)
pytest tests/integration/ -v -m integration

# E2E 测试 (nightly, L3 gate)
pytest tests/e2e/ -v -m e2e

# 按风险门禁运行
pytest -m l1_gate   # 快速门禁
pytest -m l2_gate   # 标准门禁
pytest -m l3_gate   # 强门禁
```

## 编写测试原则

1. **单元测试**：零 I/O、零 LLM、零 DB。输入通过函数参数，输出通过返回值断言。
2. **模块测试**：用 mock 上游数据，验证单 Step 完整功能。不依赖上游模块 import。
3. **集成测试**：仅验证上游真实输出能否通过下游 validate_input()。
4. **E2E 测试**：全链路真实运行，标记 @pytest.mark.slow。

## 契约驱动开发

编码前先阅读 `contracts/` 目录下对应 Step 的 YAML 契约文件。
契约定义了输入/输出/断言/证据/失败模式。
