# 远见 v0.5

远见是一个只在 Windows 本机运行的外部认知雷达。它持续读取公开信息，把同一事件的多篇报道合并，区分单源线索与多源证据，生成结构化判断，再在本机映射到个人利益和候选预测。

## 核心能力

- RSS/Atom、GDELT JSON、公开网页列表采集，失败状态和15/30/60分钟退避可见。
- 72小时事件聚类；中文、英文、数字、金额、比例和日期参与相似度计算。
- 独立域名与本地标记的官方来源形成 E1—E4 证据等级，同域转载不冒充互证。
- 6小时、24小时、7天、30天趋势；历史不足或样本少时不制造“升温”结论。
- 断网可用的本地研判，输出事实、参与者、因果链、不确定性、时间窗和反证触发器。
- 可选 OpenAI Responses API 严格结构化输出；默认关闭，无密钥、认证失败、限流、超时或非法输出时退回本地。
- 私人利益只在本机映射。E1 无论多重要都不得超过 L3。
- 候选预测必须人工选择固定概率后，才能进入不可变预测账本。
- 单实例后台、登录启动选项、运行状态、6小时通知节流和本地通知中心。
- 只读索引 Obsidian；不写回原文章库。

## 安全边界

程序只监听 `127.0.0.1`。运行数据保存在 `%LOCALAPPDATA%\YuanJian`，不放在源码或安装目录。

外部 AI 最多接收8个公开来源和12,000字符，只包含公开标题、摘要、网址、域名、时间和通用类别。精确地址、生日、家庭关系、医疗、债务、账户、Obsidian原文、私人利益图和预测历史不得外发。API 密钥使用 Windows 当前用户 DPAPI 加密，不写数据库、日志或源码。

软件不会自动借贷、投资、发送外部消息，或替用户作医疗、法律决定。采集不绕过 TLS、登录、付费墙或反爬。

## 测试与构建

```powershell
$env:PYTHONPATH='src'
$env:PYTHONWARNINGS='error::ResourceWarning'
python -m unittest discover -s tests -v
powershell -ExecutionPolicy Bypass -File build\build_windows.ps1
```

打包烟测：

```powershell
powershell -ExecutionPolicy Bypass -File tools\smoke_packaged.ps1 -ExePath 'dist\YuanJian\YuanJian.exe'
```
