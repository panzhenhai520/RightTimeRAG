import { Button } from '@/components/ui/button';
import { useNavigatePage } from '@/hooks/logic-hooks/navigate-hooks';
import {
  ArrowLeft,
  BookOpenText,
  CheckCircle2,
  ClipboardCheck,
  ExternalLink,
  FileArchive,
  FileSearch,
  FileText,
  GitBranch,
  Layers3,
  Network,
  PackageCheck,
  PlayCircle,
  Search,
  TableProperties,
} from 'lucide-react';
import { caseSteps, caseValidationItems } from './agent-creation-guide-data';
import styles from './agent-creation-guide.module.less';

const flowNodes = [
  {
    title: '入口与意图',
    text: 'Begin、GoalIntentClassifier、Categorize、UserFillUp',
  },
  {
    title: '资料搜集',
    text: 'Retrieval、TavilySearch、TavilyExtract、WorkspaceFileSearch',
  },
  {
    title: '文件读取',
    text: 'FileParser、WorkspaceFileRead、WorkspaceTableRead、DocumentNormalizer',
  },
  {
    title: '结构抽取',
    text: 'ContractClauseExtractor、ClauseExtractor、TableFactExtractor',
  },
  {
    title: '任务编排',
    text: 'TaskPlanner、AtomicTaskRefiner、PreconditionChecker、TaskFrameController',
  },
  {
    title: '比对核验',
    text: 'DocumentDiff、DocumentSemanticComparer、DocumentConflictDetector',
  },
  {
    title: '大模型综合',
    text: 'Agent:Synthesis 读取规划、条款、差异、冲突和基础报告后生成最终分析',
  },
  {
    title: '报告产物',
    text: 'RiskScorer、ChartRenderer、ReportComposer、DocGenerator、WorkspaceFileWrite',
  },
  {
    title: '受控改写',
    text: '修改用户原文件时再使用 WorkspacePatchApply、ManualApprove、HumanReview',
  },
  {
    title: '校验迭代',
    text: 'TaskResultVerifier、TaskReflection、ReplanDecider、Loop、HumanReview',
  },
];

const caseAgentId = '6f6145de757a11f1b4075dddb426bed0';
const caseAgentCanvasPath = `/agent/${caseAgentId}?category=agent_canvas`;
const caseAgentExplorePath = `/agent/${caseAgentId}/explore`;

const buildPrompt = `你是复杂任务资料整理与文档核对智能体。

输入：
1. 用户目标：{sys.query}
2. 文件 A：通过运行页浏览按钮选择工作区文件
3. 文件 B：通过运行页浏览按钮选择工作区文件
4. 输出空间：智能体默认工作空间内的 output/document-review-report.md

执行规则：
1. 先识别目标类型和缺失输入，不确定时让用户补充。
2. 找到候选文件后说明选择原因，再读取和规范化。
3. 法规/制度抽取要求项，合同/项目文件抽取条款和表格事实。
4. 同时输出精确差异、包含/缺失关系、冲突条款和风险等级。
5. Agent:Synthesis 调用本机大模型，把规划、条款、差异、冲突和基础报告综合成最终分析。
6. 普通报告自动写入智能体输出空间；涉及修改用户原文件时，先 dry-run 展示 diff，再人工确认。
7. 最终输出 Markdown 报告、结构化表格、可下载文件、工作区输出记录和审计摘要。`;

