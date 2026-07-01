import { Button } from '@/components/ui/button';
import { Operator } from '@/constants/agent';
import { useNavigatePage } from '@/hooks/logic-hooks/navigate-hooks';
import { useFetchAgentOperatorSchema } from '@/hooks/use-agent-request';
import { IAgentOperatorManifest } from '@/interfaces/database/agent';
import OperatorIcon, {
  LucideIconMap,
  OperatorIconMap,
  SVGIconMap,
} from '@/pages/agent/operator-icon';
import {
  ArrowLeft,
  BookOpenText,
  Brain,
  ClipboardCheck,
  Database,
  FileSearch,
  FileText,
  GitBranch,
  Layers3,
  Network,
  PackageCheck,
  Route,
  Search,
  Settings2,
  TableProperties,
  Wrench,
  type LucideIcon,
} from 'lucide-react';
import { useMemo } from 'react';
import {
  canvasNodeGroups,
  capabilityLayers,
  functionalChoices,
  GuideNode,
  serviceNodeGroups,
} from './agent-creation-guide-data';
import styles from './agent-creation-guide.module.less';

const getNodeKey = (node: GuideNode) =>
  node.operator ?? node.serviceName ?? node.title;

const getCanvasNodeGroupId = (index: number) =>
  `creator-node-group-${index + 1}`;

const guideValidationItems: Array<{
  title: string;
  text: string;
  icon: LucideIcon;
}> = [
  {
    title: '图标对照',
    text: '页面中的节点图标优先来自创建器实际 OperatorIcon 映射。',
    icon: FileSearch,
  },
  {
    title: '流程闭环',
    text: '分类、前置条件、执行、校验、反思、重规划构成可持续迭代。',
    icon: Brain,
  },
  {
    title: '审计边界',
    text: '涉及文件读取、冲突判断、人工审批和产物生成时都要保留引用。',
    icon: ClipboardCheck,
  },
];

const hasRealOperatorIcon = (operator?: Operator) => {
  if (!operator) return false;
  return (
    operator === Operator.Begin ||
    Object.prototype.hasOwnProperty.call(OperatorIconMap, operator) ||
    Object.prototype.hasOwnProperty.call(SVGIconMap, operator) ||
    Object.prototype.hasOwnProperty.call(LucideIconMap, operator)
  );
};

const getFallbackIcon = (node: GuideNode): LucideIcon => {
  const value = `${node.group}${node.title}${node.serviceName ?? ''}`;
  if (value.includes('任务')) return Route;
  if (value.includes('文档') || value.includes('文件')) return FileText;
  if (value.includes('表格') || value.includes('Excel')) return TableProperties;
  if (
    value.includes('流程') ||
    value.includes('循环') ||
    value.includes('分支')
  ) {
    return GitBranch;
  }
  if (value.includes('数据库') || value.includes('SQL')) return Database;
  if (value.includes('搜索') || value.includes('检索')) return Search;
  if (value.includes('多智能体') || value.includes('会议')) return Network;
  if (value.includes('报告') || value.includes('产物')) return PackageCheck;
  return Wrench;
};

const getManifest = (
  node: GuideNode,
  manifestMap: Map<string, IAgentOperatorManifest>,
) => {
  const operatorKey = node.operator ? String(node.operator) : undefined;
  return (
    (node.serviceName && manifestMap.get(node.serviceName)) ||
    (operatorKey && manifestMap.get(operatorKey)) ||
    undefined
  );
};

const getRuntimeLabels = (manifest?: IAgentOperatorManifest) => {
  if (!manifest) return [];
  const capabilities = manifest.runtime_capabilities;
  return [
    capabilities.accepts_files && '接收文件',
    capabilities.produces_artifacts && '产出附件',
    capabilities.uses_external_io && '外部 IO',
    capabilities.long_running && '长任务',
    capabilities.supports_cancel && '可取消',
  ].filter(Boolean) as string[];
};

function NodeIcon({ node }: { node: GuideNode }) {
  const FallbackIcon = getFallbackIcon(node);

  return (
    <span className={styles.nodeIcon} aria-hidden="true">
      {hasRealOperatorIcon(node.operator) ? (
        <OperatorIcon name={node.operator as Operator} />
      ) : (
        <FallbackIcon />
      )}
    </span>
  );
}

