# 架构

信息流按责任分层：

1. `external_sources.py`、`external_radar.py`：公网地址校验、采集、标准化、去重、缓存和失败状态。
2. `clustering.py`、`cognition.py`：72小时本地聚类、实体片段、独立域名、官方来源标记、证据哈希和 E1—E4。
3. `trends.py`：按类别建立小时快照，历史不足和小样本明确降级。
4. `judgments.py`：公开证据包、严格研判模式和离线本地提供者。
5. `remote_ai.py`、`secret_store.py`：默认关闭的 OpenAI Responses 适配器、每日预算、失败退避和 DPAPI。
6. `impacts.py`：结构化研判在本机映射到私人利益、L1—L4和候选预测。
7. `notifications.py`：通知冷却、本地中心和通用化 Windows 通知文本。
8. `runtime.py`、`startup.py`：单实例、运行发现、后台模式和当前用户登录启动；自启使用当前用户 Startup 目录的隐藏启动脚本，不依赖管理员权限或系统计划任务。
9. `forecasts.py`：人工确认后的不可变预测版本、结算和 Brier Score。
10. `radar_scheduler.py`：30秒采集检查、1分钟认知任务、1小时趋势任务；错误写入 `runtime_state`。
11. `http_api.py`、`static/`：只监听127.0.0.1、会话令牌保护的本地 API 和无 CDN 中文界面。

远程 AI 位于“公开证据 → 通用研判”之间。私人利益映射永远发生在 AI 返回之后，因此提供者接口无法访问私人利益表。历史研判和预测版本均不可修改或删除。
