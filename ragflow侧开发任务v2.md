# RAGFlow 侧开发任务 v2

生成时间：2026-07-01

依据文档：

- `多智能体时时交互系统ragflow侧开发任务.md`
- 当前代码核对结果
- 已通过的回归基线：`tools/run_agent_platform_regression.sh`

## 1. v2 目标

v2 不是重新建设智能体平台，而是在现有已完成基础上，把尚未完成的关键能力补齐到可被 `voice-project` 调度的生产级状态。

最终目标：

- 外部系统可以稳定指定 `agent_id + workflow_id + session_id + context` 调用 RAGFlow。
- 4 个 AI 老师拥有独立身份、工作流、知识库范围和输出格式。
- 每轮调用可以注入 `AITeacherTurnContext`，并返回结构化结果。
- 多老师并发调用时，run/session/context/trace/知识库范围互不串线。
- 共享文档写入只能通过 patch proposal + 单写者队列 + 版本校验完成。
- 前端可以配置、发布、调试这些 workflow。
- 公共接口不暴露 hidden chain-of-thought、prompt、密钥、节点完整输入输出。

## 2. 全局边界

所有阶段必须遵守以下边界：

- 不改聊天助手普通问答正文格式。
- 不改聊天助手 retrieving/thinking/answer 的现有输出样式。
- 不改普通问答流式输出节奏。
- 不把智能体 run 事件混入聊天助手会话事件。
- 不复用前端同一个临时状态对象，避免历史会话污染。
- 不在 RAGFlow 内实现 `voice-project` 的上帝调度主循环。
- 不在 RAGFlow 内实现 ASR、TTS 播放仲裁、数字人口型同步。
- 不允许智能体直接改共享文档、课程材料、知识库原文或长期记忆原文。
- 不返回 hidden chain-of-thought，只返回 `trace_summary`。
- 不为了调试方便绕过 agent/workflow/dataset/artifact 权限。

## 3. 当前已完成基线

当前已经具备的基础：

- 后端回归脚本通过：`tools/run_agent_platform_regression.sh`，138 个测试通过。
- 已有 `AgentPublicResponseService` 公共响应过滤层。
- 已有 `/agents/<agent_id>/invoke`、background run、meeting runs、run result 等接口基础。
- 已有 meeting memory、meeting fan-out/fan-in 服务基础。
- 已有请求级 `request_dataset_ids/dataset_scope` 与节点配置取交集的检索边界。
- 已有 `AgentDocumentWriteCoordinatorService`，支持 snapshot、patch proposal、expected version、audit、rollback。
- 已有合规核对节点：
  - `ContractClauseExtractor`
  - `ComplianceChecklistGenerator`
  - `ClauseMatcher`
  - `ComplianceVerifier`
  - `RiskScorer`
  - `ComplianceReportComposer`
- 已有前端节点枚举、表单、连线类型测试基础。

v2 只处理未完成或未完全验收的能力。

## 4. 任务总览

| 阶段 | 主题 | 优先级 | 依赖 | 主要验收 |
| --- | --- | --- | --- | --- |
| V2-1 | workflow_id 真实绑定 | P0 | 现有 invoke/run API | agent 与 workflow 可独立传入并校验 |
| V2-2 | 标准外部响应补齐 | P0 | V2-1 | `latency_ms/error_code/trace_summary` 完整 |
| V2-3 | 4 个 AI 老师配置 | P0 | V2-1/V2-2 | 4 老师可独立调用，session 不串 |
| V2-4 | AITeacherTurnContext 完整接入 | P0 | V2-1/V2-3 | context/hash/禁用内容/回应对象可用 |
| V2-5 | runtime timeout/cancel/deadline | P1 | V2-2 | 超时、取消、失败不阻塞其他 run |
| V2-6 | 知识库权限与标准库 metadata | P1 | V2-4 | 私有库隔离，版本/生效范围可追踪 |
| V2-7 | AI 老师 workflow 模板 | P1 | V2-3/V2-6 | 课前、课堂、课后模板可发布 |
| V2-8 | 文档核对模板端到端 | P1 | V2-6/V2-7 | 合同核对报告可下载且引用可追溯 |
| V2-9 | 前端画布与调试 smoke | P1 | V2-1 至 V2-8 | 创建、配置、发布、调试可用 |
| V2-10 | 安全、审计、prompt injection | P0 | 全阶段 | 越权拒绝、trace 过滤、审计完整 |
| V2-11 | voice-project 联调验收 | P0 | V2-1 至 V2-10 | 单老师、4 老师并发、写入协调通过 |