function NodeCard({
  node,
  manifestMap,
}: {
  node: GuideNode;
  manifestMap: Map<string, IAgentOperatorManifest>;
}) {
  const manifest = getManifest(node, manifestMap);
  const runtimeLabels = getRuntimeLabels(manifest);

  return (
    <article className={styles.nodeCard}>
      <div className={styles.nodeTop}>
        <NodeIcon node={node} />
        <div>
          <div className={styles.nodeTitleRow}>
            <span className={styles.nodeTitle}>{node.title}</span>
            <span
              className={`${styles.badge} ${
                node.availability === 'canvas'
                  ? styles.badgeCanvas
                  : styles.badgeService
              }`}
            >
              {node.availability === 'canvas' ? '创建器可添加' : '服务组件'}
            </span>
          </div>
          <div className={styles.operatorName}>{getNodeKey(node)}</div>
          {manifest && (
            <div className={styles.serviceMeta}>
              <span className={styles.pill}>风险：{manifest.risk_level}</span>
              {manifest.requires_service?.map((service) => (
                <span className={styles.pill} key={service}>
                  依赖：{service}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      <p className={styles.nodePurpose}>{node.purpose}</p>

      <div className={styles.ioGrid}>
        <div className={styles.ioBlock}>
          <div className={styles.ioLabel}>输入</div>
          <div className={styles.pillList}>
            {node.inputs.map((item) => (
              <span className={styles.pill} key={item}>
                {item}
              </span>
            ))}
          </div>
        </div>
        <div className={styles.ioBlock}>
          <div className={styles.ioLabel}>输出</div>
          <div className={styles.pillList}>
            {node.outputs.map((item) => (
              <span className={styles.pill} key={item}>
                {item}
              </span>
            ))}
          </div>
        </div>
      </div>

      {runtimeLabels.length > 0 && (
        <div className={styles.capabilityTags}>
          {runtimeLabels.map((label) => (
            <span className={styles.pill} key={label}>
              {label}
            </span>
          ))}
        </div>
      )}

      <p className={styles.useWhen}>使用场景：{node.useWhen}</p>
    </article>
  );
}

export default function AgentCreationGuide() {
  const { navigateToAgents, navigateToAgentCreationCase } = useNavigatePage();
  const { data: manifests, loading } = useFetchAgentOperatorSchema();

  const manifestMap = useMemo(() => {
    return new Map(
      manifests.flatMap((manifest) => [
        [manifest.operator, manifest] as const,
        [manifest.component_name, manifest] as const,
      ]),
    );
  }, [manifests]);

  const canvasNodeCount = canvasNodeGroups.reduce(
    (sum, group) => sum + group.nodes.length,
    0,
  );
  const serviceNodeCount = serviceNodeGroups.reduce(
    (sum, group) => sum + group.nodes.length,
    0,
  );
  const scrollToCanvasNodeGroup = (index: number) => {
    document
      .getElementById(getCanvasNodeGroupId(index))
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <main className={styles.page}>
      <div className={styles.content}>
        <header className={styles.pageHeader}>
          <div className={styles.titleBlock}>
            <div className={styles.eyebrow}>智能体培训页面</div>
            <h1 className={styles.title}>智能体创建指南</h1>
            <p className={styles.subtitle}>
              这份指南按当前代码里的智能体画布节点、数据流节点和后端能力组件整理。
              “创建器可添加”表示现在能在智能体创建画布里直接选择；“服务组件”表示后端已经具备
              schema 和执行能力，适合继续封装成可拖拽节点或由编排层调用。
            </p>
          </div>
          <div className={styles.headerActions}>
            <Button variant="secondary" onClick={navigateToAgents}>
              <ArrowLeft />
              返回智能体
            </Button>
            <Button variant="outline" onClick={navigateToAgentCreationCase}>
              <BookOpenText />
              查看创建案例
            </Button>
          </div>
        </header>

        <section className={styles.section}>
          <div className={styles.summaryGrid}>
            <div className={styles.statCard}>
              <span className={styles.statNumber}>{canvasNodeCount}</span>
              <span className={styles.statLabel}>当前可讲解画布节点</span>
              <span className={styles.statText}>
                覆盖基础、对话、流程、文档、数据处理、工具和数据流画布。
              </span>
            </div>
            <div className={styles.statCard}>
              <span className={styles.statNumber}>{serviceNodeCount}</span>
              <span className={styles.statLabel}>任务和文档服务组件</span>
              <span className={styles.statText}>
                支撑目标识别、任务分解、指定路径读取、文档结构化和冲突判断。
              </span>
            </div>
            <div className={styles.statCard}>
              <span className={styles.statNumber}>
                {loading ? '...' : manifests.length || '本地'}
              </span>
              <span className={styles.statLabel}>后端 operator schema</span>
              <span className={styles.statText}>
                页面会尽量读取后端注册组件，并显示风险等级、附件产出、外部 IO
                等运行能力。
              </span>
            </div>
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2>能力层说明</h2>
              <p>
                创建智能体时不要只看单个节点，而要把节点放进能力层：流程控制、文档处理、任务处理、报告审计。
              </p>
            </div>
          </div>
          <div className={styles.layerGrid}>
            {capabilityLayers.map((layer) => (
              <article
                className={`${styles.layerCard} ${styles.capabilityLayerCard}`}
                key={layer.title}
              >
                <h3>{layer.title}</h3>
                <p>{layer.summary}</p>
                <ul className={styles.plainList}>
                  {layer.abilities.map((ability) => (
                    <li key={ability}>{ability}</li>
                  ))}
                </ul>
                <div className={styles.ioLabel}>
                  代表性节点（英文为节点/组件标识）
                </div>
                <div className={styles.pillList}>
                  {layer.representativeNodes.map((node) => (
                    <span className={styles.pill} key={node}>
                      {node}
                    </span>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2>创建器可添加节点</h2>
              <p>
                下方节点对照的是智能体创建器里已经暴露或代码中已存在的节点。图标优先使用当前创建器节点图标，缺失时使用同类功能图标补位。
              </p>
            </div>
          </div>

          <div className={styles.groupIndex} aria-label="节点分类索引">
            <span className={styles.groupIndexLabel}>节点分类索引</span>
            {canvasNodeGroups.map((group, index) => (
              <button
                className={styles.groupIndexButton}
                key={group.title}
                onClick={() => scrollToCanvasNodeGroup(index)}
                type="button"
              >
                {group.title}
              </button>
            ))}
          </div>

          {canvasNodeGroups.map((group, index) => (
            <section
              className={styles.groupBlock}
              id={getCanvasNodeGroupId(index)}
              key={group.title}
            >
              <h3 className={styles.groupTitle}>{group.title}</h3>
              <p className={styles.groupDescription}>{group.description}</p>
              <div className={styles.nodeGrid}>
                {group.nodes.map((node) => (
                  <NodeCard
                    key={getNodeKey(node)}
                    node={node}
                    manifestMap={manifestMap}
                  />
                ))}
              </div>
            </section>
          ))}
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2>功能性选择说明</h2>
              <p>
                解析器、抽取器、比对器、报告器和人工控制节点经常容易混用。这里按任务目标给出选择边界。
              </p>
            </div>
          </div>
          <div className={styles.choiceGrid}>
            {functionalChoices.map((choice) => (
              <article
                className={`${styles.choiceCard} ${styles.functionalChoiceCard}`}
                key={choice.title}
              >
                <h3>{choice.title}</h3>
                <ul className={styles.plainList}>
                  {choice.choices.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
                <p>建议：{choice.recommendation}</p>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h2>服务组件能力盘点</h2>
              <p>
                这些能力已经进入后端组件 schema。它们是让智能体具备“像 Codex
                一样读文件、找文件、分解任务、逐步校验、回到上级任务”的关键层。
              </p>
            </div>
          </div>

          {serviceNodeGroups.map((group) => (
            <section className={styles.groupBlock} key={group.title}>
              <h3 className={styles.groupTitle}>{group.title}</h3>
              <p className={styles.groupDescription}>{group.description}</p>
              <div className={styles.serviceList}>
                {group.nodes.map((node) => (
                  <NodeCard
                    key={getNodeKey(node)}
                    node={node}
                    manifestMap={manifestMap}
                  />
                ))}
              </div>
            </section>
          ))}
        </section>

        <section className={styles.section}>
          <div className={styles.scenarioGrid}>
            <article className={styles.scenarioPanel}>
              <Layers3 className={styles.fallbackIcon} />
              <h3>搭建顺序</h3>
              <ul className={styles.plainList}>
                <li>先定入口变量、文件输入和任务边界。</li>
                <li>再做意图分类和缺失信息补齐。</li>
                <li>然后接文件读取、解析、抽取、比对、报告。</li>
                <li>最后加校验、人工复核和产物打包。</li>
              </ul>
            </article>
            <article className={styles.scenarioPanel}>
              <Settings2 className={styles.fallbackIcon} />
              <h3>测试顺序</h3>
              <ul className={styles.plainList}>
                <li>单节点调试：先确认每个节点输出字段存在。</li>
                <li>小样本联调：用两份短文件跑通端到端流程。</li>
                <li>边界测试：缺文件、空表格、冲突条款、超长文档。</li>
                <li>审计检查：确认报告引用、附件和风险记录完整。</li>
              </ul>
            </article>
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.validationGrid}>
            {guideValidationItems.map(({ title, text, icon: CurrentIcon }) => {
              return (
                <div className={styles.validationItem} key={title}>
                  <CurrentIcon className="size-4" />
                  <span>
                    <strong>{title}</strong>：{text}
                  </span>
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </main>
  );
}
