import { MessageType } from '@/constants/chat';
import {
  IMessage,
  IReference,
  IReferenceChunk,
  UploadResponseDataType,
} from '@/interfaces/database/chat';
import classNames from 'classnames';
import {
  Component,
  memo,
  ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { IRegenerateMessage, IRemoveMessageById } from '@/hooks/logic-hooks';
import { useFeatureFlags } from '@/hooks/use-feature-flags';
import { cn } from '@/lib/utils';
import {
  getThinkingPreview,
  parseRetrievingAndAnswer,
  parseThinkAndAnswer,
  stripProcessBlocks,
} from '@/utils/chat';
import { CheckCircle2, ChevronDown, ChevronUp, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { DocumentDownloadButton } from '../document-download-button';
import { GenerationTaskActions } from '../generation-task-actions';
import MarkdownContent from '../markdown-content';
import { EvidenceAuditPanel } from '../next-message-item/evidence-audit-panel';
import { ReferenceDocumentList } from '../next-message-item/reference-document-list';
import { ReferenceImageList } from '../next-message-item/reference-image-list';
import { UploadedMessageFiles } from '../next-message-item/uploaded-message-files';
import { RAGFlowAvatar } from '../ragflow-avatar';
import SvgIcon from '../svg-icon';
import { useTheme } from '../theme-provider';
import { AssistantGroupButton, UserGroupButton } from './group-button';
import styles from './index.module.less';

interface IProps extends Partial<IRemoveMessageById>, IRegenerateMessage {
  item: IMessage;
  reference: IReference;
  loading?: boolean;
  sendLoading?: boolean;
  visibleAvatar?: boolean;
  nickname?: string;
  avatar?: string;
  avatarDialog?: string | null;
  ttsConfig?: Record<string, unknown>;
  clickDocumentButton?: (documentId: string, chunk: IReferenceChunk) => void;
  index: number;
  showLikeButton?: boolean;
  showLoudspeaker?: boolean;
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

const MessageItem = ({
  item,
  reference,
  loading = false,
  avatar,
  nickname,
  avatarDialog,
  ttsConfig,
  sendLoading = false,
  clickDocumentButton,
  index,
  removeMessageById,
  regenerateMessage,
  showLikeButton = true,
  showLoudspeaker = true,
  visibleAvatar = true,
  continueMessage,
}: IProps) => {
  const { t } = useTranslation();
  const { theme } = useTheme();
  const { enabled } = useFeatureFlags();
  const evidenceAuditEnabled = enabled('evidenceAudit');
  const isAssistant = item.role === MessageType.Assistant;
  const isUser = item.role === MessageType.User;
  const [showThinking, setShowThinking] = useState(true);
  const [showRetrieving, setShowRetrieving] = useState(true);

  const uploadedFiles = useMemo(() => {
    return item?.files ?? [];
  }, [item?.files]);

  const referenceChunks = useMemo(
    () => reference?.chunks ?? [],
    [reference?.chunks],
  );
  const citedDocumentIds = useMemo(
    () =>
      new Set(
        referenceChunks.map((chunk) => chunk.document_id).filter(Boolean),
      ),
    [referenceChunks],
  );
  const referenceDocumentList = useMemo(() => {
    const docAggs = reference?.doc_aggs ?? [];
    // When no chunks carry a document_id (e.g. KG or web-search chunks that
    // lack a KB doc_id), fall back to showing every retrieved document rather
    // than hiding the panel entirely.
    if (citedDocumentIds.size === 0) return docAggs;
    return docAggs.filter((doc) => citedDocumentIds.has(doc.doc_id));
  }, [citedDocumentIds, reference?.doc_aggs]);
  const hasReferenceChunks = referenceChunks.length > 0;

  const documentDownloadInfos = useMemo(
    () => item.downloads ?? [],
    [item.downloads],
  );
  const messageContent =
    typeof item.content === 'string'
      ? item.content
      : String(item.content ?? '');
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
  const isRetrievingRunning = loading;
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
  const displayedThinking = loading
    ? thinkingPreview
    : showThinking
      ? parsedContent.thinking
      : thinkingPreview;
  const displayedThinkingLines = useMemo(
    () => displayedThinking.split(/\r?\n/).filter(Boolean),
    [displayedThinking],
  );
  const shouldShowThinkingBody =
    !!parsedContent.thinking && (loading || showThinking);

  useEffect(() => {
    if (loading) {
      setShowThinking(true);
      setShowRetrieving(true);
    }
  }, [loading]);

  const handleRegenerateMessage = useCallback(() => {
    regenerateMessage?.(item);
  }, [regenerateMessage, item]);

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
          className={classNames(styles.messageItemContent, 'group', {
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
            ) : avatarDialog ? (
              <RAGFlowAvatar
                className="size-20 shrink-0"
                avatar={avatarDialog}
                isPerson
              />
            ) : (
              <SvgIcon
                name={'assistant'}
                width={'100%'}
                className={cn('size-20 shrink-0 fill-current')}
              ></SvgIcon>
            ))}

          <section className="flex min-w-0 gap-2 flex-1 flex-col">
            {isAssistant ? (
              index !== 0 && (
                <AssistantGroupButton
                  messageId={item.id}
                  content={answerContent}
                  prompt={item.prompt}
                  showLikeButton={showLikeButton}
                  audioBinary={item.audio_binary}
                  ttsConfig={ttsConfig}
                  showLoudspeaker={showLoudspeaker}
                ></AssistantGroupButton>
              )
            ) : (
              <UserGroupButton
                content={messageContent}
                messageId={item.id}
                removeMessageById={removeMessageById}
                regenerateMessage={regenerateMessage && handleRegenerateMessage}
                sendLoading={sendLoading}
              ></UserGroupButton>
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
                  onClick={() => setShowThinking((visible) => !visible)}
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
                    {isThinkingRunning ? t('chat.thinking') : t('chat.thought')}
                  </span>
                  {parsedContent.thinking &&
                    (showThinking ? (
                      <ChevronUp className={styles.thinkingChevron} />
                    ) : (
                      <ChevronDown className={styles.thinkingChevron} />
                    ))}
                </button>
                {shouldShowThinkingBody && (
                  <div
                    className={cn(styles.thinkingText, {
                      [styles.thinkingTextRunning]: isThinkingRunning,
                    })}
                  >
                    {displayedThinkingLines.length > 0 ? (
                      <div className={styles.reasoningLineList}>
                        {displayedThinkingLines.map((line, lineIndex) => (
                          <div
                            key={`${lineIndex}-${line}`}
                            className={cn(styles.reasoningLine, {
                              [styles.reasoningLineStreaming]:
                                isThinkingRunning &&
                                lineIndex === displayedThinkingLines.length - 1,
                            })}
                          >
                            {line}
                          </div>
                        ))}
                      </div>
                    ) : (
                      displayedThinking
                    )}
                  </div>
                )}
              </div>
            )}
            {/* Show message content if there's any text besides the download */}
            {answerContent && (
              <div
                className={cn(
                  isAssistant
                    ? theme === 'dark'
                      ? styles.messageTextDark
                      : styles.messageText
                    : styles.messageUserText,
                  { '!bg-bg-card': !isAssistant },
                )}
              >
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
              </div>
            )}
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
                  referenceChunks={reference.chunks}
                  messageContent={answerContent}
                ></ReferenceImageList>
              </InlineRenderBoundary>
            )}
            {isAssistant &&
              hasReferenceChunks &&
              referenceDocumentList.length > 0 && (
                <InlineRenderBoundary
                  boundaryKey={`${item.id}-reference-docs-${referenceDocumentList.length}`}
                >
                  <ReferenceDocumentList
                    list={referenceDocumentList}
                  ></ReferenceDocumentList>
                </InlineRenderBoundary>
              )}
            {isUser &&
              Array.isArray(uploadedFiles) &&
              uploadedFiles.length > 0 && (
                <UploadedMessageFiles
                  files={uploadedFiles as UploadResponseDataType[]}
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
          </section>
        </div>
      </section>
    </div>
  );
};

export default memo(MessageItem);