## 5. V2-1：workflow_id 真实绑定

### 目标

让外部调用可以传入：

```json
{
  "agent_id": "teacher_a",
  "workflow_id": "workflow_lesson_talk_v3"
}
```

并由 RAGFlow 校验该 workflow 是否属于这个 agent 或是否被授权绑定。

### 为什么要做

当前 `/agents/<agent_id>/invoke` 中 `workflow_id != agent_id` 会被拒绝。这只能支持“agent 自己就是 workflow”的简单模式，无法支持一个 AI 老师绑定多个发布 workflow，也无法支持课前、课堂、课后、核对等不同 workflow。

### 不做会怎样

- `voice-project` 无法指定具体 workflow。
- 同一个 AI 老师无法按场景切换思考流程。
- 后续 4 老师并发只能调用默认 agent，不能做到“老师身份”和“工作流版本”解耦。

### 怎么做

1. 增加 workflow binding 查询函数。
   - 输入：`tenant_id`、`agent_id`、`workflow_id`。
   - 输出：是否允许、workflow DSL、workflow version、release mode。
2. 修改 `/agents/<agent_id>/invoke`。
   - 不再要求 `workflow_id == agent_id`。
   - 如果没有传 `workflow_id`，默认使用 `agent_id` 对应发布 workflow。
   - 如果传了 `workflow_id`，必须经过绑定校验。
3. 修改 background run 创建逻辑。
   - run payload 保留 `agent_id` 和 `workflow_id`。
   - `agent_id` 用于身份、权限、老师私有知识库。
   - `workflow_id` 用于加载 DSL 和 workflow 版本。
4. 修改 run state。
   - 增加 `workflow_id`、`workflow_version`。
   - trace_summary 返回 workflow 信息。
5. 修改测试。
   - 补充 agent 与 workflow 匹配、不匹配、未授权、默认 workflow 的测试。

### 边界

- 不允许任意 agent 调用任意 workflow。
- 不允许外部请求直接传 DSL 绕过发布和权限。
- 不改变普通聊天助手接口。

### 达标标准

- `agent_id != workflow_id` 时，只要绑定合法，调用成功。
- 未绑定 workflow 返回 `WORKFLOW_AGENT_MISMATCH` 或 `PERMISSION_DENIED`。
- run state 和公共响应中同时返回 `agent_id`、`workflow_id`。
- trace_summary 中可看到 workflow version。

### 测试方法

- 单测：合法 binding 通过。
- 单测：非法 binding 被拒绝。
- 单测：不传 `workflow_id` 走默认 workflow。
- 接口测试：`POST /agents/<agent_id>/invoke` 指定合法 `workflow_id` 成功。
- 回归：`tools/run_agent_platform_regression.sh` 通过。

## 6. V2-2：标准外部响应补齐

### 目标

把外部响应固定为稳定 envelope：

```json
{
  "agent_id": "",
  "workflow_id": "",
  "run_id": "",
  "session_id": "",
  "message_id": "",
  "status": "",
  "answer": "",
  "intention": "",
  "target": "",
  "confidence": 0.0,
  "knowledge_used": [],
  "suggested_next_action": "",
  "references": [],
  "downloads": [],
  "trace_summary": {},
  "error_code": "",
  "error": null,
  "latency_ms": 0
}
```

### 为什么要做

`voice-project` 需要稳定字段做调度、播报、错误降级和审计。只返回一段自然语言不够用。

### 不做会怎样

- 上帝调度器无法读取意图、置信度和目标对象。
- 前端和外部系统难以区分失败类型。
- 长任务、超时和部分失败无法统一处理。

### 怎么做

1. 扩展 `AgentPublicResponseService.build_response`。
   - 增加 `latency_ms`。
   - 增加 `error_code` 顶层字段。
   - 支持 structured output 字段：
     - `intention`
     - `target`
     - `confidence`
     - `knowledge_used`
     - `suggested_next_action`
2. 从 final answer 中解析结构化输出。
   - 如果内容是 JSON，提取标准字段。
   - 如果不是 JSON，只填 `answer`，并标记 `structured_output_missing`。
