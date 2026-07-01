import { FileUploadProps } from '@/components/file-upload';
import { NextMessageInput } from '@/components/message-input/next';
import MessageItem from '@/components/next-message-item';
import PdfSheet from '@/components/pdf-drawer';
import { useClickDrawer } from '@/components/pdf-drawer/hooks';
import message from '@/components/ui/message';
import { MessageType } from '@/constants/chat';
import { useUploadAgentFileWithProgress } from '@/hooks/use-agent-request';
import { useFetchUserInfo } from '@/hooks/use-user-setting-request';
import {
  IAgentLogResponse,
  IAgentValidationIssue,
  IAgentValidationResponse,
} from '@/interfaces/database/agent';
import { IMessage } from '@/interfaces/database/chat';
import { BeginQueryType } from '@/pages/agent/constant';
import { BeginQuery } from '@/pages/agent/interface';
import { getNodeGuide, getNodeGuideCategory } from '@/pages/agent/node-guide';
import { ParameterDialog } from '@/pages/agent/share/parameter-dialog';
import { validateAgentDsl } from '@/services/agent-service';
import { buildMessageUuidWithRole } from '@/utils/chat';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FileInput,
  FileOutput,
  ListChecks,
  Loader2,
  SearchCheck,
  Workflow,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useExploreUrlParams } from '../hooks/use-explore-url-params';
import { useSendSessionMessage } from '../hooks/use-send-session-message';
import { useExploreRunContext } from '../run-context';

interface SessionChatProps {
  session?: IAgentLogResponse;
}

type AgentRunGuide = {
  title: string;
  prologue?: string;
  requiredInputs: string[];
  optionalInputs: string[];
  stages: Array<{
    id: string;
    title: string;
    description: string;
    category: string;
    external?: boolean;
  }>;
  outputs: string[];
  placeholder: string;
  warnings: string[];
  summary: string;
  hasVisibleOutput: boolean;
};

const InputTypeLabel: Record<string, string> = {
  [BeginQueryType.Line]: '短文本',
  [BeginQueryType.Paragraph]: '长文本',
  [BeginQueryType.Options]: '选项',
  [BeginQueryType.File]: '文件',
  [BeginQueryType.Integer]: '数字',
  [BeginQueryType.Boolean]: '是/否',
};

function unique(items: string[]) {
  return Array.from(new Set(items.filter(Boolean)));
}

function readBeginForm(canvasInfo: any) {
  const graphNodes = canvasInfo?.dsl?.graph?.nodes || [];
  const beginNode = graphNodes.find((node: any) => node.id === 'begin');
  const graphForm = beginNode?.data?.form;
  const componentForm =
    canvasInfo?.dsl?.components?.begin?.obj?.params ||
    canvasInfo?.dsl?.components?.Begin?.obj?.params;
  return graphForm || componentForm || {};
}

function formatInput(input: BeginQuery) {
  const type = InputTypeLabel[input.type] || input.type || '输入';
  return `${input.name || input.key}（${type}）`;
}

type WorkflowNode = {
  id: string;
  operator: string;
  name: string;
};

const VisibleOutputLabels: Record<string, string> = {
  Message: '聊天窗口显示 Message 节点内容',
  VoiceReplyOutput: '语音回复结果',
  DocGenerator: '可下载文档',
  ExcelProcessor: '表格或 Excel 结果',
  ChartRenderer: '图表结果',
  ArtifactPackager: '产物包或附件清单',
  WorkspaceFileWrite: '写入智能体工作区文件',
  WorkspacePatchApply: 'patch 预演、应用结果和审计记录',
  Email: '邮件发送结果',
};

const VisibleOutputOperators = new Set(Object.keys(VisibleOutputLabels));

function readWorkflowNodes(canvasInfo: any): WorkflowNode[] {
  const graphNodes = canvasInfo?.dsl?.graph?.nodes || [];
  const components = canvasInfo?.dsl?.components || {};

  if (Array.isArray(graphNodes) && graphNodes.length > 0) {
    return graphNodes.map((node: any) => {
      const component = components[node.id];
      const operator =
        node?.data?.label ||
        component?.obj?.component_name ||
        node?.data?.name ||
        node.id;
      return {
        id: node.id,
        operator,
        name: node?.data?.name || operator,
      };
    });
  }

  return Object.entries(components).map(([id, component]: [string, any]) => {
    const operator = component?.obj?.component_name || id;
    return { id, operator, name: operator };
  });
}

