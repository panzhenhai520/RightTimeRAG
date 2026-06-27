import { MessageType } from '@/constants/chat';
import {
  IMessage,
  IReferenceChunk,
  IReferenceObject,
  UploadResponseDataType,
} from '@/interfaces/database/chat';
import classNames from 'classnames';
import {
  Component,
  PropsWithChildren,
  ReactNode,
  memo,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { IRegenerateMessage, IRemoveMessageById } from '@/hooks/logic-hooks';
import { useFeatureFlags } from '@/hooks/use-feature-flags';
import { INodeEvent, MessageEventType } from '@/hooks/use-send-message';
import { cn } from '@/lib/utils';
import { AgentChatContext } from '@/pages/agent/context';
import { WorkFlowTimeline } from '@/pages/agent/log-sheet/workflow-timeline';
import {
  getThinkingPreview,
  parseRetrievingAndAnswer,
  parseThinkAndAnswer,
  stripProcessBlocks,
} from '@/utils/chat';
import { citationMarkerReg } from '@/utils/citation-utils';
import { getDirAttribute } from '@/utils/text-direction';
import { isEmpty } from 'lodash';
import {
  Atom,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  ClipboardList,
  FileSearch,
  Loader2,
  PenLine,
  SearchCheck,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { DocumentDownloadButton } from '../document-download-button';
import { GenerationTaskActions } from '../generation-task-actions';
import MarkdownContent from '../next-markdown-content';
import { RAGFlowAvatar } from '../ragflow-avatar';
import SvgIcon from '../svg-icon';
import { useTheme } from '../theme-provider';
import { Button } from '../ui/button';
import { EvidenceAuditPanel } from './evidence-audit-panel';
import { AssistantGroupButton, UserGroupButton } from './group-button';
import styles from './index.module.less';
import { ReferenceDocumentList } from './reference-document-list';
import { ReferenceImageList } from './reference-image-list';
import { UploadedMessageFiles } from './uploaded-message-files';

const toMessageText = (value: unknown): string => {
  if (typeof value === 'string') return value;
  if (value === undefined || value === null) return '';
  if (Array.isArray(value)) return value.map(toMessageText).join('');
  return String(value);
};

interface IProps
  extends Partial<IRemoveMessageById>, IRegenerateMessage, PropsWithChildren {
  item: IMessage;
  conversationId?: string;
  currentEventListWithoutMessageById?: (messageId: string) => INodeEvent[];
  setCurrentMessageId?: (messageId: string) => void;
  reference?: IReferenceObject;
  loading?: boolean;
  sendLoading?: boolean;
  visibleAvatar?: boolean;
  nickname?: string;
  avatar?: string;
  avatarDialog?: string | null;
  agentName?: string;
  ttsConfig?: Record<string, unknown>;
  clickDocumentButton?: (documentId: string, chunk: IReferenceChunk) => void;
  index: number;
  showLikeButton?: boolean;
  showLoudspeaker?: boolean;
  showLog?: boolean;
  isShare?: boolean;
  continueMessage?: (item: IMessage) => void;
}

class InlineRenderBoundary extends Component<
  {
    boundaryKey: string;
    children: ReactNode;
    fallback?: ReactNode;
  },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error) {
    console.error('Message section render failed', error);
  }

  componentDidUpdate(prevProps: { boundaryKey: string }) {
    if (
      this.state.hasError &&
      prevProps.boundaryKey !== this.props.boundaryKey
    ) {
      this.setState({ hasError: false });
    }
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? null;
    }
    return this.props.children;
  }
}

