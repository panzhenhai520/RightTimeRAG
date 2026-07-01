import { Operator } from '@/constants/agent';

export type NodeGuideCategoryId =
  | 'foundation'
  | 'inputOutput'
  | 'flow'
  | 'task'
  | 'document'
  | 'data'
  | 'compliance'
  | 'voice'
  | 'external'
  | 'database'
  | 'review';

export type NodeGuideDefinition = {
  title: string;
  description: string;
  category: NodeGuideCategoryId;
  external?: boolean;
};

export const NodeGuideCategories: Array<{
  id: NodeGuideCategoryId;
  title: string;
  description: string;
}> = [
  {
    id: 'foundation',
    title: '基础能力',
    description: '大模型回答、知识库检索、问题改写等常用智能体能力。',
  },
  {
    id: 'inputOutput',
    title: '输入输出',
    description: '接收用户输入、补充参数、展示回答或生成可见结果。',
  },
  {
    id: 'flow',
    title: '流程控制',
    description: '分支、循环、分类、等待等控制流程走向的节点。',
  },
  {
    id: 'task',
    title: '任务规划',
    description: '识别目标、拆解任务、检查前置条件、验证结果和重新规划。',
  },
  {
    id: 'document',
    title: '文件文档',
    description: '读取、解析、生成、写回文件和工作区内容。',
  },
  {
    id: 'data',
    title: '数据处理',
    description: '变量、列表、字符串、数字、图表和产物整理。',
  },
  {
    id: 'compliance',
    title: '合规比对',
    description: '合同条款、合规清单、风险评分和冲突判断。',
  },
  {
    id: 'voice',
    title: '语音多媒体',
    description: '音频输入、语音识别、语音合成和语音回复。',
  },
  {
    id: 'external',
    title: '外部工具',
    description: '联网搜索、网页、邮件、HTTP、代码仓库和金融数据等外部服务。',
  },
  {
    id: 'database',
    title: '数据库',
    description: '受控数据库连接、建表、插入、更新和查询。',
  },
  {
    id: 'review',
    title: '人工审核',
    description: '人工确认、审批和高风险操作拦截。',
  },
];

