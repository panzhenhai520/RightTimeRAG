# Agent 新增对外接口层的开发步骤

## 全局边界

- 不改聊天助手现有回答正文格式。
- 不改聊天助手的 retrieving / thinking / answer 输出样式。
- 不改普通问答的流式输出节奏。
- 不把智能体 run 事件混到聊天助手会话事件里。
- 不复用前端同一个临时状态对象，避免历史会话污染。
- 对外接口只返回白名单字段，不暴露隐藏思维链、节点原始输入、节点原始输出、密钥、Token、Cookie、数据库连接参数等内部调试信息。

## 阶段 0：接口盘点与边界锁定

目标：明确当前 Agent 能力、内部接口和对外接口的分界。

具体工作：
- 盘点现有 `/agents/chat/completions`、`/agents/<agent_id>/runs`、`/agents/runs/<run_id>/trace`、`/agents/runs/<run_id>/artifacts`。
- 确认现有 `AgentRunService.summarize_events` 是内部调试 trace，不直接作为对外标准结果。
- 确认当前输出文件能力：docx、pdf、txt、markdown、html、xlsx、csv、svg、zip、wav 等由节点和 artifact service 生成。

达成标准：
- 新接口设计不替换现有聊天助手接口。
- 内部 trace 与外部 trace_summary 明确分离。

边界：
- 不在本阶段改检索、模型调用、节点执行逻辑。
- 不重构 Agent 编排运行器。

测试方法：
- 代码阅读确认路由和服务边界。
- 后续阶段用单元测试固定对外返回结构。

## 阶段 1：标准响应模型与安全过滤

目标：新增统一的对外响应适配层。

具体工作：
- 新增 `AgentPublicResponseService`。
- 统一输出结构：
  - `agent_id`
  - `workflow_id`
  - `run_id`
  - `session_id`
  - `message_id`
  - `status`
  - `answer`
  - `references`
  - `downloads`
  - `trace_summary`
  - `error`
- 对 answer 去除 `<think>...</think>` 等隐藏思维链片段。
- 对 references 做字段白名单。
- 对 trace_summary 做字段白名单，只保留运行状态、节点状态、进度、错误摘要、下载摘要。
- 对 downloads 做去重和字段白名单。

达成标准：
- 任意内部 trace 输入都不会把 `thoughts`、`inputs`、`outputs`、`latest_output` 暴露给外部调用方。
- 错误返回使用结构化 `error.code`、`error.message`、`error.retryable`。

边界：
- 不删除内部 trace 字段，调试接口仍可使用。
- 不修改节点事件原始记录。

测试方法：
- 单测：输入包含 `<think>` 的回答，输出必须只保留正文。
- 单测：输入包含节点 `inputs/outputs/thoughts/latest_output` 的 trace，输出不得包含这些字段。
- 单测：输入重复 downloads，输出按文件 id 去重。

## 阶段 2：外部上下文与请求级知识库范围注入

目标：支持外部系统调用 Agent 时传入上下文和本轮知识库范围。

具体工作：
- 在 `Canvas.globals` 中新增：
  - `sys.external_context`
  - `sys.request_dataset_ids`
- 在 Agent 执行入口接收：
  - `external_context`
  - `dataset_ids` / `request_dataset_ids`
- 将这些字段透传到 `Canvas.run`。
- 第一阶段只做注入和变量可用，不强行改写已有 Retrieval 节点配置。

达成标准：
- 编排节点可以通过系统变量读取外部上下文。
- 请求中的知识库范围能进入运行上下文，供后续检索约束使用。

边界：
- 不破坏已有 Retrieval 节点 `dataset_ids/kb_ids` 配置。
- 不改变普通聊天助手的检索策略。

测试方法：
- 单测或编译检查：`Canvas.run(external_context=..., request_dataset_ids=...)` 不报错并写入 globals。
- 后续接口测试验证请求字段能被接收。

## 阶段 3：新增同步对外调用接口

目标：提供稳定的外部系统调用入口。

具体工作：
- 新增 `POST /agents/<agent_id>/invoke`。
- 支持请求字段：
  - `query` / `question`
  - `session_id`
  - `user_id`
  - `inputs`
  - `files`
  - `external_context`
  - `dataset_ids`
  - `workflow_id`
  - `return_trace`