3. 错误码统一。
   - `INVALID_ARGUMENT`
   - `WORKFLOW_AGENT_MISMATCH`
   - `AGENT_NOT_FOUND`
   - `SESSION_NOT_FOUND`
   - `PERMISSION_DENIED`
   - `WORKFLOW_TIMEOUT`
   - `AGENT_TIMEOUT`
   - `WORKFLOW_FAILED`
   - `DATASET_SCOPE_DENIED`
   - `INVALID_CONTEXT`
   - `INVALID_TARGET`
4. trace_summary 白名单过滤。
   - 不返回 `thoughts`、`inputs`、`outputs`、`latest_output`、prompt、密钥。

### 边界

- 不把 hidden chain-of-thought 转成 trace_summary。
- 不强制普通聊天助手返回这些字段。
- 不把节点完整输入输出放进公共接口。

### 达标标准

- 所有外部 Agent API 都返回同一 envelope。
- 成功响应有 `latency_ms`。
- 失败响应有 `error_code` 和 `error.message`。
- hidden thought 不出现在 `answer/references/trace_summary/error`。

### 测试方法

- 单测：JSON structured output 能提取字段。
- 单测：非 JSON output 降级为 answer。
- 单测：`<think>...</think>` 被清理。
- 单测：敏感字段不会出现在 trace_summary。
- 接口测试：成功、失败、超时三类返回结构一致。

## 7. V2-3：4 个真实 AI 老师配置

### 目标

创建 4 个可被 `voice-project` 调用的真实 AI 老师配置，每个老师有独立：

- `agent_id`
- `chat_id/session` 策略
- `workflow_id`
- 角色定位
- 人格摘要
- 语言风格
- 知识库范围
- 输出 schema

### 为什么要做

当前代码有 multi-agent fan-out 基础，但没有 4 个真实 AI 老师实例。没有实例就无法做真实联调。

### 不做会怎样

- 只能跑模拟测试，无法证明系统上线后 4 个老师能并行工作。
- `voice-project` 无法注册固定老师。
- 老师私有库、人格和风格无法验证隔离。

### 怎么做

1. 定义 4 个老师角色。
   - 示例：
     - `lead_teacher`：主持与总结。
     - `phonetics_teacher`：发音和听说训练。
     - `grammar_teacher`：结构和表达纠错。
     - `learning_coach`：鼓励、反馈和学习策略。
2. 建立配置表或配置文件。
   - 固定 `agent_id/workflow_id/default_dataset_scope/persona/style`。
3. 为每个老师创建最小 workflow。
   - Begin/context。
   - Retrieval 可选。
   - LLM。
   - OutputFormatter。
4. 配置默认输出 schema。
   - `answer/intention/target/confidence/knowledge_used/suggested_next_action`。
5. 增加 smoke 测试。
   - 每个老师同一问题输出不同风格。
   - 每个老师返回自己的 `agent_id/workflow_id/session_id`。

### 边界

- 不在 RAGFlow 绑定 TTS 音色。
- 不在 RAGFlow 决定谁最终发言。
- 不把 4 个老师写成硬编码业务分支，应该使用配置和 workflow。

### 达标标准

- 4 个老师均可通过外部 API 调用。
- 4 个老师 session 不串。
- 4 个老师 trace 不串。
- 4 个老师无法默认读取彼此私有库。
- 输出字段满足标准 envelope。

### 测试方法

- 单测：配置完整性校验。
- 接口 smoke：分别调用 4 个老师。
- 并发 smoke：同一会议 fan-out 4 个老师。
- 权限测试：老师 A 请求老师 B 私有库被拒绝。

## 8. V2-4：AITeacherTurnContext 完整接入

### 目标

完整支持外部注入上下文：

```json
{
  "meeting_topic": "",
  "meeting_goal": "",
  "student_last_utterance": "",
  "other_teachers_last_round": [],
  "round_index": 1,
  "god_instruction": "",
  "current_task": "",
  "teacher_personality_summary": "",
  "language_style_constraints": "",
  "dataset_scope": [],
  "forbidden_content": [],
  "output_schema": {},
  "reply_to": "",
  "target_listener": ""
}
```

### 为什么要做

AI 老师每次发言必须基于当前会议状态，而不是自由聊天。上下文注入是“可被上帝调度”的核心。

### 不做会怎样

- 老师无法知道当前轮次、学生上一句话、其他老师观点和上帝调度要求。
- 同一个问题在不同会议状态下输出不可控。
- 无法做发言对象、禁说内容和输出格式约束。

### 怎么做