function readWorkflowEdges(canvasInfo: any) {
  const graphEdges = canvasInfo?.dsl?.graph?.edges || [];
  if (Array.isArray(graphEdges) && graphEdges.length > 0) {
    return graphEdges
      .map((edge: any) => ({
        source: edge.source,
        target: edge.target,
      }))
      .filter((edge: any) => edge.source && edge.target);
  }

  const components = canvasInfo?.dsl?.components || {};
  return Object.entries(components).flatMap(([id, component]: [string, any]) =>
    (component?.downstream || []).map((target: string) => ({
      source: id,
      target,
    })),
  );
}

function buildReachableNodes(nodes: WorkflowNode[], edges: any[]) {
  const nodeMap = new Map(nodes.map((node) => [node.id, node]));
  const beginNode =
    nodes.find((node) => node.id === 'begin') ||
    nodes.find((node) => node.operator === 'Begin');
  if (!beginNode) {
    return nodes;
  }

  const downstream = edges.reduce<Record<string, string[]>>((acc, edge) => {
    acc[edge.source] = [...(acc[edge.source] || []), edge.target];
    return acc;
  }, {});
  const visited = new Set<string>();
  const ordered: WorkflowNode[] = [];
  const queue = [beginNode.id];

  while (queue.length > 0) {
    const id = queue.shift();
    if (!id || visited.has(id)) {
      continue;
    }
    visited.add(id);
    const node = nodeMap.get(id);
    if (node) {
      ordered.push(node);
    }
    (downstream[id] || []).forEach((target) => {
      if (!visited.has(target)) {
        queue.push(target);
      }
    });
  }

  return ordered;
}

function buildOutputs(nodes: WorkflowNode[]) {
  return unique(
    nodes
      .map((node) => VisibleOutputLabels[node.operator])
      .filter(Boolean),
  );
}

function buildStageList(nodes: WorkflowNode[]) {
  const seen = new Set<string>();
  return nodes
    .filter((node) => node.operator !== 'Begin')
    .filter((node) => {
      if (seen.has(node.operator)) {
        return false;
      }
      seen.add(node.operator);
      return true;
    })
    .map((node) => {
      const guide = getNodeGuide(node.operator);
      const category = getNodeGuideCategory(guide.category);
      return {
        id: node.id,
        title: guide.title,
        description: guide.description,
        category: category.title,
        external: guide.external,
      };
    });
}

function buildLocalWorkflowWarnings(
  allNodes: WorkflowNode[],
  reachableNodes: WorkflowNode[],
  edges: any[],
  beginInputs: BeginQuery[],
) {
  const warnings: string[] = [];
  const reachableIds = new Set(reachableNodes.map((node) => node.id));
  const nonBeginReachable = reachableNodes.filter(
    (node) => node.operator !== 'Begin',
  );
  const downstreamMap = edges.reduce<Record<string, string[]>>((acc, edge) => {
    acc[edge.source] = [...(acc[edge.source] || []), edge.target];
    return acc;
  }, {});
  const disconnected = allNodes.filter(
    (node) => node.operator !== 'Begin' && !reachableIds.has(node.id),
  );
  const terminalWithoutOutput = nonBeginReachable.filter(
    (node) =>
      !VisibleOutputOperators.has(node.operator) &&
      (downstreamMap[node.id] || []).length === 0,
  );
  const hasAudioProcessing = nonBeginReachable.some((node) =>
    ['AudioInput', 'ASRTranscribe', 'TTSGenerate'].includes(node.operator),
  );
  const hasFileLikeInput = beginInputs.some(
    (input) => input.type === BeginQueryType.File,
  );

  if (nonBeginReachable.length === 0) {
    warnings.push('当前流程只有开始节点，还没有配置处理节点或输出节点。');
  }

  if (!nonBeginReachable.some((node) => VisibleOutputOperators.has(node.operator))) {
    warnings.push(
      '未检测到 Message、VoiceReplyOutput、DocGenerator、WorkspaceFileWrite 等可见输出节点，运行后可能没有用户可见结果。',
    );
  }

  if (terminalWithoutOutput.length > 0) {
    warnings.push(
      `以下节点没有下游输出：${terminalWithoutOutput
        .map((node) => getNodeGuide(node.operator).title)
        .join('、')}。`,
    );
  }

  if (disconnected.length > 0) {
    warnings.push(
      `有 ${disconnected.length} 个节点未连到 Begin 主流程，运行时可能不会执行。`,
    );
  }

  if (hasAudioProcessing && !hasFileLikeInput) {
    warnings.push(
      '流程包含语音节点，但 Begin 未配置文件/音频类输入；请确认音频来源已经通过变量或上传文件接入。',
    );
  }

  return unique(warnings);
}

