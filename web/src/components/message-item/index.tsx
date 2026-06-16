import { MessageType } from '@/constants/chat';
import {
  IMessage,
  IReference,
  IReferenceChunk,
  UploadResponseDataType,
} from '@/interfaces/database/chat';
import classNames from 'classnames';
import { memo, useCallback, useEffect, useMemo, useState } from 'react';

import { IRegenerateMessage, IRemoveMessageById } from '@/hooks/logic-hooks';
import { cn } from '@/lib/utils';
import {
  getThinkingPreview,
  parseRetrievingAndAnswer,
  parseThinkAndAnswer,
} from '@/utils/chat';
import { CheckCircle2, ChevronDown, ChevronUp, Loader2 } from 'lucide-react';
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
  const thinkingPreview = useMemo(
    () => getThinkingPreview(parsedContent.thinking, loading ? 6 : 2),
    [loading, parsedContent.thinking],
  );
  const retrievingPreview = useMemo(
    () => getThinkingPreview(parsedRetrievingContent.thinking, loading ? 6 : 2),
    [loading, parsedRetrievingContent.thinking],
  );
  const answerContent = parsedRetrievingContent.answer;
  const shouldShowRetrieving =
    isAssistant && (loading || parsedRetrievingContent.hasThinking);
  const isRetrievingRunning =
    loading && !parsedRetrievingContent.thinkingComplete;
  const displayedRetrieving = loading
    ? retrievingPreview
    : showRetrieving
      ? parsedRetrievingContent.thinking
      : retrievingPreview;
  const shouldShowRetrievingBody =
    !!parsedRetrievingContent.thinking && (loading || showRetrieving);
  const shouldShowThinking =
    isAssistant && (loading || parsedContent.hasThinking);
  const isThinkingRunning = loading && !parsedContent.thinkingComplete;
  const displayedThinking = loading
    ? thinkingPreview
    : showThinking
      ? parsedContent.thinking
      : thinkingPreview;
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
                  content={answerContent}
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
                  <span>
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
                    {displayedRetrieving}
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
                  <span>
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
                    {displayedThinking}
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
                <MarkdownContent
                  loading={loading}
                  content={answerContent}
                  reference={reference}
                  clickDocumentButton={clickDocumentButton}
                ></MarkdownContent>
              </div>
            )}
            {isAssistant && hasReferenceChunks && (
              <ReferenceImageList
                referenceChunks={reference.chunks}
                messageContent={answerContent}
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
