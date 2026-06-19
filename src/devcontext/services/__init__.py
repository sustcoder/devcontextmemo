"""业务逻辑层 — 编排业务流程，连接交互层与管理引擎层。

包含：
- knowledge.py: 知识 CRUD + 检索编排
- pipeline.py: 流水线编排（Step 0→6 全链路）
- review.py: 审核流程管理
- dream.py: 主动扫描（代码变更 → 知识校准）
- injection.py: 知识注入服务（AGENTS.md 生成 + 三层注入路由）
"""