function MessageItem({
  item,
  conversationId,
  currentEventListWithoutMessageById,
  setCurrentMessageId,
  reference,
  loading = false,
  avatar,
  nickname,
  avatarDialog,
  agentName,
  ttsConfig,
  sendLoading = false,
  clickDocumentButton,
  removeMessageById,
  regenerateMessage,
  showLikeButton = true,
  showLoudspeaker = true,
  visibleAvatar = true,
  children,
  showLog,
  isShare,
  continueMessage,
}: IProps) {
  const { t } = useTranslation();
  const { theme } = useTheme();
  const { enabled } = useFeatureFlags();
  const evidenceAuditEnabled = enabled('evidenceAudit');
  const isAssistant = item.role === MessageType.Assistant;
  const isUser = item.role === MessageType.User;
  const [showThinking, setShowThinking] = useState(true);
  const [showRetrieving, setShowRetrieving] = useState(true);
  const [showReasoning, setShowReasoning] = useState(true);
  const { setLastSendLoadingFunc } = useContext(AgentChatContext);

  useEffect(() => {
    if (typeof setLastSendLoadingFunc === 'function') {
      setLastSendLoadingFunc(loading, item.id);
    }
  }, [loading, setLastSendLoadingFunc, item.id]);

  const referenceChunks = useMemo(
    () => Object.values(reference?.chunks ?? {}),
    [reference?.chunks],
  );
  const citedDocumentIds = useMemo(
    () =>
      new Set(
        referenceChunks.map((chunk) => chunk.document_id).filter(Boolean),
      ),
    [referenceChunks],
  );
  const referenceDocuments = useMemo(() => {
    const docs = reference?.doc_aggs ?? {};

    return Object.values(docs).filter((doc) =>
      citedDocumentIds.has(doc.doc_id),
    );
  }, [citedDocumentIds, reference?.doc_aggs]);
  const hasReferenceChunks = referenceChunks.length > 0;

  const documentDownloadInfos = useMemo(
    () => item.downloads ?? [],
    [item.downloads],
  );
  const messageContent = toMessageText(item.content);
  const parsedRetrievingContent = useMemo(
    () => parseRetrievingAndAnswer(messageContent),
    [messageContent],
  );
  const parsedContent = useMemo(
    () => parseThinkAndAnswer(parsedRetrievingContent.answer),
    [parsedRetrievingContent.answer],
  );
  const thinkingPreview = useMemo(
    () => getThinkingPreview(parsedContent.thinking, loading ? 6 : 2),
    [loading, parsedContent.thinking],
  );
  const retrievingPreview = useMemo(
    () => getThinkingPreview(parsedRetrievingContent.thinking, loading ? 6 : 2),
    [loading, parsedRetrievingContent.thinking],
  );
  const answerContent = stripProcessBlocks(parsedContent.answer);
  const shouldShowRetrieving =
    isAssistant && (loading || parsedRetrievingContent.hasThinking);
  const isRetrievingRunning =
    loading && !parsedRetrievingContent.thinkingComplete;
  const displayedRetrieving = loading
    ? retrievingPreview
    : showRetrieving
      ? parsedRetrievingContent.thinking
      : retrievingPreview;
  const displayedRetrievingLines = useMemo(
    () => displayedRetrieving.split(/\r?\n/).filter(Boolean),
    [displayedRetrieving],
  );
  const shouldShowRetrievingBody =
    !!parsedRetrievingContent.thinking && (loading || showRetrieving);
  const shouldShowThinking =
    isAssistant && (loading || parsedContent.hasThinking);
  const isThinkingRunning = loading;
  const shouldShowReasoningBody =
    !!parsedContent.thinking && (loading || showReasoning);
  const displayedReasoning = loading
    ? thinkingPreview
    : showReasoning
      ? parsedContent.thinking
      : thinkingPreview;
  const displayedReasoningLines = useMemo(
    () => displayedReasoning.split(/\r?\n/).filter(Boolean),
    [displayedReasoning],
  );
  const reasoningPanelTitle = isThinkingRunning
    ? t('chat.thinking')
    : t('chat.thought');
  const processStages = useMemo(() => {
    const hasRetrieval =
      loading || parsedRetrievingContent.hasThinking || hasReferenceChunks;
    const hasReasoning = parsedContent.hasThinking;
    const hasAnswer = !isEmpty(answerContent);
    const currentKey = hasAnswer
      ? 'compose'
      : hasReasoning
        ? 'reason'
        : hasRetrieval
          ? 'retrieve'
          : 'analyze';
    const stages = [
      {
        key: 'analyze',
        label: t('chat.processAnalyze'),
        visible: true,
        icon: ClipboardList,
      },
      {
        key: 'retrieve',
        label: t('chat.processRetrieve'),
        visible: loading || hasRetrieval,
        icon: FileSearch,
      },
      {
        key: 'reason',
        label: t('chat.processReason'),
        visible: loading || hasReasoning,
        icon: SearchCheck,
      },
      {
        key: 'compose',
        label: t('chat.processCompose'),
        visible: loading || hasAnswer,
        icon: PenLine,
      },
    ];
    const currentIndex = stages.findIndex((stage) => stage.key === currentKey);

    return stages
      .map((stage, index) => {
        const isCurrent = loading && stage.key === currentKey;
        return {
          ...stage,
          status: isCurrent
            ? t('chat.processInProgress')
            : !loading || index < currentIndex
              ? t('chat.processDone')
              : t('chat.processPending'),
          running: isCurrent,
          done: !loading || index < currentIndex,
        };
      })
      .filter((stage) => stage.visible);
  }, [
    answerContent,
    hasReferenceChunks,
    loading,
    parsedContent.hasThinking,
    parsedRetrievingContent.hasThinking,
    t,
  ]);

  const handleRegenerateMessage = useCallback(() => {
    regenerateMessage?.(item);
  }, [regenerateMessage, item]);

  useEffect(() => {
    if (typeof setCurrentMessageId === 'function') {
      setCurrentMessageId(item.id);
    }
  }, [item.id, setCurrentMessageId]);

  useEffect(() => {
    if (loading) {
      setShowRetrieving(true);
      setShowReasoning(true);
    }
  }, [loading]);

  const startedNodeList = useCallback(
    (item: IMessage) => {
      const finish = currentEventListWithoutMessageById?.(item.id)?.some(
        (item) => item.event === MessageEventType.WorkflowFinished,
      );
      return !finish && loading;
    },
    [currentEventListWithoutMessageById, loading],
  );

  const renderContent = useCallback(() => {
    const hasInteractiveData = item.data && !item.data.longTask;

    if (!answerContent && !(hasInteractiveData || (sendLoading && !isShare))) {
      return null;
    }

    return (
      <div
        className={cn({
          [theme === 'dark' ? styles.messageTextDark : styles.messageText]:
            isAssistant,
          [styles.messageUserText]: !isAssistant,
          'bg-bg-card': !isAssistant,
        })}
        dir={getDirAttribute(answerContent.replace(citationMarkerReg, ''))}
      >
        {hasInteractiveData ? (
          children
        ) : sendLoading && isEmpty(answerContent) ? (
          <>{!isShare && 'running...'}</>
        ) : (
          <InlineRenderBoundary
            boundaryKey={`${item.id}-answer-${answerContent.length}`}
            fallback={
              <div className="whitespace-pre-wrap text-sm leading-6 text-text-primary">
                {answerContent}
              </div>
            }
          >
            <MarkdownContent
              loading={loading}
              content={answerContent}
              reference={reference}
              clickDocumentButton={clickDocumentButton}
            ></MarkdownContent>
          </InlineRenderBoundary>
        )}
      </div>
    );
  }, [
    children,
    clickDocumentButton,
    answerContent,
    isAssistant,
    isShare,
    item.data,
    item.id,
    loading,
    reference,
    sendLoading,
    theme,
  ]);

  return (
    <div
      className={classNames(styles.messageItem, {
        [styles.messageItemLeft]: item.role === MessageType.Assistant,
        [styles.messageItemRight]: item.role === MessageType.User,
      })}
    >
      <section
        className={classNames(styles.messageItemSection, {
          [styles.messageItemSectionLeft]: item.role === MessageType.Assistant,
          [styles.messageItemSectionRight]: item.role === MessageType.User,
        })}
      >
        <div
          className={classNames(styles.messageItemContent, {
            [styles.messageItemContentReverse]: item.role === MessageType.User,
          })}
        >
          {visibleAvatar &&
            (item.role === MessageType.User ? (
              <RAGFlowAvatar
                className="size-20 shrink-0"
                avatar={avatar}
                name={nickname}
                isPerson
              />
            ) : avatarDialog || agentName ? (
              <RAGFlowAvatar
                className="size-20 shrink-0"
                avatar={avatarDialog as string}
                name={agentName}
                isPerson
              />
            ) : (
              <SvgIcon
                name={'assistant'}
                width={'100%'}
                className={cn('size-20 shrink-0 fill-current')}
              ></SvgIcon>
            ))}
          <section className="flex-col gap-2 flex-1">
            <div className="flex justify-between items-center">
              {isShare && isAssistant && (
                <Button
                  variant={'transparent'}
                  onClick={() => setShowThinking((think) => !think)}
                >
                  <div className="flex items-center gap-1">
                    <div className="">
                      <Atom
                        className={startedNodeList(item) ? 'animate-spin' : ''}
                      />
                    </div>
                    {t('chat.processTimeline')}
                    {showThinking ? <ChevronUp /> : <ChevronDown />}
                  </div>
                </Button>
              )}
              <div className="space-x-1">
                {isAssistant ? (
                  <>
                    {isShare && !sendLoading && !isEmpty(item.content) && (
                      <AssistantGroupButton
                        messageId={item.id}
                        content={answerContent}
                        prompt={item.prompt}
                        showLikeButton={showLikeButton}
                        audioBinary={item.audio_binary}
                        ttsConfig={ttsConfig}
                        showLoudspeaker={showLoudspeaker}
                        showLog={showLog}
                        attachment={item.attachment}
                        isShare={isShare}
                      ></AssistantGroupButton>
                    )}
                    {!isShare && (
                      <AssistantGroupButton
                        messageId={item.id}
                        content={answerContent}
                        prompt={item.prompt}
                        showLikeButton={showLikeButton}
                        audioBinary={item.audio_binary}
                        ttsConfig={ttsConfig}
                        showLoudspeaker={showLoudspeaker}
                        showLog={showLog}
                        attachment={item.attachment}
                      ></AssistantGroupButton>
                    )}
                  </>
                ) : (
                  <UserGroupButton
                    content={messageContent}
                    messageId={item.id}
                    removeMessageById={removeMessageById}
                    regenerateMessage={
                      regenerateMessage && handleRegenerateMessage
                    }
                    sendLoading={sendLoading}
                  ></UserGroupButton>
                )}
              </div>
            </div>

            {isAssistant &&
              currentEventListWithoutMessageById &&
              showThinking && (
                <div className="mt-4 mb-4">
                  <WorkFlowTimeline
                    currentEventListWithoutMessage={currentEventListWithoutMessageById(
                      item.id,
                    )}
                    isShare={isShare}
                    currentMessageId={item.id}
                    canvasId={conversationId}
                    sendLoading={loading}
                  />
                </div>
              )}

            {shouldShowRetrieving && (
              <div className={styles.thinkingPanel}>
                <button
                  type="button"
                  className={styles.thinkingHeader}
                  onClick={() => setShowRetrieving((visible) => !visible)}
                >
                  {isRetrievingRunning ? (
                    <Loader2
                      className={cn(styles.thinkingIcon, 'animate-spin')}
                    />
                  ) : (
                    <CheckCircle2 className={styles.thinkingIcon} />
                  )}
                  <span
                    className={cn({
                      [styles.thinkingHeaderRunning]: isRetrievingRunning,
                    })}
                  >
                    {isRetrievingRunning
                      ? t('chat.retrieving')
                      : t('chat.retrieved')}
                  </span>
                  {parsedRetrievingContent.thinking &&
                    (showRetrieving ? (
                      <ChevronUp className={styles.thinkingChevron} />
                    ) : (
                      <ChevronDown className={styles.thinkingChevron} />
                    ))}
                </button>
                {shouldShowRetrievingBody && (
                  <div
                    className={cn(styles.thinkingText, {
                      [styles.thinkingTextRunning]: isRetrievingRunning,
                    })}
                  >
                    {displayedRetrievingLines.length > 0 ? (
                      <div className={styles.reasoningLineList}>
                        {displayedRetrievingLines.map((line, lineIndex) => (
                          <div
                            key={`${lineIndex}-${line}`}
                            className={cn(styles.reasoningLine, {
                              [styles.reasoningLineStreaming]:
                                isRetrievingRunning &&
                                lineIndex ===
                                  displayedRetrievingLines.length - 1,
                            })}
                          >
                            {line}
                          </div>
                        ))}
                      </div>
                    ) : (
                      displayedRetrieving
                    )}
                  </div>
                )}
              </div>
            )}

            {shouldShowThinking && (
              <div className={styles.thinkingPanel}>
                <button
                  type="button"
                  className={styles.thinkingHeader}
                  onClick={() => setShowReasoning((visible) => !visible)}
                >
                  {isThinkingRunning ? (
                    <Loader2
                      className={cn(styles.thinkingIcon, 'animate-spin')}
                    />
                  ) : (
                    <CheckCircle2 className={styles.thinkingIcon} />
                  )}
                  <span
                    className={cn({
                      [styles.thinkingHeaderRunning]: isThinkingRunning,
                    })}
                  >
                    {reasoningPanelTitle}
                  </span>
                  {parsedContent.thinking &&
                    (showReasoning ? (
                      <ChevronUp className={styles.thinkingChevron} />
                    ) : (
                      <ChevronDown className={styles.thinkingChevron} />
                    ))}
                </button>
                {shouldShowReasoningBody && (
                  <div className={styles.thinkingText}>
                    {loading && (
                      <ol className={styles.processStageList}>
                        {processStages.map((stage) => {
                          const StageIcon = stage.icon;

                          return (
                            <li
                              key={stage.key}
                              className={cn(styles.processStage, {
                                [styles.processStageRunning]: stage.running,
                                [styles.processStageDone]: stage.done,
                              })}
                            >
                              <span className={styles.processStageIcon}>
                                {stage.running ? (
                                  <Loader2 className="animate-spin" />
                                ) : (
                                  <StageIcon />
                                )}
                              </span>
                              <span className={styles.processStageLabel}>
                                {stage.label}
                              </span>
                              <span className={styles.processStageStatus}>
                                {stage.status}
                              </span>
                            </li>
                          );
                        })}
                      </ol>
                    )}
                    {displayedReasoningLines.length > 0 && (
                      <div className={styles.reasoningLineList}>
                        {displayedReasoningLines.map((line, lineIndex) => (
                          <div
                            key={`${lineIndex}-${line}`}
                            className={cn(styles.reasoningLine, {
                              [styles.reasoningLineStreaming]:
                                loading &&
                                lineIndex ===
                                  displayedReasoningLines.length - 1,
                            })}
                          >
                            {line}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {renderContent()}

            {isAssistant &&
              evidenceAuditEnabled &&
              reference?.evidence_audit && (
                <InlineRenderBoundary
                  boundaryKey={`${item.id}-evidence-audit-${answerContent.length}`}
                >
                  <EvidenceAuditPanel
                    audit={reference.evidence_audit}
                  ></EvidenceAuditPanel>
                </InlineRenderBoundary>
              )}

            {isAssistant && hasReferenceChunks && (
              <InlineRenderBoundary
                boundaryKey={`${item.id}-reference-images-${answerContent.length}`}
              >
                <ReferenceImageList
                  referenceChunks={reference?.chunks}
                  messageContent={answerContent}
                ></ReferenceImageList>
              </InlineRenderBoundary>
            )}

            {isAssistant &&
              hasReferenceChunks &&
              referenceDocuments.length > 0 && (
                <InlineRenderBoundary
                  boundaryKey={`${item.id}-reference-docs-${referenceDocuments.length}`}
                >
                  <ReferenceDocumentList
                    list={referenceDocuments}
                  ></ReferenceDocumentList>
                </InlineRenderBoundary>
              )}

            {isUser && (
              <UploadedMessageFiles
                files={item.files as File[] | UploadResponseDataType[]}
              ></UploadedMessageFiles>
            )}
            {documentDownloadInfos.length > 0 && (
              <div className="mt-3 space-y-3">
                {documentDownloadInfos.map((downloadInfo, index) => (
                  <div key={`${downloadInfo.filename}-${index}`}>
                    {index > 0 && <div className="my-6 h-px bg-border" />}
                    <DocumentDownloadButton downloadInfo={downloadInfo} />
                  </div>
                ))}
              </div>
            )}
            {isAssistant && (
              <GenerationTaskActions
                item={item}
                loading={loading}
                onContinue={continueMessage}
              />
            )}
            {/* {isAssistant && item.attachment && item.attachment.doc_id && (
              <div className="w-full flex items-center justify-end">
                <Button
                  variant="link"
                  className="p-1 m-0 h-auto text-text-sub-title-invert"
                  onClick={async () => {
                    if (item.attachment?.doc_id) {
                      try {
                        const response = await downloadFile({
                          docId: item.attachment.doc_id,
                          ext: item.attachment.format,
                        });
                        const blob = new Blob([response.data], {
                          type: response.data.type,
                        });
                        downloadFileFromBlob(blob, item.attachment.file_name);
                      } catch (error) {
                        console.error('Download failed:', error);
                      }
                    }
                  }}
                >
                  <Download size={16} />
                </Button>
              </div>
            )} */}
          </section>
        </div>
      </section>
    </div>
  );
}

export default memo(MessageItem);
