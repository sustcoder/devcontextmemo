"""8 Step 写入流水线 — 对话日志 → 结构化知识 → 持久化 → 晋升。

Step 0: receiver      — 统一接收（适配器路由 + 原始存储）
Step 1: batcher       — JSONL 攒批
Step 2a: extractor    — LLM 知识提炼 + 分类 + 时间提取
Step 2b: entity_extractor — 实体 + 关系提取
Step 3: validator     — 签名 + 语义验证 + 安全扫描
Step 4: deduplicator  — Jaccard + 语义去重
Step 5: writer        — MD → DB 原子写入
Step 6: consolidator  — 晋升 + 修剪 + 巩固
"""