1. 增加 `AITeacherTurnContext` schema。
   - 放到后端公共 schema 或 agent schema。
2. API 规范化。
   - `context`、`external_context`、顶层字段统一归并成 `AITeacherTurnContext`。
3. 注入 Canvas globals / Begin inputs。
   - 保证 workflow 节点可引用。
4. 生成 hash。
   - `context_hash`：上下文摘要 hash。
   - `constraint_hash`：语言风格、禁用内容、输出 schema hash。
5. 回应对象校验。
   - `reply_to` 指向不存在老师时返回 `INVALID_TARGET` 或降级为 `all` 并记录 trace。
6. forbidden 内容检查。
   - 质量检查节点或 OutputFormatter 识别命中内容。

### 边界

- RAGFlow 不生成学生长期画像，只消费摘要。
- 不把完整上下文原文返回给外部。
- 不把上下文全部塞进 chat history 作为唯一记忆。

### 达标标准

- workflow 能读取所有标准 context 字段。
- trace_summary 返回 hash 和字段使用状态，不返回隐私原文。
- `god_instruction/current_task` 能影响输出。
- `reply_to/target_listener` 能影响语气和目标。
- `forbidden_content` 命中时能失败或重写。

### 测试方法

- 单测：顶层字段和 `external_context` 可规范化为同一 schema。
- 单测：缺少可选字段仍可执行。
- 单测：非法 `reply_to` 被识别。
- 单测：`forbidden_content` 触发质量检查。
- 集成测试：同一老师在不同 `god_instruction` 下输出不同 intention。

## 9. V2-5：runtime timeout/cancel/deadline

### 目标

让每个 agent run 支持独立：

- `deadline_ms`
- timeout
- cancel
- failed
- partial fan-in

### 为什么要做

4 个老师并发时，一个老师慢或失败不能阻塞整轮课堂。

### 不做会怎样

- 单个模型卡住会拖住整轮会议。
- 外部系统无法取消过期 run。
- fan-in 无法区分超时、失败、取消。

### 怎么做

1. run payload 增加 `deadline_ms`。
2. executor 执行时检查 deadline。
3. 超时返回：
   - `AGENT_TIMEOUT` 或 `WORKFLOW_TIMEOUT`。
4. cancel 接口落地。
   - 已有 route 的情况下，补执行中取消状态检查。
5. fan-in 允许部分失败。
   - 汇总每个 run 的 `status/error_code/latency_ms`。
6. trace_summary 记录超时节点和耗时。

### 边界

- 不强杀底层模型进程。
- 不让 LLM 长推理持有写锁。
- 取消一个 run 不影响同会议其他 run。

### 达标标准

- 单个 run 超时后状态为 `timeout` 或 `failed` 且 error_code 正确。
- cancel 后状态为 `canceled`。
- 4 个老师中 1 个超时，其他 3 个可正常返回。
- fan-in 结果包含每个老师的状态。

### 测试方法

- 单测：deadline 已过直接超时。
- 单测：运行中 cancel 状态可查询。
- 并发测试：4 run 并发，其中一个模拟慢任务。
- 回归：平台回归脚本通过。

## 10. V2-6：知识库权限与标准库 metadata

### 目标

补齐老师私有库、课程共有库、教材库、教案库、学生记录库和标准核对库的权限与 metadata 过滤。

### 为什么要做

多老师和文档核对都依赖知识库边界。特别是法规/制度核对，如果没有版本、生效时间、条号，报告无法证明依据可靠。

### 不做会怎样

- 老师可能越权读到别的老师私有库。
- 文档核对可能引用未授权或过期标准。
- references 无法支持审计。

### 怎么做

1. 定义 dataset role。
   - `teacher_private`
   - `course_shared`
   - `textbook`
   - `lesson_plan`
   - `student_record`
   - `compliance_standard`
2. 检索前权限 guard。
   - agent scope 与 request scope 取交集。
   - 交集为空不回退全库。
3. 标准库 metadata。
   - `standard_type`
   - `jurisdiction`
   - `industry`
   - `effective_from`
   - `effective_to`
   - `version`
   - `article_no`
   - `topic`
4. Retrieval 支持 metadata filters。
5. references 补齐字段。
   - `dataset_id`
   - `document_id`
   - `chunk_id`
   - `page`
   - `version`
   - `effective_from/effective_to`
   - `article_no`
   - `metadata_incomplete`

### 边界