function buildAgentRunGuide(
  canvasInfo: any,
  beginInputs: BeginQuery[],
): AgentRunGuide {
  const beginForm = readBeginForm(canvasInfo);
  const allNodes = readWorkflowNodes(canvasInfo);
  const edges = readWorkflowEdges(canvasInfo);
  const reachableNodes = buildReachableNodes(allNodes, edges);
  const reachableOperators = reachableNodes.map((node) => node.operator);
  const componentSet = new Set(reachableOperators);
  const requiredInputs = beginInputs
    .filter((input) => !input.optional)
    .map(formatInput);
  const optionalInputs = beginInputs
    .filter((input) => input.optional)
    .map(formatInput);
  const stages = buildStageList(reachableNodes);
  const outputs = buildOutputs(reachableNodes);
  const warnings = buildLocalWorkflowWarnings(
    allNodes,
    reachableNodes,
    edges,
    beginInputs,
  );
  const hasFileInput =
    beginInputs.some((input) => input.type === BeginQueryType.File) ||
    ['FileParser', 'DocumentNormalizer', 'WorkspaceFileRead'].some((name) =>
      componentSet.has(name),
    );
  const hasAudioInput = ['AudioInput', 'ASRTranscribe', 'TTSGenerate'].some(
    (name) => componentSet.has(name),
  );
  const inputNames = beginInputs
    .slice(0, 4)
    .map((input) => input.name || input.key)
    .join('、');
  const fileHint = hasFileInput
    ? '；有文件时可点击回形针上传或填写文件路径'
    : '';
  const placeholder = inputNames
    ? `请按参数表单填写：${inputNames}${fileHint}。`
    : hasAudioInput
      ? '请上传或选择音频文件，并确认语音节点的音频变量来源。'
      : `请在下方输入要交给流程的文字内容${fileHint}。`;
  const hasVisibleOutput = outputs.length > 0;
  const stageNames = stages
    .slice(0, 4)
    .map((stage) => stage.title)
    .join('、');
  const summary =
    stages.length === 0
      ? '当前流程还没有配置可执行的处理节点。'
      : hasVisibleOutput
        ? `当前流程会按连线依次执行：${stageNames}。`
        : `当前流程会执行：${stageNames}，但还没有配置可见输出节点。`;

  return {
    title: `${canvasInfo?.title || '这个智能体'}怎么用`,
    prologue: beginForm?.enablePrologue ? beginForm?.prologue : undefined,
    requiredInputs,
    optionalInputs,
    stages: stages.slice(0, 5),
    outputs,
    placeholder,
    warnings,
    summary,
    hasVisibleOutput,
  };
}