export const NodeGuideMap: Record<string, NodeGuideDefinition> = {
  [Operator.Begin]: {
    title: '开始',
    description: '定义智能体的入口、对话开场白和需要用户填写的参数。',
    category: 'inputOutput',
  },
  [Operator.Agent]: {
    title: '智能体',
    description: '调用大模型进行多轮思考，可配置工具、提示词和结构化输出。',
    category: 'foundation',
  },
  LLM: {
    title: '大模型',
    description: '调用语言模型理解、分析、生成文本或结构化结果。',
    category: 'foundation',
    external: true,
  },
  [Operator.Retrieval]: {
    title: '知识库检索',
    description: '从知识库或记忆中召回相关内容，作为后续回答依据。',
    category: 'foundation',
  },
  [Operator.Categorize]: {
    title: '问题分类',
    description: '用大模型判断输入属于哪个类别，并按类别进入不同分支。',
    category: 'flow',
    external: true,
  },
  [Operator.RewriteQuestion]: {
    title: '问题改写',
    description: '结合上下文把用户问题改写成更适合检索或执行的表达。',
    category: 'foundation',
    external: true,
  },
  [Operator.Message]: {
    title: '消息输出',
    description: '把指定内容输出到聊天窗口，是最常用的可见结果节点。',
    category: 'inputOutput',
  },
  [Operator.UserFillUp]: {
    title: '用户补充',
    description: '运行中暂停流程，请用户补充缺失信息后继续执行。',
    category: 'inputOutput',
  },
  [Operator.WaitingDialogue]: {
    title: '等待对话',
    description: '等待用户继续输入，再把新输入交给后续节点处理。',
    category: 'inputOutput',
  },
  [Operator.Switch]: {
    title: '条件分支',
    description: '按条件判断走向不同分支，适合规则明确的流程控制。',
    category: 'flow',
  },
  [Operator.Iteration]: {
    title: '迭代',
    description: '对列表中的每个元素重复执行一段子流程。',
    category: 'flow',
  },
  [Operator.Loop]: {
    title: '循环',
    description: '按终止条件重复执行子流程，适合持续修正或多轮处理。',
    category: 'flow',
  },
  [Operator.ExitLoop]: {
    title: '退出循环',
    description: '在循环内部满足条件时提前结束循环。',
    category: 'flow',
  },
  GoalIntentClassifier: {
    title: '意图识别',
    description: '判断用户要找文件、改文档、比对文档、生成报告还是执行代码任务。',
    category: 'task',
    external: true,
  },
  GoalNormalizer: {
    title: '目标规范化',
    description: '把用户自然语言目标整理成清晰、可执行、可追踪的任务目标。',
    category: 'task',
  },
  TaskContextCollector: {
    title: '上下文收集',
    description: '收集任务相关的路径、文件、历史输出和运行上下文。',
    category: 'task',
  },
  RecentArtifactFinder: {
    title: '最近产物查找',
    description: '按时间和名称查找最近生成或修改过的文档、报告和文件。',
    category: 'task',
  },
  RelevantFileResolver: {
    title: '相关文件解析',
    description: '按路径、文件名、时间和相似度定位任务相关文件。',
    category: 'task',
  },
  TaskPlanner: {
    title: '任务规划',
    description: '把用户目标拆成有依赖关系的阶段和子任务。',
    category: 'task',
    external: true,
  },
  TaskDecomposer: {
    title: '任务拆解',
    description: '继续把复杂任务拆到更小、更容易执行的原子步骤。',
    category: 'task',
  },
  AtomicTaskRefiner: {
    title: '原子任务细化',
    description: '检查每个子任务是否足够简单，并补充输入、输出和完成条件。',
    category: 'task',
  },
  PreconditionChecker: {
    title: '前置条件检查',
    description: '检查路径、文件、模型、权限、依赖节点等是否已满足。',
    category: 'task',
  },
  DependencyResolver: {
    title: '依赖解析',
    description: '整理子任务之间的先后顺序和依赖关系。',
    category: 'task',
  },
  TaskExecutor: {
    title: '任务执行',
    description: '按计划执行当前子任务，并记录执行结果。',
    category: 'task',
  },
  TaskFrameController: {
    title: '任务框架控制',
    description: '维护 pending、running、done、blocked 等任务状态。',
    category: 'task',
  },
  TaskResultVerifier: {
    title: '结果核对',
    description: '核对当前结果是否满足任务目标和验收条件。',
    category: 'task',
  },
  TaskReflection: {
    title: '任务反思',
    description: '分析执行结果的问题，决定是否需要补充信息或调整方案。',
    category: 'task',
  },
  ReplanDecider: {
    title: '重规划判断',
    description: '判断是否回到上一级任务、继续下一步或重新规划。',
    category: 'task',
  },
  TaskExecutionReportComposer: {
    title: '执行报告生成',
    description: '汇总任务计划、执行过程、结果和未完成事项。',
    category: 'task',
  },
  [Operator.FileParser]: {
    title: '文件解析',
    description: '解析上传文件内容，输出文本片段、匹配结果和文件信息。',
    category: 'document',
  },
  WorkspaceFileList: {
    title: '列出工作区文件',
    description: '列出智能体工作区内的文件和目录。',
    category: 'document',
  },
  WorkspaceFileSearch: {
    title: '搜索工作区文件',
    description: '按文件名、类型或内容在智能体工作区中搜索文件。',
    category: 'document',
  },
  WorkspaceFileRead: {
    title: '读取工作区文件',
    description: '读取指定路径的文件内容，支持按范围读取。',
    category: 'document',
  },
  [Operator.WorkspaceFileWrite]: {
    title: '写入工作区文件',
    description: '在智能体授权工作区内创建、覆盖或追加写入文件。',
    category: 'document',
  },
  [Operator.WorkspacePatchApply]: {
    title: '应用文件补丁',
    description: '对工作区文件执行 dry-run 或应用 patch，并记录审计结果。',
    category: 'document',
  },
  WorkspaceTableRead: {
    title: '读取表格',
    description: '把 CSV、Excel 等表格文件读取成结构化数据。',
    category: 'document',
  },
  DocumentNormalizer: {
    title: '文档规范化',
    description: '把不同格式文档整理成统一结构，方便后续抽取和比对。',
    category: 'document',
  },
  DocumentStructureAdvisor: {
    title: '文档结构分析',
    description: '识别标题、章节、段落、表格、条款和层级关系。',
    category: 'document',
  },
  ContentPlacementPlanner: {
    title: '内容放置规划',
    description: '判断新增内容应该放入目标、背景、任务、测试、风险等哪一层级。',
    category: 'document',
  },
  [Operator.DocGenerator]: {
    title: '文档生成',
    description: '根据模板或内容生成可下载的文档文件。',
    category: 'document',
  },
  [Operator.ExcelProcessor]: {
    title: 'Excel 处理',
    description: '读取、合并、计算或生成 Excel 表格数据。',
    category: 'document',
  },
  [Operator.DataOperations]: {
    title: '数据操作',
    description: '对对象或结构化数据做选择、过滤、映射等操作。',
    category: 'data',
  },
  [Operator.ListOperations]: {
    title: '列表操作',
    description: '对列表进行筛选、合并、去重、排序等处理。',
    category: 'data',
  },
  [Operator.VariableAssigner]: {
    title: '变量赋值',
    description: '把上游结果保存到指定变量，供后续节点使用。',
    category: 'data',
  },
  [Operator.VariableAggregator]: {
    title: '变量聚合',
    description: '把多个分支或多个节点的结果合并成统一变量。',
    category: 'data',
  },
  [Operator.StringTransform]: {
    title: '文本转换',
    description: '对字符串进行截取、拼接、替换、格式化等处理。',
    category: 'data',
  },
  [Operator.PromptTemplate]: {
    title: '提示词模板',
    description: '把变量填入固定模板，生成更稳定的模型输入。',
    category: 'data',
  },
  [Operator.SummaryNode]: {
    title: '摘要',
    description: '对长文本、资料或结果进行摘要整理。',
    category: 'data',
    external: true,
  },
  [Operator.ReportComposer]: {
    title: '报告组织',
    description: '把分析结果组织成报告结构、章节和摘要。',
    category: 'data',
  },
  [Operator.NumberCalculate]: {
    title: '数值计算',
    description: '执行加权评分、系数计算等简单数值计算。',
    category: 'data',
  },
  [Operator.ChartSpecBuilder]: {
    title: '图表配置',
    description: '根据数据生成图表规格，供图表渲染节点使用。',
    category: 'data',
  },
  [Operator.ChartRenderer]: {
    title: '图表渲染',
    description: '把图表规格渲染成可展示的图表结果。',
    category: 'data',
  },
  [Operator.ArtifactPackager]: {
    title: '产物打包',
    description: '把多个文件、报告或附件整理成一个产物包。',
    category: 'data',
  },
  [Operator.Code]: {
    title: '代码执行',
    description: '执行受控脚本处理数据，适合规则明确的计算或转换。',
    category: 'data',
  },
  [Operator.ContractClauseExtractor]: {
    title: '合同条款抽取',
    description: '从合同中抽取条款、主体、义务、期限等信息。',
    category: 'compliance',
    external: true,
  },
  ClauseExtractor: {
    title: '条款抽取',
    description: '从法律、合同或制度文件中抽取条款片段。',
    category: 'compliance',
  },
  ObligationExtractor: {
    title: '义务抽取',
    description: '识别主体、责任、义务、期限和违约后果。',
    category: 'compliance',
  },
  DefinitionExtractor: {
    title: '定义抽取',
    description: '抽取术语定义、简称和解释性条款。',
    category: 'compliance',
  },
  ViewpointExtractor: {
    title: '观点抽取',
    description: '提取文档中的主张、观点和判断依据。',
    category: 'compliance',
  },
  RiskPointExtractor: {
    title: '风险点抽取',
    description: '识别可能存在的法律、履约、权限或合规风险。',
    category: 'compliance',
  },
  TableFactExtractor: {
    title: '表格事实抽取',
    description: '从表格中抽取事实项、金额、日期和关联主体。',
    category: 'compliance',
  },
  DocumentDiff: {
    title: '文档差异比对',
    description: '逐段或逐条对比两份文档的差异。',
    category: 'compliance',
  },
  TableDiff: {
    title: '表格差异比对',
    description: '对比两个表格的数据差异、缺失和变更。',
    category: 'compliance',
  },
  DocumentSemanticComparer: {
    title: '语义比对',
    description: '判断两段内容在含义上是否一致、包含、冲突或缺失。',
    category: 'compliance',
    external: true,
  },
  DocumentConflictDetector: {
    title: '冲突检测',
    description: '识别法律条款、合同条款或制度要求之间的冲突。',
    category: 'compliance',
    external: true,
  },
  [Operator.ComplianceChecklistGenerator]: {
    title: '合规清单生成',
    description: '把规则、条款或制度要求整理成可检查清单。',
    category: 'compliance',
  },
  [Operator.ClauseMatcher]: {
    title: '条款匹配',
    description: '把合同条款与法律条款、模板条款或清单项进行匹配。',
    category: 'compliance',
  },
  [Operator.ComplianceVerifier]: {
    title: '合规核验',
    description: '判断材料是否满足清单或条款要求。',
    category: 'compliance',
  },
  [Operator.RiskScorer]: {
    title: '风险评分',
    description: '根据风险项、证据和规则给出风险等级或分数。',
    category: 'compliance',
  },
  [Operator.ComplianceReportComposer]: {
    title: '合规报告',
    description: '把核验结果、风险点和建议整理成合规报告。',
    category: 'compliance',
  },
  DocumentCompareReportComposer: {
    title: '文档比对报告',
    description: '汇总差异、冲突、缺失和引用证据，生成比对报告。',
    category: 'compliance',
  },
  [Operator.AudioInput]: {
    title: '音频输入',
    description: '接收上游音频文件或音频变量，作为语音处理入口。',
    category: 'voice',
  },
  [Operator.ASRTranscribe]: {
    title: '语音转文字',
    description: '调用语音识别服务，把音频转换成文本。',
    category: 'voice',
    external: true,
  },
  [Operator.TTSGenerate]: {
    title: '文字转语音',
    description: '调用语音合成服务，把文本转换成音频。',
    category: 'voice',
    external: true,
  },
  [Operator.VoiceReplyOutput]: {
    title: '语音回复输出',
    description: '把文本和音频组织成语音回复结果。',
    category: 'voice',
  },
  [Operator.MeetingContextInput]: {
    title: '会议上下文',
    description: '加载会议轮次、共享记忆和智能体记忆。',
    category: 'voice',
  },
  [Operator.MemoryInject]: {
    title: '记忆写入',
    description: '把当前内容写入智能体或会议记忆。',
    category: 'voice',
  },
  [Operator.AgentFanout]: {
    title: '多智能体分发',
    description: '把任务分发给多个智能体并收集运行引用。',
    category: 'voice',
  },
  [Operator.ResultAggregator]: {
    title: '结果聚合',
    description: '汇总多个智能体或多个分支的结果。',
    category: 'voice',
  },
  [Operator.WebhookInput]: {
    title: 'Webhook 输入',
    description: '从外部系统通过 Webhook 触发流程。',
    category: 'external',
    external: true,
  },
  [Operator.ExternalScoreReceiver]: {
    title: '外部分数接收',
    description: '接收外部评分系统返回的结果。',
    category: 'external',
    external: true,
  },
  [Operator.Invoke]: {
    title: 'HTTP 请求',
    description: '调用外部 HTTP API，并把响应传给后续节点。',
    category: 'external',
    external: true,
  },
  [Operator.Email]: {
    title: '发送邮件',
    description: '通过邮件服务发送文本或附件。',
    category: 'external',
    external: true,
  },
  [Operator.Browser]: {
    title: '浏览器操作',
    description: '调用浏览器能力访问网页或提取页面信息。',
    category: 'external',
    external: true,
  },
  [Operator.TavilySearch]: {
    title: 'Tavily 搜索',
    description: '调用 Tavily 搜索网页资料。',
    category: 'external',
    external: true,
  },
  [Operator.TavilyExtract]: {
    title: 'Tavily 提取',
    description: '调用 Tavily 从网页中提取正文内容。',
    category: 'external',
    external: true,
  },
  [Operator.DuckDuckGo]: {
    title: 'DuckDuckGo 搜索',
    description: '通过 DuckDuckGo 搜索公开网页。',
    category: 'external',
    external: true,
  },
  [Operator.Google]: {
    title: 'Google 搜索',
    description: '调用 Google 搜索服务。',
    category: 'external',
    external: true,
  },
  [Operator.Bing]: {
    title: 'Bing 搜索',
    description: '调用 Bing 搜索服务。',
    category: 'external',
    external: true,
  },
  [Operator.GoogleScholar]: {
    title: 'Google Scholar',
    description: '检索学术论文和引用信息。',
    category: 'external',
    external: true,
  },
  [Operator.Wikipedia]: {
    title: '维基百科',
    description: '检索维基百科词条内容。',
    category: 'external',
    external: true,
  },
  [Operator.PubMed]: {
    title: 'PubMed',
    description: '检索医学文献摘要。',
    category: 'external',
    external: true,
  },
  [Operator.ArXiv]: {
    title: 'ArXiv',
    description: '检索 ArXiv 论文信息。',
    category: 'external',
    external: true,
  },
  [Operator.GitHub]: {
    title: 'GitHub',
    description: '访问 GitHub 仓库、Issue 或代码信息。',
    category: 'external',
    external: true,
  },
  [Operator.SearXNG]: {
    title: 'SearXNG 搜索',
    description: '调用 SearXNG 聚合搜索服务。',
    category: 'external',
    external: true,
  },
  [Operator.YahooFinance]: {
    title: 'Yahoo Finance',
    description: '查询股票、指数等金融数据。',
    category: 'external',
    external: true,
  },
  [Operator.WenCai]: {
    title: '问财',
    description: '调用问财金融数据接口。',
    category: 'external',
    external: true,
  },
  [Operator.Crawler]: {
    title: '网页爬取',
    description: '抓取指定网页内容。',
    category: 'external',
    external: true,
  },
  [Operator.ExeSQL]: {
    title: '执行 SQL',
    description: '连接数据库并执行 SQL 查询。',
    category: 'database',
    external: true,
  },
  [Operator.ScopedDBConnector]: {
    title: '受控数据库连接',
    description: '在限定权限范围内连接数据库。',
    category: 'database',
    external: true,
  },
  [Operator.SafeTableEnsure]: {
    title: '安全建表',
    description: '按白名单和约束创建或确认表结构。',
    category: 'database',
    external: true,
  },
  [Operator.SafeRecordInsert]: {
    title: '安全插入',
    description: '在受控表中插入记录。',
    category: 'database',
    external: true,
  },
  [Operator.SafeRecordUpdate]: {
    title: '安全更新',
    description: '在受控范围内更新记录。',
    category: 'database',
    external: true,
  },
  [Operator.SafeRecordQuery]: {
    title: '安全查询',
    description: '在受控表和字段范围内查询记录。',
    category: 'database',
    external: true,
  },
  [Operator.HumanReview]: {
    title: '人工复核',
    description: '把关键结果交给人工确认或补充意见。',
    category: 'review',
  },
  [Operator.ManualApprove]: {
    title: '人工审批',
    description: '对写文件、patch 或高风险动作进行人工审批。',
    category: 'review',
  },
  [Operator.Tool]: {
    title: '工具',
    description: '作为智能体工具配置的一部分，由智能体节点调用。',
    category: 'foundation',
  },
  [Operator.Placeholder]: {
    title: '占位节点',
    description: '拖拽连线时临时出现的节点占位。',
    category: 'flow',
  },
  [Operator.Note]: {
    title: '备注',
    description: '在画布上写说明，不参与实际运行。',
    category: 'inputOutput',
  },
  [Operator.File]: {
    title: '文件入口',
    description: '数据流水线中的文件输入节点。',
    category: 'document',
  },
  [Operator.Parser]: {
    title: '解析器',
    description: '数据流水线中的文档解析配置节点。',
    category: 'document',
  },
  [Operator.Tokenizer]: {
    title: '分词器',
    description: '把文本切分为模型或索引可处理的 token 单元。',
    category: 'document',
  },
  [Operator.TokenChunker]: {
    title: 'Token 切块',
    description: '按 token 数把文本切成知识库片段。',
    category: 'document',
  },
  [Operator.TitleChunker]: {
    title: '标题切块',
    description: '按标题和章节结构切分文档。',
    category: 'document',
  },
  [Operator.Extractor]: {
    title: '抽取器',
    description: '从文档片段中抽取关键信息或元数据。',
    category: 'document',
    external: true,
  },
};

export function getNodeGuide(operator?: string): NodeGuideDefinition {
  const normalized = operator || '';
  return (
    NodeGuideMap[normalized] || {
      title: normalized || '未命名节点',
      description: normalized
        ? `执行 ${normalized} 节点对应的处理逻辑。`
        : '节点信息缺失，无法判断具体用途。',
      category: 'foundation',
    }
  );
}

export function getNodeGuideCategory(categoryId?: string) {
  return (
    NodeGuideCategories.find((category) => category.id === categoryId) ||
    NodeGuideCategories[0]
  );
}