- RAGFlow 不判断法律是否真实现行有效，只按知识库 metadata 过滤和提示。
- metadata 缺失不能包装成“最新有效标准”。
- 不允许请求绕过 workflow 授权扫全库。

### 达标标准

- A 老师无法读取 B 老师私有库。
- 所有授权老师可读取课程共有库。
- 核对模板只能检索绑定标准库。
- metadata 缺失时报告提示“标准版本信息不足”。

### 测试方法

- 单测：scope 交集为空不检索。
- 单测：无权限 dataset 返回 `DATASET_SCOPE_DENIED`。
- 单测：metadata filter 生效。
- 集成测试：核对模板不能引用未绑定知识库。

## 11. V2-7：AI 老师 workflow 模板

### 目标

提供可复制的三类模板：

- 课前会议模板。
- 课堂教学模板。
- 课后复盘模板。

### 为什么要做

没有标准模板，管理员很难通过低代码方式稳定创建 AI 老师。每次手工搭节点容易格式漂移。

### 不做会怎样

- 4 个老师只能靠手工配置，复现困难。
- 输出结构不稳定。
- 无法形成可发布、可回归的标准工作流。

### 怎么做

1. 课前模板。
   - 输入课程目标、学生画像摘要、教师角色。
   - 输出教学目标、内容安排、分工建议。
2. 课堂模板。
   - 输入 `AITeacherTurnContext`。
   - 检索私有库和课程库。
   - 生成话术。
   - 质量检查。
   - 输出结构化结果。
3. 课后模板。
   - 输入课堂记录、学生表现、评分。
   - 输出复盘报告和下次建议。
4. 每个模板带发布校验。
5. 每个模板带 fixture 测试。

### 边界

- 不硬编码具体学生隐私数据。
- 不决定最终谁发言。
- 不绑定具体 TTS 音色。

### 达标标准

- 三类模板都可导入、发布、运行。
- 输出满足标准 envelope。
- 模板可复制给 4 个不同老师并修改 persona。

### 测试方法

- 单测：模板 JSON schema 合法。
- 单测：模板必要节点存在。
- 集成测试：三个模板使用 fixture 跑通。
- 前端 smoke：模板可在画布打开并发布。

## 12. V2-8：文档核对模板端到端

### 目标

把现有合规节点串成完整“核对智能体”模板：

```text
Begin/UserFillUp
  -> FileParser
  -> ContractClauseExtractor
  -> Retrieval
  -> ComplianceChecklistGenerator
  -> ClauseMatcher
  -> ComplianceVerifier
  -> RiskScorer
  -> CitationFormatter
  -> ComplianceReportComposer
  -> DocGenerator
  -> Message
```

### 为什么要做

现在已经有核对节点，但用户需要的是能上传文档、指定知识库、生成报告和下载结果的完整智能体。

### 不做会怎样

- 节点只能单测证明可用，不能作为业务智能体交付。
- 法律/合同核对仍可能出现“没有下载链接”“报告截断”“引用不完整”等问题。

### 怎么做

1. 完善 `compliance_verification_agent.json`。
2. 确保 FileParser 输出同时包含：
   - 解析文本。
   - chunk refs。
   - 原始文件信息。
3. Retrieval 只检索绑定知识库。
4. ComplianceChecklistGenerator 不允许无依据生成强制核对项。
5. ComplianceVerifier 每个结论必须引用：
   - 标准依据。
   - 合同条款。
6. DocGenerator 生成 markdown/docx。
7. Message 返回摘要、风险数量、下载链接和人工复核提示。

### 边界

- 不接外部法律数据库。
- 不使用第三方法务系统。
- 不输出正式法律意见。
- 不直接修改合同原文。

### 达标标准

- 上传合同 fixture 后生成：
  - `verification_results`
  - `risk_summary`
  - markdown/docx 下载产物
  - references
  - trace_summary
- 依据缺失时输出 `ambiguous/needs_human_review`，不强行合规。
- prompt injection 样例不能覆盖知识库标准。

### 测试方法

- 单测：每个核对节点已覆盖。
- 集成测试：合同 fixture + 标准库 fixture 端到端生成报告。
- 负例测试：标准无命中时输出证据不足。
- 安全测试：上传文档要求“忽略知识库”时仍以绑定知识库为准。

## 13. V2-9：前端画布与调试 smoke

### 目标

管理员可以在前端完成：

