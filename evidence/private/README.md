# 私有完整请求样本

本目录保存一份完整、结构化、经过身份脱敏的 WorkBuddy Chat Completion 请求，用于研究模型中转层的机密性与完整性风险。

## 文件

- `workbuddy-full-request.redacted.json`：完整消息、系统提示、工具 schema 和模型参数；
- `workbuddy-full-request.metadata.json`：原始文件哈希、脱敏文件哈希、字段规模和脱敏计数。
- `workbuddy-followup-request.redacted.json`：另一轮完整后续请求，用于观察 Agent 如何重新提交上下文；
- `workbuddy-followup-request.metadata.json`：后续请求的来源、脱敏哈希和规模。

## 保留内容

- 消息顺序和角色；
- 系统提示语义；
- 用户包装结构；
- 24 个工具定义及其参数 schema；
- 模型与生成配置。

第二个样本额外说明：Agent 后续轮次会重新组织并提交大量历史、任务状态和引用内容，因此只改写一轮消息并不能完整描述有状态风险。

## 已删除或替换

- API Key、Bearer Token 和 Cookie；
- 本机用户名、用户目录和可关联工作区路径；
- 邮箱、公网 IP 和敏感 URL 查询参数；
- 其他显式指定的身份字符串。

## 披露状态

本目录只适用于当前私有仓库。转为公开仓库前必须获得专业安全人员和相关厂商的复核，确认提示词知识产权、隐私、产品安全与协调披露要求。