function AgentRunGuidePanel({
  guide,
  onValidate,
  validating,
  validation,
}: {
  guide: AgentRunGuide;
  onValidate?: () => void;
  validating?: boolean;
  validation?: IAgentValidationResponse;
}) {
  const validationIssues: IAgentValidationIssue[] =
    validation?.issues || [...(validation?.errors || []), ...(validation?.warnings || [])];

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-4 rounded-lg border border-border-default bg-white p-5 text-[#132330] shadow-sm dark:border-[#9fd0ea]/24 dark:bg-[#102636] dark:text-[#edf7fb]">
      <div className="flex items-start justify-between gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-[#8b4c36]/10 text-[#6f3f2f] dark:bg-[#dceef8]/10 dark:text-[#d6eefb]">
          <Workflow className="size-5" />
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold">{guide.title}</h2>
          <p className="mt-1 text-sm leading-6 text-text-secondary">
            {guide.prologue || guide.summary}
          </p>
        </div>
        {onValidate && (
          <button
            type="button"
            onClick={onValidate}
            disabled={validating}
            className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-border-default px-3 text-xs font-medium text-text-primary hover:bg-background-card disabled:cursor-not-allowed disabled:opacity-60"
          >
            {validating ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <SearchCheck className="size-3.5" />
            )}
            检测流程
          </button>
        )}
      </div>

      {guide.warnings.length > 0 && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm leading-6 text-amber-900 dark:border-amber-300/30 dark:bg-amber-300/10 dark:text-amber-100">
          <div className="mb-1 flex items-center gap-2 font-medium">
            <AlertTriangle className="size-4" />
            流程可能不完整
          </div>
          <ul className="space-y-1">
            {guide.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      {validation && (
        <div className="rounded-md border border-border-default bg-[#f7fafc] px-3 py-2 text-sm leading-6 text-text-secondary dark:border-[#9fd0ea]/20 dark:bg-[#dceef8]/8">
          {validation.ok && validationIssues.length === 0 ? (
            <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-200">
              <CheckCircle2 className="size-4" />
              后端校验通过，流程结构可以执行。
            </div>
          ) : (
            <>
              <div className="mb-1 font-medium text-text-primary">
                检测结果
              </div>
              <ul className="space-y-1">
                {validationIssues.slice(0, 6).map((issue, index) => (
                  <li key={`${issue.code}-${issue.component_id}-${index}`}>
                    {issue.severity === 'error' ? '错误' : '建议'}：
                    {issue.component_name ? `${issue.component_name} - ` : ''}
                    {issue.message}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      <div className="grid gap-4 border-t border-border-default pt-4 md:grid-cols-3">
        <div>
          <div className="mb-2 flex items-center gap-2 text-sm font-medium">
            <FileInput className="size-4" />
            需要你提供
          </div>
          <ul className="space-y-1 text-sm leading-6 text-text-secondary">
            {(guide.requiredInputs.length > 0
              ? guide.requiredInputs
              : ['聊天输入框文字内容']
            ).map((item) => (
              <li key={item}>必填：{item}</li>
            ))}
            {guide.optionalInputs.slice(0, 3).map((item) => (
              <li key={item}>可选：{item}</li>
            ))}
          </ul>
        </div>

        <div>
          <div className="mb-2 flex items-center gap-2 text-sm font-medium">
            <ListChecks className="size-4" />
            中间会加工
          </div>
          <ul className="space-y-1 text-sm leading-6 text-text-secondary">
            {guide.stages.length > 0 ? (
              guide.stages.slice(0, 5).map((item) => (
                <li className="flex gap-2" key={item.id}>
                  <ArrowRight className="mt-1 size-3.5 shrink-0" />
                  <span>
                    <span className="font-medium text-text-primary">
                      {item.title}
                    </span>
                    <span className="ml-1 text-xs text-text-secondary">
                      {item.category}
                      {item.external ? ' · 外部服务' : ''}
                    </span>
                    <span className="block text-xs leading-5">
                      {item.description}
                    </span>
                  </span>
                </li>
              ))
            ) : (
              <li>还没有配置处理节点</li>
            )}
          </ul>
        </div>

        <div>
          <div className="mb-2 flex items-center gap-2 text-sm font-medium">
            <FileOutput className="size-4" />
            最后会输出
          </div>
          <ul className="space-y-1 text-sm leading-6 text-text-secondary">
            {guide.outputs.length > 0 ? (
              guide.outputs.map((item) => <li key={item}>{item}</li>)
            ) : (
              <li className="text-amber-700 dark:text-amber-200">
                未配置可见输出节点
              </li>
            )}
          </ul>
        </div>
      </div>
    </div>
  );
}

export function SessionChat({ session }: SessionChatProps) {
  const { data: userInfo } = useFetchUserInfo();
  const { canvasId, sessionId, isNew } = useExploreUrlParams();
  const hasLocalMessageRef = useRef(false);
  const [validation, setValidation] = useState<IAgentValidationResponse>();
  const [validating, setValidating] = useState(false);
  const { getSessionRunId } = useExploreRunContext();
  const recoveredRunId = getSessionRunId(sessionId);

  const sessionLoading = false;

  const {
    value,
    derivedMessages,
    scrollRef,
    messageContainerRef,
    sendLoading,
    backgroundSendLoading,
    handleInputChange,
    handlePressEnter,
    stopOutputMessage,
    canvasInfo,
    findReferenceByMessageId,
    appendUploadResponseList,
    removeFile,
    parameterDialogVisible,
    handleParametersOk,
    beginInputs,
    shouldShowParameterDialog,
    setDerivedMessages,
  } = useSendSessionMessage({ recoveredRunId });
  const runGuide = useMemo(
    () => buildAgentRunGuide(canvasInfo, beginInputs),
    [beginInputs, canvasInfo],
  );
  const handleValidateFlow = useCallback(async () => {
    if (!canvasId) {
      message.error('缺少智能体 ID，无法检测流程。');
      return;
    }
    setValidating(true);
    try {
      const ret = await validateAgentDsl(canvasId, canvasInfo?.dsl);
      setValidation(ret.data.data);
    } catch (error) {
      message.error(
        error instanceof Error ? error.message : '流程检测失败，请稍后再试。',
      );
    } finally {
      setValidating(false);
    }
  }, [canvasId, canvasInfo?.dsl]);
  const hasActiveSession = Boolean(
    sessionId || isNew || hasLocalMessageRef.current,
  );

  const { visible, hideModal, documentId, selectedChunk, clickDocumentButton } =
    useClickDrawer();

  // File upload
  const { uploadAgentFile, loading: isUploading } =
    useUploadAgentFileWithProgress();

  const handleUploadFile: NonNullable<FileUploadProps['onUpload']> =
    useCallback(
      async (files, options) => {
        const ret = await uploadAgentFile({ files, options });
        appendUploadResponseList(ret.data, files);
      },
      [appendUploadResponseList, uploadAgentFile],
    );

  useEffect(() => {
    shouldShowParameterDialog();
  }, [shouldShowParameterDialog]);

  useEffect(() => {
    hasLocalMessageRef.current = false;
  }, [sessionId, isNew]);

  useEffect(() => {
    if (hasLocalMessageRef.current) {
      return;
    }
    if (sessionId && session?.id === sessionId && session?.message) {
      const messages = session.message;
      setDerivedMessages(messages as IMessage[]);
    }
  }, [session?.id, session?.message, sessionId, setDerivedMessages]);

  useEffect(() => {
    if (!sessionId && !isNew && !hasLocalMessageRef.current && !sendLoading) {
      setDerivedMessages([]);
    }
  }, [sessionId, isNew, sendLoading, setDerivedMessages]);

  const handleSessionPressEnter = useCallback(async () => {
    if (value.trim()) {
      hasLocalMessageRef.current = true;
    }
    return handlePressEnter();
  }, [handlePressEnter, value]);

  return (
    <>
      <section className="flex flex-col h-full">
        {!hasActiveSession && (
          <div className="flex-1 flex items-center justify-center p-5">
            <AgentRunGuidePanel
              guide={runGuide}
              onValidate={handleValidateFlow}
              validating={validating}
              validation={validation}
            />
          </div>
        )}

        {hasActiveSession && (
          <div
            ref={messageContainerRef}
            className="flex-1 overflow-auto min-h-0 p-5"
          >
            {sessionLoading ? (
              <div className="flex items-center justify-center h-full">
                Loading...
              </div>
            ) : derivedMessages.length === 0 ? (
              <div className="flex min-h-full items-center justify-center">
                <AgentRunGuidePanel
                  guide={runGuide}
                  onValidate={handleValidateFlow}
                  validating={validating}
                  validation={validation}
                />
              </div>
            ) : (
              <div className="w-full pr-5">
                {derivedMessages.map((message, i) => (
                  <MessageItem
                    loading={
                      message.role === MessageType.Assistant &&
                      sendLoading &&
                      derivedMessages.length - 1 === i
                    }
                    key={buildMessageUuidWithRole(message)}
                    item={message}
                    nickname={userInfo.nickname}
                    avatar={userInfo.avatar}
                    avatarDialog={canvasInfo?.avatar || ''}
                    agentName={canvasInfo?.title}
                    reference={findReferenceByMessageId(message.id)}
                    clickDocumentButton={clickDocumentButton}
                    index={i}
                    showLikeButton={false}
                    sendLoading={sendLoading}
                    showLog={false}
                  />
                ))}
              </div>
            )}
            <div ref={scrollRef} />
          </div>
        )}
        <section className="p-4">
          <div className="mb-3 rounded-md border border-border-default bg-[#f7fafc] px-3 py-2 text-sm leading-6 text-text-secondary dark:border-[#9fd0ea]/20 dark:bg-[#dceef8]/8">
            <span className="font-medium text-[#132330] dark:text-[#edf7fb]">
              输入提示：
            </span>
            <span className="ml-1">{runGuide.placeholder}</span>
          </div>
          <NextMessageInput
            value={value}
            placeholder={runGuide.placeholder}
            sendLoading={sendLoading}
            disabled={false}
            sendDisabled={sendLoading || backgroundSendLoading}
            isUploading={isUploading}
            onPressEnter={handleSessionPressEnter}
            onInputChange={handleInputChange}
            stopOutputMessage={stopOutputMessage}
            onUpload={handleUploadFile}
            removeFile={removeFile}
            conversationId=""
          />
        </section>
      </section>

      {parameterDialogVisible && beginInputs.length > 0 && (
        <ParameterDialog
          ok={handleParametersOk}
          agentId={canvasId}
          data={beginInputs.reduce(
            (acc, item) => {
              const { key, ...rest } = item;
              acc[key] = rest;
              return acc;
            },
            {} as Record<string, Omit<BeginQuery, 'key'>>,
          )}
        />
      )}

      {visible && (
        <PdfSheet
          visible={visible}
          hideModal={hideModal}
          documentId={documentId}
          chunk={selectedChunk}
        />
      )}
    </>
  );
}
