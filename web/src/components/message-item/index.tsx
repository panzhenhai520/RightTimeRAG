import { MessageType } from '@/constants/chat';
import {
  IMessage,
  IReference,
  IReferenceChunk,
  UploadResponseDataType,
} from '@/interfaces/database/chat';
import classNames from 'classnames';
import { memo, useCallback, useMemo } from 'react';

import { IRegenerateMessage, IRemoveMessageById } from '@/hooks/logic-hooks';
import { cn } from '@/lib/utils';
import {
  getThinkingPreview,
  parseRetrievingAndAnswer,
  parseThinkAndAnswer,
} from '@/utils/chat';
import { isEmpty } from 'lodash';
import {
  CheckCircle2,
  ChevronDown,
  ClipboardList,
  FileSearch,
  Loader2,
  PenLine,
  SearchCheck,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { DocumentDownloadButton } from '../document-download-button';
import MarkdownContent from '../markdown-content';
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
  clickDocumentButton?: (documentId: string, chunk: IReferenceChunk) => void;
  index: number;
  showLikeButton?: boolean;
  showLoudspeaker?: boolean;
}

const MessageItem = ({
  item,
  reference,
  loading = false,
  avatar,
  avatarDialog,
  sendLoading = false,
  clickDocumentButton,
  index,
  removeMessageById,
  regenerateMessage,
  showLikeButton = true,
  showLoudspeaker = true,
  visibleAvatar = true,
}: IProps) => {
  const { t } = useTranslation();
  const { theme } = useTheme();
  const isAssistant = item.role === MessageType.Assistant;
  const isUser = item.role === MessageType.User;

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
    return (reference?.doc_aggs ?? []).filter((doc) =>
      citedDocumentIds.has(doc.doc_id),
    );
  }, [citedDocumentIds, reference?.doc_aggs]);
  const hasReferenceChunks = referenceChunks.length > 0;

  const documentDownloadInfos = useMemo(
    () => item.downloads ?? [],
    [item.downloads],
  );
  const messageContent = item.content;
  const parsedContent = useMemo(
    () => parseThinkAndAnswer(messageContent),
    [messageContent],
  );
  const parsedRetrievingContent = useMemo(
    () => parseRetrievingAndAnswer(parsedContent.answer),
    [parsedContent.answer],
  );
  const combinedThinking = useMemo(
    () =>
      [parsedContent.thinking, parsedRetrievingContent.thinking]
        .filter(Boolean)
        .join('\n\n'),
    [parsedContent.thinking, parsedRetrievingContent.thinking],
  );
  const thinkingPreview = useMemo(
    () => getThinkingPreview(combinedThinking, 2),
    [combinedThinking],
  );
  const answerContent = parsedRetrievingContent.answer;
  const hasProcessSignals =
    parsedContent.hasThinking || parsedRetrievingContent.hasThinking;
  const shouldShowProgress = isAssistant && (loading || hasProcessSignals);
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
                className="size-10"
                avatar={avatar ?? '/logo.svg'}
                isPerson
              />
            ) : avatarDialog ? (
              <RAGFlowAvatar
                className="size-10"
                avatar={avatarDialog}
                isPerson
              />
            ) : (
              <SvgIcon
                name={'assistant'}
                width={'100%'}
                className={cn('size-10 fill-current')}
              ></SvgIcon>
            ))}

          <section className="flex min-w-0 gap-2 flex-1 flex-col">
            {isAssistant ? (
              index !== 0 && (
                <AssistantGroupButton
                  messageId={item.id}
                  content={messageContent}
                  prompt={item.prompt}
                  showLikeButton={showLikeButton}
                  audioBinary={item.audio_binary}
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
            {shouldShowProgress && (
              <div className={styles.thinkingPanel}>
                <div className={styles.thinkingHeader}>
                  {loading ? (
                    <Loader2
                      className={cn(styles.thinkingIcon, 'animate-spin')}
                    />
                  ) : (
                    <CheckCircle2 className={styles.thinkingIcon} />
                  )}
                  <span>
                    {loading ? t('chat.processRunning') : t('chat.processShow')}
                  </span>
                  {combinedThinking && (
                    <ChevronDown className={styles.thinkingChevron} />
                  )}
                </div>
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
                  {loading ? thinkingPreview : combinedThinking}
                </div>
              </div>
            )}
            {/* Show message content if there's any text besides the download */}
            {messageContent && (
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
                <MarkdownContent
                  loading={loading}
                  content={messageContent}
                  reference={reference}
                  clickDocumentButton={clickDocumentButton}
                ></MarkdownContent>
              </div>
            )}
            {isAssistant && hasReferenceChunks && (
              <ReferenceImageList
                referenceChunks={reference.chunks}
                messageContent={messageContent}
              ></ReferenceImageList>
            )}
            {isAssistant &&
              hasReferenceChunks &&
              referenceDocumentList.length > 0 && (
                <ReferenceDocumentList
                  list={referenceDocumentList}
                ></ReferenceDocumentList>
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
          </section>
        </div>
      </section>
    </div>
  );
};

export default memo(MessageItem);
