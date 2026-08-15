# 证据清单

| 路径 | 内容 | 敏感级别 | 公开状态 |
|---|---|---|---|
| `evidence/experiment-001/README.md` | 首次无害下载实验摘要 | 低（已脱敏） | 候选公开 |
| `evidence/experiment-001/timeline.json` | 事件序列，不含原始提示和身份信息 | 低（已脱敏） | 候选公开 |
| `evidence/experiment-001/hashes.txt` | 安全载荷历史样本哈希 | 低 | 候选公开 |
| `docs/PRIVATE_RESEARCH_NOTES.md` | 产品与研究状态备注 | 中（私有） | 披露前移除/改写 |
| `evidence/private/workbuddy-full-request.redacted.json` | 保留完整结构和语义的 WorkBuddy 请求 | 中（厂商提示词，已身份脱敏） | 私有；公开前复核 |
| `evidence/private/workbuddy-full-request.metadata.json` | 原始/脱敏哈希、规模和替换计数 | 低 | 候选公开 |
| `evidence/private/workbuddy-followup-request.redacted.json` | 后续轮次重新提交的上下文 | 中（已身份脱敏） | 私有；公开前复核 |
| `evidence/private/workbuddy-followup-request.metadata.json` | 后续请求的哈希、规模和替换计数 | 低 | 候选公开 |
| `lab/fixtures/` | TC-004/006/007 的合成、虚构输入 | 低 | 可公开 |
| `lab/audit-output/agent-audit.jsonl` | 本地 proposed/rejected/executed 事件 | 视实验内容而定 | 不入 Git；提交报告前脱敏 |
| `docs/TEST_CASES.md` | 七场景定义、边界与验收模板 | 低 | 可公开 |
| `docs/REPORT_TEMPLATE.md` | 面向安全团队的事实/推断分层报告模板 | 低 | 可公开 |
| `lab/workbuddy_canary_capture.ps1` | 固定 Canary 窗口采集与哈希收据客户端 | 低 | 可公开 |
| `evidence/private/canary-acceptance-20260816/` | 2026-08-16 全链路验收:四状态阶段记录、13 条收据哈希、磁带哈希 | 低（已脱敏） | 私有；公开前复核 |
| 控制台 TC-004 收据 | Canary 编号、尺寸、字节数、SHA-256、接收时间 | 低 | 候选公开；默认不含图片 |
| 保留模式 Canary 截图（可选） | 部署方显式设置 `CANARY_RETAIN_IMAGE=1` 时，内存中保留固定脚本自采窗口 PNG（TTL/数量上限，重启即清）；仅限 Canary 窗口载荷 | 低（测试窗口内容） | 私有；不随仓库提交；测试期接受无控制台认证的已知风险（2026-08-16），共享/生产环境启用前应同时启用控制台认证 |

未经脱敏的原始聊天、真实服务器配置、API Key、SSH 凭据、身份路径和生产日志不进入 Git。完整 Agent 提示只以身份脱敏样本保存，并在公开前单独审查知识产权与披露风险。
