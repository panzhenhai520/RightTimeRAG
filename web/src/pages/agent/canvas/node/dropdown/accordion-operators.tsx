import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Input } from '@/components/ui/input';
import { Operator } from '@/constants/agent';
import {
  NodeGuideCategoryId,
  getNodeGuide,
  getNodeGuideCategory,
} from '@/pages/agent/node-guide';
import useGraphStore from '@/pages/agent/store';
import {
  PropsWithChildren,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { OperatorItemList } from './operator-item-list';

function OperatorAccordionTrigger({ children }: PropsWithChildren) {
  return (
    <AccordionTrigger className="text-xs text-text-secondary hover:no-underline items-center">
      <span className="h-4 translate-y-1"> {children}</span>
    </AccordionTrigger>
  );
}

function OperatorSearchInput({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="px-2 pb-2">
      <Input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={t('flow.search') || 'Search'}
        className="h-8 text-xs"
      />
    </div>
  );
}

type OperatorGroup = {
  id: NodeGuideCategoryId;
  operators: Operator[];
};

const AgentOperatorGroups: OperatorGroup[] = [
  {
    id: 'foundation',
    operators: [Operator.Agent, Operator.Retrieval, Operator.RewriteQuestion],
  },
  {
    id: 'inputOutput',
    operators: [
      Operator.Message,
      Operator.UserFillUp,
      Operator.WaitingDialogue,
      Operator.Note,
    ],
  },
  {
    id: 'flow',
    operators: [
      Operator.Switch,
      Operator.Iteration,
      Operator.Loop,
      Operator.Categorize,
    ],
  },
  {
    id: 'document',
    operators: [
      Operator.FileParser,
      Operator.WorkspaceFileWrite,
      Operator.WorkspacePatchApply,
      Operator.DocGenerator,
      Operator.ExcelProcessor,
    ],
  },
  {
    id: 'data',
    operators: [
      Operator.Code,
      Operator.StringTransform,
      Operator.PromptTemplate,
      Operator.ScoreRubricBuilder,
      Operator.PronunciationJudge,
      Operator.SummaryNode,
      Operator.ReportComposer,
      Operator.NumberCalculate,
      Operator.ChartSpecBuilder,
      Operator.ChartRenderer,
      Operator.ArtifactPackager,
      Operator.DataOperations,
      Operator.ListOperations,
      Operator.VariableAssigner,
      Operator.VariableAggregator,
    ],
  },
  {
    id: 'compliance',
    operators: [
      Operator.ContractClauseExtractor,
      Operator.ComplianceChecklistGenerator,
      Operator.ClauseMatcher,
      Operator.ComplianceVerifier,
      Operator.RiskScorer,
      Operator.ComplianceReportComposer,
    ],
  },
  {
    id: 'voice',
    operators: [
      Operator.AudioInput,
      Operator.ASRTranscribe,
      Operator.TTSGenerate,
      Operator.VoiceReplyOutput,
      Operator.MeetingContextInput,
      Operator.MemoryInject,
      Operator.AgentFanout,
      Operator.ResultAggregator,
    ],
  },
  {
    id: 'external',
    operators: [
      Operator.TavilySearch,
      Operator.TavilyExtract,
      Operator.Invoke,
      Operator.Email,
      Operator.Browser,
      Operator.ExeSQL,
      Operator.Google,
      Operator.Bing,
      Operator.DuckDuckGo,
      Operator.Wikipedia,
      Operator.GoogleScholar,
      Operator.ArXiv,
      Operator.PubMed,
      Operator.GitHub,
      Operator.WenCai,
      Operator.YahooFinance,
      Operator.SearXNG,
      Operator.Crawler,
      Operator.WebhookInput,
      Operator.ExternalScoreReceiver,
    ],
  },
  {
    id: 'database',
    operators: [
      Operator.ScopedDBConnector,
      Operator.SafeTableEnsure,
      Operator.SafeRecordInsert,
      Operator.SafeRecordUpdate,
      Operator.SafeRecordQuery,
    ],
  },
  {
    id: 'review',
    operators: [Operator.HumanReview, Operator.ManualApprove],
  },
];

function operatorMatchesQuery(operator: Operator, query: string) {
  const keyword = query.trim().toLowerCase();
  if (!keyword) {
    return true;
  }
  const guide = getNodeGuide(operator);
  const category = getNodeGuideCategory(guide.category);
  return [
    operator,
    guide.title,
    guide.description,
    category.title,
    category.description,
    guide.external ? '外部 api 外部服务' : '',
  ]
    .join(' ')
    .toLowerCase()
    .includes(keyword);
}

function buildVisibleGroups(groups: OperatorGroup[], query: string) {
  return groups
    .map((group) => ({
      ...group,
      operators: group.operators.filter((operator) =>
        operatorMatchesQuery(operator, query),
      ),
    }))
    .filter((group) => group.operators.length > 0);
}

export function AccordionOperators({
  isCustomDropdown = false,
  mousePosition,
  nodeId,
}: {
  isCustomDropdown?: boolean;
  mousePosition?: { x: number; y: number };
  nodeId?: string;
}) {
  const [query, setQuery] = useState('');
  const [activeGroupId, setActiveGroupId] =
    useState<NodeGuideCategoryId>('foundation');
  const { getOperatorTypeFromId, getParentIdById } = useGraphStore(
    (state) => state,
  );

  const exitLoopList = useMemo(() => {
    if (getOperatorTypeFromId(getParentIdById(nodeId)) === Operator.Loop) {
      return [Operator.ExitLoop];
    }
    return [];
  }, [getOperatorTypeFromId, getParentIdById, nodeId]);

  const groups = useMemo(() => {
    return AgentOperatorGroups.map((group) =>
      group.id === 'flow'
        ? { ...group, operators: [...group.operators, ...exitLoopList] }
        : group,
    );
  }, [exitLoopList]);

  const visibleGroups = useMemo(
    () => buildVisibleGroups(groups, query),
    [groups, query],
  );
  const activeGroup = useMemo(() => {
    return (
      visibleGroups.find((group) => group.id === activeGroupId) ||
      visibleGroups[0]
    );
  }, [activeGroupId, visibleGroups]);

  useEffect(() => {
    if (activeGroup && activeGroup.id !== activeGroupId) {
      setActiveGroupId(activeGroup.id);
    }
  }, [activeGroup, activeGroupId]);

  const activeCategory = getNodeGuideCategory(activeGroup?.id);

  return (
    <div className="px-3 pb-3 text-text-title">
      <OperatorSearchInput value={query} onChange={setQuery} />
      <div className="grid max-h-[58vh] grid-cols-[150px_minmax(0,1fr)] gap-3 overflow-hidden">
        <div className="min-h-0 space-y-1 overflow-auto pr-1">
          {visibleGroups.map((group) => {
            const category = getNodeGuideCategory(group.id);
            const active = group.id === activeGroup?.id;
            return (
              <button
                key={group.id}
                type="button"
                onClick={() => setActiveGroupId(group.id)}
                className={[
                  'flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-xs font-medium',
                  active
                    ? 'bg-background-card text-text-primary'
                    : 'text-text-secondary hover:bg-background-card',
                ].join(' ')}
              >
                <span>{category.title}</span>
                <span className="text-[11px] text-text-secondary">
                  {group.operators.length}
                </span>
              </button>
            );
          })}
        </div>
        <div className="min-h-0 overflow-hidden rounded-md border border-border bg-bg-base">
          <div className="border-b border-border px-3 py-2">
            <div className="text-sm font-medium text-text-primary">
              {activeCategory.title}
            </div>
            <div className="mt-1 text-xs font-normal leading-5 text-text-secondary">
              {activeCategory.description}
            </div>
          </div>
          <OperatorItemList
            operators={activeGroup?.operators || []}
            isCustomDropdown={isCustomDropdown}
            mousePosition={mousePosition}
            query={query}
            variant="card"
          ></OperatorItemList>
        </div>
      </div>
      {visibleGroups.length === 0 && (
        <div className="px-2 py-6 text-center text-xs font-normal text-text-secondary">
          没有找到匹配的节点
        </div>
      )}
    </div>
  );
}

// Limit the number of operators of a certain type on the canvas to only one
function useRestrictSingleOperatorOnCanvas() {
  const { findNodeByName } = useGraphStore((state) => state);

  const restrictSingleOperatorOnCanvas = useCallback(
    (singleOperators: Operator[]) => {
      const list: Operator[] = [];
      singleOperators.forEach((operator) => {
        if (!findNodeByName(operator)) {
          list.push(operator);
        }
      });
      return list;
    },
    [findNodeByName],
  );

  return restrictSingleOperatorOnCanvas;
}

export function PipelineAccordionOperators({
  isCustomDropdown = false,
  mousePosition,
  nodeId,
}: {
  isCustomDropdown?: boolean;
  mousePosition?: { x: number; y: number };
  nodeId?: string;
}) {
  const [query, setQuery] = useState('');
  const restrictSingleOperatorOnCanvas = useRestrictSingleOperatorOnCanvas();
  const { getOperatorTypeFromId } = useGraphStore((state) => state);
  const sourceOperator = getOperatorTypeFromId(nodeId);

  const operators = useMemo(() => {
    const list = [...restrictSingleOperatorOnCanvas([Operator.Parser])];

    if (sourceOperator === Operator.Extractor) {
      list.push(Operator.Tokenizer, Operator.DocGenerator);
    } else {
      list.push(...restrictSingleOperatorOnCanvas([Operator.Tokenizer]));
    }

    list.push(Operator.Extractor);
    return Array.from(new Set(list));
  }, [restrictSingleOperatorOnCanvas, sourceOperator]);

  const chunkerOperators = useMemo(() => {
    return [
      ...restrictSingleOperatorOnCanvas([
        Operator.TokenChunker,
        Operator.TitleChunker,
      ]),
    ];
  }, [restrictSingleOperatorOnCanvas]);

  const showChunker = useMemo(() => {
    return sourceOperator !== Operator.Extractor && chunkerOperators.length > 0;
  }, [chunkerOperators.length, sourceOperator]);

  return (
    <>
      <OperatorSearchInput value={query} onChange={setQuery} />
      <OperatorItemList
        operators={operators}
        isCustomDropdown={isCustomDropdown}
        mousePosition={mousePosition}
        query={query}
      ></OperatorItemList>
      {showChunker && (
        <Accordion
          type="single"
          collapsible
          className="w-full px-4"
          defaultValue="item-1"
        >
          <AccordionItem value="item-1">
            <AccordionTrigger className="translate-y-2 hover:no-underline text-text-primary font-normal">
              Chunker
            </AccordionTrigger>
            <AccordionContent className="flex flex-col gap-4">
              <OperatorItemList
                operators={chunkerOperators}
                isCustomDropdown={isCustomDropdown}
                mousePosition={mousePosition}
                query={query}
              ></OperatorItemList>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      )}
    </>
  );
}