- 创建 workflow。
- 添加节点。
- 配置表单。
- 连接节点。
- 发布前校验。
- 调试输入 `AITeacherTurnContext`。
- 查看 answer、references、trace_summary、error_code。

### 为什么要做

后端节点可用不代表低代码平台可用。用户最终需要通过界面搭建和调试智能体。

### 不做会怎样

- 只能靠开发人员改 JSON。
- 节点即使存在，用户也无法配置。
- 发布前错误不能提前发现。

### 怎么做

1. 补齐所有新增节点的前端入口。
2. 补齐节点表单。
3. 补齐连线类型校验。
4. 调试面板支持标准 context 输入。
5. trace 面板只展示安全摘要。
6. Playwright smoke 覆盖真实流程。

### 边界

- 不显示 hidden chain-of-thought。
- 不显示完整节点输入输出给普通管理员。
- 不实现数字人教室 UI。

### 达标标准

- 前端 build 通过。
- Jest 连线类型测试通过。
- Playwright smoke 可创建并发布 workflow。
- trace 面板不出现 hidden thought。

### 测试方法

- `npm test -- --runInBand src/pages/agent/utils/connection-schema.test.ts`
- `npm run build`
- Playwright：
  - 登录。
  - 创建 agent。
  - 添加核心节点。
  - 连线。
  - 发布。
  - 调试运行。

## 14. V2-10：安全、审计、prompt injection

### 目标

确保外部调用、知识库检索、artifact 下载、patch proposal、共享写入都有权限和审计。

### 为什么要做

多智能体系统中越权、泄密、prompt injection 和共享写入覆盖是最危险的生产风险。

### 不做会怎样

- A 老师可能读 B 老师私有材料。
- 用户上传文档可能诱导模型忽略标准。
- 外部系统可能下载不属于自己的 artifact。
- patch proposal 可能被未授权 agent 提交或应用。

### 怎么做

1. API 鉴权。
   - 登录态。
   - API token。
   - agent/workflow 权限。
2. Dataset 权限。
   - 检索前检查。
   - 空交集不回退。
3. Artifact 权限。
   - 下载前检查 run/session/tenant。
4. Patch proposal 权限。
   - submit 和 apply 都检查 agent 权限。
5. Prompt injection 防护。
   - 用户输入和上传文档不能覆盖系统约束。
   - 检索内容不能要求泄露 prompt。
6. 审计日志。
   - run。
   - retrieval。
   - artifact download。
   - patch proposal。
   - write。
   - rollback。
   - permission denied。

### 边界

- 安全过滤不能替代权限系统。
- 不为了测试方便添加后门。
- 不把 prompt 存进可下载报告。

### 达标标准

- 无权限 agent 调用被拒绝。
- 无权限 dataset 检索被拒绝。
- 无权限 artifact 下载被拒绝。
- 无权限 patch proposal 或共享写入被拒绝。
- prompt injection 不能泄露系统 prompt。
- 成功和拒绝都有审计记录。

### 测试方法

- 单测：权限拒绝。
- 单测：prompt injection 样例。
- 单测：trace 过滤敏感字段。
- 单测：artifact 越权下载。
- 单测：patch proposal 越权。
- 审计测试：检查成功和失败记录。

## 15. V2-11：voice-project 联调验收

### 目标

证明 RAGFlow 可以支撑真实外部会议系统。

### 为什么要做

内部单测和模拟集成不能证明跨系统可用。最终必须由 `voice-project` 调用 RAGFlow。

### 不做会怎样

- API 字段可能和外部系统理解不一致。
- 并发、超时、错误码和上下文注入可能只在本地模拟里成立。
- 上线后才发现 session 串线、知识库越权或下载不可用。

### 怎么做

1. 单老师闭环。
   - `voice-project` 传 `AITeacherTurnContext`。
   - RAGFlow 返回 answer/references/trace_summary。
2. 4 老师并发。
   - 同一 `meeting_id/turn_id` fan-out。
   - 每个老师独立 `run_id/session_id/context/trace`。
3. 知识库只检索。
   - 外部传 dataset scope。
   - 返回 references 和版本。
4. 错误降级。
   - 模拟一个老师 timeout。
   - 模拟一个 workflow failed。
   - 模拟 dataset denied。
5. 共享文档写入。
   - 4 老师读取同一 snapshot。
   - 输出 patch proposal。
   - GodCoordinator 选择 proposal。
   - RAGFlow 单写者写入新版本。
   - 支持 rollback。

