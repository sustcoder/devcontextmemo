"""工具函数层 — 贯穿各层的横切关注点。

包含：
- hash.py: 内容签名（SHA-256）+ 语义签名
- diff.py: 文件 Diff + AST 解析
- llm.py: LLM API 封装（MiniMax + GLM）
- security.py: 安全扫描器（提示注入/凭据/Unicode 检测）
- path.py: 路径校验（realpath + 遍历防护）
"""