- 调用现有 Agent 运行器，结束后用 `AgentPublicResponseService` 包装结果。

达成标准：
- 返回结构稳定为标准 envelope。
- 运行失败时返回 `status=failed` 和结构化错误。
- `workflow_id` 缺省等于 `agent_id`；传入非当前 agent 的 workflow_id 时拒绝。

边界：
- 本接口默认同步返回。
- 不在本阶段引入新的 SSE 输出形式。
- 不影响 `/agents/chat/completions`。

测试方法：
- 单测服务包装。
- 编译检查路由。
- 条件允许时用真实 Agent 调用一次，确认返回 envelope。

## 阶段 4：新增异步结果查询接口

目标：支持长任务外部系统轮询最终结果。

具体工作：
- 新增 `GET /agents/runs/<run_id>/result`。
- 根据 run state 校验权限。
- 从会话消息中读取最终 assistant answer。
- 合并 run trace，输出标准 envelope。

达成标准：
- 未完成任务返回 `status=running/queued`，answer 可为空。
- 完成任务返回 answer、references、downloads、trace_summary。
- 失败任务返回结构化 error。

边界：
- 保留现有 `/events`、`/trace`、`/artifacts` 内部调试接口。
- 不把内部 event stream 改造成公共 stream。

测试方法：
- 单测公共包装服务。
- 手动或集成测试：创建 background run 后轮询 result。

## 阶段 5：权限与会话归属补强

目标：保证外部接口不会跨 Agent 读取或删除 session。

具体工作：
- `GET /agents/<agent_id>/sessions/<session_id>` 校验 `conv.dialog_id == agent_id`。
- `DELETE /agents/<agent_id>/sessions/<session_id>` 校验 `conv.dialog_id == agent_id`。
- `POST /agents/<agent_id>/runs` 传入已有 session 时校验 session 归属。

达成标准：
- 有权限访问 Agent 也不能读取不属于该 Agent 的 session。
- 对外调用结果只允许当前登录用户可访问的 Agent run。

边界：
- 不改变会话列表查询排序和分页。
- 不改变已有 session 数据结构。

测试方法：
- 编译检查。
- 单元或接口测试：session 不属于 agent 时返回错误。

## 阶段 6：请求级知识库硬约束

目标：把请求级 `dataset_ids` 从运行上下文进一步接入 Retrieval。

具体工作：
- 在 Retrieval 执行时读取 `sys.request_dataset_ids`。
- 策略采用交集优先：
  - 节点配置为空，请求范围作为本轮可检索范围。
  - 节点配置不为空且请求范围不为空，只检索二者交集。
  - 交集为空时返回空证据，不回退到全库检索。
- 校验 dataset 必须属于当前租户或当前用户可访问范围。

达成标准：
- 外部调用可限定知识库范围。
- 不满足范围约束时不会返回范围外证据。

边界：
- 不改普通聊天助手默认检索。
- 不改变知识库索引结构。

测试方法：
- 单测：节点配置 A/B，请求 B/C，最终只检索 B。
- 单测：交集为空时返回空证据。
- 接口测试：传入 dataset_ids 后 references 只来自指定范围。

## 阶段 7：集成测试与回归

目标：证明新增对外层可用于真实外部服务对接，同时不破坏现有聊天助手。

具体工作：
- 新增或补充测试脚本：
  - 公共响应过滤单测。
  - Agent run trace 回归测试。
  - Agent 组件契约测试。
  - 有条件时执行真实 Agent invoke 测试。
- 检查现有聊天助手入口未变更输出格式。

达成标准：
- 新增单测通过。
- 现有 Agent 组件和 trace 测试通过。
- 普通聊天助手接口代码路径未混入公共 envelope。

边界：
- 真实模型、OCR、ASR、TTS、外部搜索等依赖服务不可用时，测试只验证本地可验证边界。
- 不因为外部服务缺失而改核心接口设计。

测试方法：
- `python -m pytest -q test/unit_test/test_agent_public_response_service.py`
- `python -m pytest -q test/unit_test/test_agent_run_trace_summary.py`
- `python -m pytest -q test/unit_test/test_agent_component_contract.py`
- `python -m py_compile api/apps/restful_apis/agent_api.py api/db/services/agent_public_response_service.py agent/canvas.py`