### 边界

- RAGFlow 不负责选择哪个老师发言。
- RAGFlow 不负责 TTS/ASR/播放。
- RAGFlow 不决定采用哪个 patch proposal，只负责校验、写入、版本化和审计。

### 达标标准

- 单老师端到端通过。
- 4 老师并发端到端通过。
- 一个老师失败不影响其他老师返回。
- 知识库 scope 生效。
- patch proposal 到新版本写入闭环通过。
- 外部系统能按 error_code 做降级。

### 测试方法

- 联调脚本：
  - `voice-project` 调 RAGFlow 单老师。
  - `voice-project` 调 RAGFlow 4 老师。
  - `voice-project` 调只检索接口。
  - `voice-project` 调共享写入接口。
- 压测：
  - 多会议并发。
  - 每会议 4 老师。
  - 模拟慢老师和失败老师。
- 验收记录：
  - 保存请求样例。
  - 保存响应样例。
  - 保存错误样例。
  - 保存审计记录截图或 JSON。

## 16. 最小执行顺序

建议按以下顺序执行，不能跳过 P0：

1. V2-1：workflow_id 真实绑定。
2. V2-2：标准外部响应补齐。
3. V2-3：4 个 AI 老师配置。
4. V2-4：AITeacherTurnContext 完整接入。
5. V2-10：安全、审计、prompt injection 基线。
6. V2-5：runtime timeout/cancel/deadline。
7. V2-6：知识库权限与标准库 metadata。
8. V2-7：AI 老师 workflow 模板。
9. V2-8：文档核对模板端到端。
10. V2-9：前端画布与调试 smoke。
11. V2-11：voice-project 联调验收。

原因：

- `workflow_id` 绑定和标准响应是所有外部调用的前置。
- 4 个老师配置和 context 注入是多智能体能力的核心。
- 安全基线必须尽早加，不能等所有功能完成后再补。
- runtime、知识库、模板、前端、联调按依赖自然推进。

## 17. 每阶段完成定义

每个阶段完成时必须同时满足：

- 代码改动已完成。
- 单元测试已补充。
- 相关接口或模板有最小集成测试。
- `tools/run_agent_platform_regression.sh` 通过。
- 如果改前端，`npm test` 对应测试通过，必要时 `npm run build` 通过。
- 如果涉及权限，必须有越权拒绝测试。
- 如果涉及 trace，必须证明不暴露 hidden chain-of-thought。
- 如果涉及共享写入，必须证明走 patch proposal + expected version + audit。

## 18. 风险优先级

| 风险 | 优先级 | 处理方式 |
| --- | --- | --- |
| workflow_id 不能独立绑定 | 高 | V2-1 优先完成 |
| 4 个老师没有真实配置 | 高 | V2-3 建立固定配置 |
| 上下文注入不完整 | 高 | V2-4 schema 化 |
| 私有知识库越权 | 高 | V2-6/V2-10 权限 guard |
| trace 泄露 prompt 或 hidden thought | 高 | V2-2/V2-10 白名单过滤 |
| 单老师 timeout 阻塞整轮 | 高 | V2-5 独立 deadline |
| 合同核对引用不可靠 | 中 | V2-6/V2-8 metadata + references |
| 前端节点可配置性不足 | 中 | V2-9 Playwright smoke |
| 只在本地模拟可用 | 高 | V2-11 真实联调 |

## 19. v2 完成后的验收清单

全部完成后，应能回答“是”：

- 外部系统能传 `agent_id + workflow_id` 调用指定工作流吗？
- 外部系统能传入和拿回 `session_id` 吗？
- 每次调用能注入 `AITeacherTurnContext` 吗？
- 4 个 AI 老师能并发运行且互不串线吗？
- 每个老师能绑定私有知识库和课程共有知识库吗？
- 无权限知识库会被拒绝而不是回退全库吗？
- 返回结果包含 `answer + intention + target + confidence + references + trace_summary` 吗？
- trace_summary 不暴露 hidden chain-of-thought 吗？
- 一个老师超时不会阻塞其他老师吗？
- 合同核对能生成逐条核对表、风险汇总和下载报告吗？
- 共享文档写入是否只能通过 patch proposal 和单写者队列？
- 前端是否能创建、配置、发布、调试这些 workflow？
- `voice-project` 是否完成单老师、4 老师、只检索、写入协调联调？