export default function AgentCreationCase() {
  const { navigateToAgents, navigateToAgentCreationGuide } = useNavigatePage();

  return (
    <main className={styles.page}>
      <div className={styles.content}>
        <header className={styles.pageHeader}>
          <div className={styles.titleBlock}>
            <div className={styles.eyebrow}>智能体培训页面</div>
            <h1 className={styles.title}>智能体创建案例</h1>
            <p className={styles.subtitle}>
              案例目标：创建一个复杂任务 AI
              智能体，能够根据任务搜集资料、整理文件、对照文件、分类归类、
              总结对比、输出报告、形成表格并生成可下载文件。这个案例尽量串起当前智能体平台的流程控制、
              文档处理、任务处理、报告审计和人工复核能力。
            </p>
          </div>
          <div className={styles.headerActions}>
            <Button variant="secondary" onClick={navigateToAgents}>
              <ArrowLeft />
              返回智能体
            </Button>
            <Button variant="outline" onClick={navigateToAgentCreationGuide}>
              <BookOpenText />
              查看创建指南
            </Button>
          </div>
        </header>

        <section className={styles.section}>
          <div className={styles.scenarioGrid}>
            <article className={styles.scenarioPanel}>
              <FileSearch className={styles.fallbackIcon} />
              <h3>训练场景</h3>
              <ul className={styles.plainList}>
                <li>
                  用户输入任务说明，并通过浏览按钮选择合同、制度或历史报告。
                </li>
                <li>智能体自动找出相关文件和资料来源。</li>
                <li>逐段、逐条款、逐表格比较差异和冲突。</li>
                <li>
                  调用大模型综合分析，生成报告、风险清单、表格和文件产物。
                </li>
              </ul>
            </article>
            <article className={styles.scenarioPanel}>
              <PackageCheck className={styles.fallbackIcon} />
              <h3>最终交付物</h3>
              <ul className={styles.plainList}>
                <li>Markdown 主报告。</li>
                <li>合同条款与法规要求比对表。</li>
                <li>风险等级统计图和风险清单。</li>
                <li>DOCX/XLSX/JSON/工作区输出文件及执行审计。</li>
              </ul>
            </article>
          </div>
        </section>

        <section className={styles.section}>
          <article
            className={`${styles.scenarioPanel} ${styles.caseAgentPanel}`}
          >
            <div className={styles.caseAgentHeader}>
              <PackageCheck className={styles.fallbackIcon} />
              <div>
                <h3>已发布案例智能体</h3>
                <p>
                  这个智能体已经按本页案例创建并发布，可打开画布查看节点结构，也可以进入运行页体验输入表单和执行流程。
                </p>
              </div>
            </div>
            <div className={styles.caseAgentMeta}>
              <span>名称：文档核对案例智能体</span>
              <span>ID：{caseAgentId}</span>
            </div>
            <div className={styles.caseAgentActions}>
              <Button asLink to={caseAgentCanvasPath}>
                <ExternalLink />
                打开画布
              </Button>
              <Button asLink variant="outline" to={caseAgentExplorePath}>
                <PlayCircle />
                运行体验
              </Button>
            </div>
          </article>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2>画布流程示意</h2>
              <p>
                实际创建时可以按这个顺序把节点放到画布上。工作区写入和 Patch
                节点分两类：报告输出可写入智能体输出空间；修改用户原文件才进入
                dry-run 和人工确认。
              </p>
            </div>
          </div>
          <div className={styles.caseFlow}>
            {flowNodes.map((node, index) => (
              <div className={styles.flowNode} key={node.title}>
                <div className={styles.flowNodeTitle}>
                  <span className={styles.flowStepIndex}>{index + 1}</span>
                  <span>{node.title}</span>
                </div>
                <div className={styles.flowNodeText}>{node.text}</div>
              </div>
            ))}
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2>创建步骤</h2>
              <p>
                每一步都有明确边界：先完成本阶段配置和测试，再进入下一阶段。这样能避免复杂智能体一次性堆节点后无法定位问题。
              </p>
            </div>
          </div>
          <div className={styles.stepList}>
            {caseSteps.map((step, index) => (
              <article className={styles.stepCard} key={step.title}>
                <div className={styles.stepNumber}>{index + 1}</div>
                <div className={styles.stepBody}>
                  <h3>{step.title}</h3>
                  <p className={styles.stepGoal}>{step.goal}</p>
                  <div className={styles.stepColumns}>
                    <div>
                      <div className={styles.ioLabel}>推荐节点</div>
                      <div className={styles.pillList}>
                        {step.nodes.map((node) => (
                          <span className={styles.pill} key={node}>
                            {node}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div>
                      <div className={styles.ioLabel}>关键配置</div>
                      <ul className={styles.plainList}>
                        {step.configuration.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                  <p className={styles.stepOutput}>阶段产物：{step.output}</p>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2>关键配置模板</h2>
              <p>
                创建智能体节点时，可以把这段作为系统提示词或 PromptTemplate
                的基础模板，再把变量接到 Begin、文件解析和任务规划输出上。
              </p>
            </div>
          </div>
          <pre className={styles.codeBlock}>{buildPrompt}</pre>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2>节点使用覆盖</h2>
              <p>
                这个案例不要求每个任务都强行使用所有节点，但覆盖了创建复杂智能体时最常用的能力组。下面是能力组和对应节点。
              </p>
            </div>
          </div>
          <div className={styles.layerGrid}>
            {[
              {
                icon: GitBranch,
                title: '流程控制',
                items: [
                  'Categorize',
                  'Switch',
                  'Iteration',
                  'Loop',
                  'ExitLoop',
                  'UserFillUp',
                ],
              },
              {
                icon: FileText,
                title: '文档处理',
                items: [
                  'FileParser',
                  'DocumentNormalizer',
                  'WorkspaceFileRead',
                  'DocumentDiff',
                  'DocumentConflictDetector',
                ],
              },
              {
                icon: TableProperties,
                title: '表格与图表',
                items: [
                  'WorkspaceTableRead',
                  'ExcelProcessor',
                  'ChartSpecBuilder',
                  'ChartRenderer',
                ],
              },
              {
                icon: Search,
                title: '资料搜集',
                items: [
                  'Retrieval',
                  'TavilySearch',
                  'TavilyExtract',
                  'SearXNG',
                  'Browser',
                ],
              },
              {
                icon: Layers3,
                title: '任务拆解',
                items: [
                  'GoalIntentClassifier',
                  'TaskPlanner',
                  'AtomicTaskRefiner',
                  'TaskFrameController',
                ],
              },
              {
                icon: Network,
                title: '协作复核',
                items: [
                  'AgentFanout',
                  'ResultAggregator',
                  'HumanReview',
                  'ManualApprove',
                  'WebhookInput',
                ],
              },
              {
                icon: ClipboardCheck,
                title: '合规核验',
                items: [
                  'ContractClauseExtractor',
                  'ComplianceChecklistGenerator',
                  'ClauseMatcher',
                  'ComplianceVerifier',
                  'RiskScorer',
                ],
              },
              {
                icon: FileArchive,
                title: '报告产物',
                items: [
                  'ReportComposer',
                  'ComplianceReportComposer',
                  'DocGenerator',
                  'ArtifactPackager',
                ],
              },
            ].map((group) => {
              const Icon = group.icon;
              return (
                <article className={styles.layerCard} key={group.title}>
                  <Icon className={styles.fallbackIcon} />
                  <h3>{group.title}</h3>
                  <div className={styles.pillList}>
                    {group.items.map((item) => (
                      <span className={styles.pill} key={item}>
                        {item}
                      </span>
                    ))}
                  </div>
                </article>
              );
            })}
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2>验收清单</h2>
              <p>
                训练完成后，用这组清单验证智能体是否真正具备文件相关复杂任务能力。
              </p>
            </div>
          </div>
          <div className={styles.validationGrid}>
            {caseValidationItems.map((item) => (
              <div className={styles.validationItem} key={item}>
                <CheckCircle2 className="size-4" />
                <span>{item}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
