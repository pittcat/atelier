# atelier-common

> 跨 Agent 共享的基础库（占位实现）。

注意：当前只包含"足以让依赖装上、能 import 成功"的最小包。具体能力
（共享 LLM 客户端、tracing、auth utils、shell 工具 SDK）将由各 Agent 子包
直接复用其实现；后续抽公共部分时再合并进来。
