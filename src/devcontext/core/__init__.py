"""核心业务逻辑层 — 管理引擎 + 处理流水线 + 数据源适配器。

包含：
- adapters/: 多数据源适配器（统一接收层）
- pipeline/: 8 Step 写入流水线
- calibration.py: 校准引擎
- conflict.py: 冲突检测引擎
- promotion.py: 晋升评估
- pruning.py: 修剪规则
- health.py: 数据健康引擎
- init.py: 冷启动引擎
"""
