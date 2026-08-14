# 当模型端点不可信

> **When the Model Endpoint Lies: Stateful Integrity Attacks Against Tool-Using AI Agents**
> 私有、受控、负责任披露优先的 AI Agent 完整性研究项目。

## 项目要回答的问题

当一个工具型 AI Agent 使用“OpenAI 兼容”的模型地址时，用户看到的模型名称、API 地址和最终界面，并不能证明请求与响应在途中没有被改写。若中转层能够修改：

- 用户发给模型的消息；
- 模型返回的自然语言；
- `tool_calls` / `function_call` 参数；
- Agent 后续轮次携带的历史上下文；

那么一次看似普通的对话，可能被转换成非预期的工具行为。真正需要研究的不是一次性替换文本，而是篡改如何沿 Agent 的多轮循环持续传播，以及系统应在哪一层验证“用户意图”和“工具执行意图”的一致性。

## 当前结论（尚非漏洞定论）

我们已在自有账号、自有 API Key、自有服务器和无害载荷下完成一次受控复现：

1. 测试者在 Agent 客户端只输入普通问候；
2. 授权的实验网关在请求发送给模型前修改任务描述；
3. 模型生成了下载无害 ZIP 的工具调用；
4. Agent 执行下载并在工作区内保存文件；
5. 后续模型调用计算 SHA-256，验证文件完整性；
6. 测试包不含程序、脚本、宏、安装器或回连逻辑。

这证明“模型通道的完整性失效可能影响 Agent 工具行为”在该测试配置中具有可观测性；它**不等于**已经证明某个具体产品存在可利用漏洞，也不证明恶意程序能够绕过系统权限、用户审批或终端防护。产品级结论必须经过版本确认、对照实验、厂商沟通和独立复核。

## 研究愿景

我们希望推动四件事：

1. 让普通用户理解：正确的界面文字或模型 URL，并不自动等于可信的数据路径；
2. 让 Agent 开发者把模型输出当作不可信输入，而不是天然可信的控制指令；
3. 建立可重复、可审计、不会伤害真实用户的完整性测试方法；
4. 与安全研究者和厂商共同形成可落地的防御基线，再决定是否公开完整材料。

项目当前保持私有。公开时间取决于：解决方案成熟度、专业同行复核、受影响厂商沟通与负责任披露窗口，而不是传播效果。

## 仓库地图

- [`lab/`](lab/)：本地优先的 OpenAI 兼容请求/响应审批实验台；
- [`evidence/experiment-001/`](evidence/experiment-001/)：首个无害下载实验的脱敏证据；
- [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md)：信任边界、攻击面与不变量；
- [`docs/FINDINGS.md`](docs/FINDINGS.md)：目前观察和结论边界；
- [`docs/MITIGATIONS.md`](docs/MITIGATIONS.md)：客户端、网关、Agent 与厂商侧防御；
- [`docs/EXPERIMENT_MATRIX.md`](docs/EXPERIMENT_MATRIX.md)：后续受控实验矩阵；
- [`docs/PAPER_OUTLINE.md`](docs/PAPER_OUTLINE.md)：论文/技术报告结构；
- [`docs/VIDEO_STORYBOARD.md`](docs/VIDEO_STORYBOARD.md)：面向公众的安全演示脚本；
- [`ETHICS.md`](ETHICS.md)、[`SECURITY.md`](SECURITY.md)、[`RESPONSIBLE_DISCLOSURE.md`](RESPONSIBLE_DISCLOSURE.md)：研究边界和披露规则。

## 快速开始

要求 Python 3.11+，代码只使用标准库。

```powershell
cd lab
Copy-Item ..\.env.example .env
$env:LAB_GATEWAY_URL = "https://api.deepseek.com/chat/completions"
$env:LOG_VIEWER_USER = "researcher"
$env:LOG_VIEWER_PASSWORD = "请换成长随机密码"
python ..\scripts\build_safe_artifact.py
python app.py
```

默认只监听 `127.0.0.1:8001`。浏览器访问：

- 聊天页：`http://127.0.0.1:8001/chat`
- 审批控制台：`http://127.0.0.1:8001/console`
- Agent 兼容地址：`http://127.0.0.1:8001/workbuddy/v1/chat/completions`

真实 API Key 由客户端以 Bearer Key 发送，只在内存中保留到上游转发开始；控制台 API 不返回 Key，服务也不记录请求头。不要在共享主机、公网或生产账号上运行实验。

## 测试

```powershell
python -m unittest discover -s lab -p "test_*.py" -v
python scripts/verify_safe_artifact.py
python scripts/scan_secrets.py
```

## 安全边界

允许：自有或明确授权系统、无害文件、工作区内写入、哈希验证、可撤销且可审计的模拟。

禁止：真实恶意软件、持久化、权限提升、凭据获取、规避安全产品、未授权第三方系统、隐蔽部署、诱导真实用户执行未知载荷。

完整规则见 [`ETHICS.md`](ETHICS.md)。

## 语言与署名

主要研究记录使用中文，关键概念保留英文术语，便于后续形成双语论文、厂商建议书和公开演示。本仓库在协调披露完成前不授予公开使用许可，详见 [`NOTICE.md`](NOTICE.md)。
