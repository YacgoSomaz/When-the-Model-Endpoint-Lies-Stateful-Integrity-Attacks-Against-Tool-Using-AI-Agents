# 受控完整性实验台

该实验台在客户端和 OpenAI 兼容模型端点之间插入一个人工审批层，可观察并编辑完整 Chat Completion 请求和响应。它用于回答“如果模型通道被改写，Agent 会如何行动”，不用于生产代理。

## 页面与端点

- `/chat`：普通聊天客户端；
- `/console`：请求/响应审批与会话粘性规则；
- `/openai/v1/chat/completions`：网页聊天入口；
- `/workbuddy/v1/chat/completions`：固定实验会话入口；
- `/workbuddy/session/<id>/v1/chat/completions`：独立实验会话入口；
- `/artifacts/safe-demo-package.zip`：由本仓库脚本生成的无害载荷。
- `/diag-receive`：只接受 `127.0.0.1` 的 TC-005 固定字段诊断事件；
- `/api/console/test-case`：显示当前隔离测试场景；
- `/api/console/diagnostics`：显示最近的回环诊断事件。

## 安全机制

- 默认仅监听回环地址；
- 必须设置 `LAB_ACKNOWLEDGEMENT=CONTROLLED_RESEARCH_ONLY` 才接受模型请求；
- API Key 不进入控制台响应、不写日志，开始上游转发后立即从内存记录删除；
- 待审批记录 15 分钟过期，会话规则 2 小时过期；
- 主动限制同时待处理数量和请求体大小；
- 安全载荷只含 README 与 manifest，不含可执行内容。
- 受限基准 Agent 没有 shell、任意路径读取、真实截图、真实环境扫描或任意网络客户端；
- 测试变更审计只保存 JSON 路径与前后 SHA-256，不复制提示词或回答。

该原型仍会在内存中短暂接触明文 Key 和消息。因此它不是“零信任”解决方案，不能部署到不可信主机。

## 启动

```powershell
$env:LAB_GATEWAY_URL = "https://api.deepseek.com/chat/completions"
$env:LAB_ACKNOWLEDGEMENT = "CONTROLLED_RESEARCH_ONLY"
$env:LOG_VIEWER_USER = "researcher"
$env:LOG_VIEWER_PASSWORD = "replace-me"
python ..\scripts\build_safe_artifact.py
python ..\scripts\build_test_fixtures.py
python app.py
```

若用于 Agent 客户端，把模型 URL 指向本地 `/workbuddy/v1/chat/completions`；使用真实但低额度、可随时撤销的测试 Key。实验结束立即撤销 Key、停止服务并删除工作区产物。

七个场景的范围、启动方法、判定口径与验收模板见 [`../docs/TEST_CASES.md`](../docs/TEST_CASES.md)。
