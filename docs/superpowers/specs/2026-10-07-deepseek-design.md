# DeepSeek 接入方案（2026-10-07 已确认单一云端密钥方案）

目标：现有 EduMind 使用 DeepSeek 完成实际教学内容生成，尽量只要求一个 API Key。

## 官方能力与范围

官方接口 https://api.deepseek.com/chat/completions；模型名可配置，按当前文档默认 deepseek-flash。
官方文档：https://api-docs.deepseek.com/guides/vision/ 和 https://api-docs.deepseek.com/api/list-models/。
文字与图片使用 DeepSeek；当前官方公开 API 没有项目所需的 embedding 和语音转写接口，不能伪装为 DeepSeek 功能。

## 推荐方案：单一云端密钥

- 实现 DeepSeek provider 与配置，覆盖备课意图识别、图谱提取、冲突判断、PPT/Word/提纲/试卷/HTML 生成和修改。
- 图片与视频抽帧理解接入 DeepSeek 图片输入格式。
- 知识库采用本地文本特征向量完成词面检索，无额外云端密钥；明确区别于语义 embedding。
- 本地特征索引与现有演示/百炼索引隔离，避免不同维度或含义的向量混用；切换后从已保存的文本重建索引，保留源文档和旧索引。
- Word/PPT/PDF 文本解析保留本地路径；MinerU 与联网搜索保留为可选服务。
- 语音暂时保留 stub 模式，在说明中明确这是演示转写。
- .env 中设置 LLM_PROVIDER=deepseek、DEEPSEEK_API_KEY 和可选 DEEPSEEK_MODEL；不在输出、日志、测试或版本控制中暴露密钥。
- 错误密钥、模型错误和异常响应明确报告，不能静默改用演示模型。

## 替代方案

1. DeepSeek 负责文字和图片，百炼负责语义 embedding 和真实语音，需要两家密钥，保留完整语义检索与语音功能。
2. 仅接入 DeepSeek 文字生成，其他服务维持原配置，改动少，但无法实现只填 DeepSeek Key 的完整知识库流程。

## 验证

先通过 httpx 模拟接口测试验证 DeepSeek 请求、图片输入、鉴权、异常响应和本地检索，再运行完整后端测试与前端构建。
配置切换后重启本项目后端；使用本机私有配置中的密钥进行小规模连通和实际备课验证。真实云端调用有正常的 API 用量计费。
演示模式端到端脚本继续在 stub 配置下执行；真实模型使用独立验收，避免依赖 TCP 固定示例的断言。
