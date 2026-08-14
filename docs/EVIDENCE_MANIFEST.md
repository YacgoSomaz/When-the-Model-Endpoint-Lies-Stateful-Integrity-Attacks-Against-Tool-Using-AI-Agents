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

未经脱敏的原始聊天、真实服务器配置、API Key、SSH 凭据、身份路径和生产日志不进入 Git。完整 Agent 提示只以身份脱敏样本保存，并在公开前单独审查知识产权与披露风险。
