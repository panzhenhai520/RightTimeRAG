import { PromptIcon } from '@/assets/icon/next-icon';
import CopyToClipboard from '@/components/copy-to-clipboard';
import { Modal } from '@/components/ui/modal/modal';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { useSetModalState } from '@/hooks/common-hooks';
import { IRemoveMessageById } from '@/hooks/logic-hooks';
import { AgentChatContext } from '@/pages/agent/context';
import { downloadAgentFile } from '@/services/file-manager-service';
import { downloadFileFromBlob } from '@/utils/file-util';
import {
  DeleteOutlined,
  DislikeOutlined,
  LikeOutlined,
  LoadingOutlined,
  PauseCircleOutlined,
  SoundOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import { Download, FileSearch, NotebookText } from 'lucide-react';
import { useCallback, useContext } from 'react';
import { useTranslation } from 'react-i18next';
import FeedbackDialog from '../feedback-dialog';
import { PromptDialog } from '../prompt-dialog';
import { ToggleGroup, ToggleGroupItem } from '../ui/toggle-group';
import { useRemoveMessage, useSendFeedback, useSpeech } from './hooks';

interface IProps {
  messageId: string;
  content: string;
  prompt?: string;
  showLikeButton: boolean;
  audioBinary?: string;
  ttsConfig?: Record<string, unknown>;
  showLoudspeaker?: boolean;
  onSelectReferenceMessage?: () => void;
  showLog?: boolean;
  attachment?: {
    file_name: string;
    doc_id: string;
    format: string;
  };
  isShare?: boolean;
}

export const AssistantGroupButton = ({
  messageId,
  content,
  prompt,
  audioBinary,
  ttsConfig,
  showLikeButton,
  showLoudspeaker = true,
  onSelectReferenceMessage,
  showLog = true,
  attachment,
  isShare,
}: IProps) => {
  const { visible, hideModal, showModal, onFeedbackOk, loading } =
    useSendFeedback(messageId);
  const {
    visible: promptVisible,
    hideModal: hidePromptModal,
    showModal: showPromptModal,
  } = useSetModalState();
  const { t } = useTranslation();
  const { handleRead, ref, isPlaying, isLoading, speechState } = useSpeech(
    content,
    audioBinary,
    ttsConfig,
  );
  const speechTooltip =
    speechState === 'loading'
      ? t('chat.ttsGenerating')
      : speechState === 'playing'
        ? t('chat.ttsPlaying')
        : t('chat.read');

  const handleLike = useCallback(() => {
    onFeedbackOk({ thumbup: true });
  }, [onFeedbackOk]);

  const { showLogSheet } = useContext(AgentChatContext);

  const handleShowLogSheet = useCallback(() => {
    showLogSheet(messageId);
  }, [messageId, showLogSheet]);

  return (
    <>
      <ToggleGroup
        type={'single'}
        size="sm"
        variant="outline"
        className="space-x-1"
      >
        <ToggleGroupItem value="a">
          <CopyToClipboard
            text={content}
            className="border-none hover:!bg-transparent"
          ></CopyToClipboard>
        </ToggleGroupItem>
        {showLoudspeaker && (
          <ToggleGroupItem
            value="b"
            onClick={handleRead}
            aria-label={speechTooltip}
            title={speechTooltip}
            className={isPlaying ? 'text-accent-primary' : undefined}
          >
            <Tooltip>
              <TooltipTrigger asChild>
                <span>
                  {isLoading ? (
                    <LoadingOutlined spin />
                  ) : isPlaying ? (
                    <PauseCircleOutlined className="animate-pulse" />
                  ) : (
                    <SoundOutlined />
                  )}
                </span>
              </TooltipTrigger>
              <TooltipContent>{speechTooltip}</TooltipContent>
            </Tooltip>
            <audio src="" ref={ref}></audio>
          </ToggleGroupItem>
        )}
        {showLikeButton && (
          <>
            <ToggleGroupItem value="c" onClick={handleLike}>
              <LikeOutlined />
            </ToggleGroupItem>
            <ToggleGroupItem value="d" onClick={showModal}>
              <DislikeOutlined />
            </ToggleGroupItem>
          </>
        )}
        {onSelectReferenceMessage && (
          <ToggleGroupItem
            value="d-recall"
            onClick={onSelectReferenceMessage}
            aria-label={t('chat.showRecallPanel')}
            title={t('chat.showRecallPanel')}
          >
            <FileSearch />
          </ToggleGroupItem>
        )}
        {prompt && (
          <ToggleGroupItem value="e" onClick={showPromptModal}>
            <PromptIcon style={{ fontSize: '16px' }} />
          </ToggleGroupItem>
        )}
        {showLog && (
          <ToggleGroupItem value="f" onClick={handleShowLogSheet}>
            <NotebookText className="size-4" />
          </ToggleGroupItem>
        )}
        {!!attachment?.doc_id && !isShare && (
          <ToggleGroupItem
            value="g"
            onClick={async () => {
              try {
                const response = await downloadAgentFile({
                  docId: attachment.doc_id,
                  ext: attachment.format,
                });
                const blob = new Blob([response.data], {
                  type: response.data.type,
                });
                downloadFileFromBlob(blob, attachment.file_name);
              } catch (error) {
                console.error('Download failed:', error);
              }
            }}
          >
            <Download size={16} />
          </ToggleGroupItem>
        )}
      </ToggleGroup>
      {visible && (
        <FeedbackDialog
          visible={visible}
          hideModal={hideModal}
          onOk={onFeedbackOk}
          loading={loading}
        ></FeedbackDialog>
      )}
      {promptVisible && (
        <PromptDialog
          visible={promptVisible}
          hideModal={hidePromptModal}
          prompt={prompt}
        ></PromptDialog>
      )}
    </>
  );
};

interface UserGroupButtonProps extends Partial<IRemoveMessageById> {
  messageId: string;
  content: string;
  regenerateMessage?: () => void;
  sendLoading: boolean;
}

export const UserGroupButton = ({
  content,
  messageId,
  sendLoading,
  removeMessageById,
  regenerateMessage,
}: UserGroupButtonProps) => {
  const { onRemoveMessage, loading } = useRemoveMessage(
    messageId,
    removeMessageById,
  );
  const { t } = useTranslation();
  const handleRemoveTurn = useCallback(() => {
    Modal.confirm({
      title: t('chat.deleteTurnTitle', { defaultValue: 'Delete this turn?' }),
      content: t('chat.deleteTurnDescription', {
        defaultValue:
          'This will remove the selected question and its answer from this conversation. Deleted content will not be used when adding this conversation to memo.',
      }),
      okText: t('common.delete'),
      cancelText: t('common.cancel'),
      onOk: onRemoveMessage,
    });
  }, [onRemoveMessage, t]);

  return (
    <ToggleGroup
      type="single"
      size="sm"
      variant="outline"
      className="space-x-1"
    >
      <ToggleGroupItem value="a">
        <CopyToClipboard text={content}></CopyToClipboard>
      </ToggleGroupItem>
      {regenerateMessage && (
        <ToggleGroupItem
          value="b"
          onClick={regenerateMessage}
          disabled={sendLoading}
        >
          <Tooltip>
            <TooltipTrigger asChild>
              <SyncOutlined spin={sendLoading} />
            </TooltipTrigger>
            <TooltipContent>{t('chat.regenerate')}</TooltipContent>
          </Tooltip>
        </ToggleGroupItem>
      )}
      {removeMessageById && (
        <ToggleGroupItem
          value="c"
          onClick={handleRemoveTurn}
          disabled={loading}
        >
          <Tooltip>
            <TooltipTrigger asChild>
              <DeleteOutlined spin={loading} />
            </TooltipTrigger>
            <TooltipContent>
              {t('chat.deleteTurn', { defaultValue: 'Delete this Q&A turn' })}
            </TooltipContent>
          </Tooltip>
        </ToggleGroupItem>
      )}
    </ToggleGroup>
  );
};
