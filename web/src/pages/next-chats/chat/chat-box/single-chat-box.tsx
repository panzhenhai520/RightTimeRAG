import { DS4CompactingBanner } from '@/components/ds4-compacting-banner';
import { NextMessageInput } from '@/components/message-input/next';
import MessageItem from '@/components/message-item';
import PdfSheet from '@/components/pdf-drawer';
import { useClickDrawer } from '@/components/pdf-drawer/hooks';
import { TtsPlaybackConsent } from '@/components/tts-playback-consent';
import { MessageType } from '@/constants/chat';
import { useFetchChat, useGetChatSearchParams } from '@/hooks/use-chat-request';
import {
  ds4IsCompacting,
  ds4IsWarming,
  ds4NeedsMaintenance,
  useDS4Health,
} from '@/hooks/use-ds4-health';
import { useFetchUserInfo } from '@/hooks/use-user-setting-request';
import { IClientConversation } from '@/interfaces/database/chat';
import api from '@/utils/api';
import {
  buildMessageUuidWithRole,
  mergeFinalAnswerWithProcess,
} from '@/utils/chat';
import request from '@/utils/next-request';
import { useResponsive } from 'ahooks';
import { t } from 'i18next';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import {
  useGetSendButtonDisabled,
  useSendButtonDisabled,
} from '../../hooks/use-button-disabled';
import { useCreateConversationBeforeUploadDocument } from '../../hooks/use-create-conversation';
import { useSendMessage } from '../../hooks/use-send-chat-message';
import { buildMessageItemReference } from '../../utils';
import { AddToMemoryDialog } from '../add-to-memory-dialog';
import { useShowInternet } from '../use-show-internet';
import { RecallPanel } from './recall-panel';

const hasProcessBlocks = (content: unknown) =>
  typeof content === 'string' && /<(?:retrieving|think)>/i.test(content);

interface IProps {
  controller: AbortController;
  stopOutputMessage(): void;
  conversation: IClientConversation;
  onLoadingChange?: (loading: boolean, conversationId?: string) => void;
  onConversationRefresh?: (conversationId: string) => void | Promise<void>;
}

export function SingleChatBox({
  controller,
  stopOutputMessage,
  conversation,
  onLoadingChange,
  onConversationRefresh,
}: IProps) {
  const { data: userInfo } = useFetchUserInfo();
  const { data: currentDialog } = useFetchChat();
  const { createConversationBeforeUploadDocument } =
    useCreateConversationBeforeUploadDocument();
  const { conversationId, isNew } = useGetChatSearchParams();
  const disabled = useGetSendButtonDisabled();
  const ds4Health = useDS4Health();
  const ds4Busy =
    ds4IsCompacting(ds4Health.state) ||
    ds4IsWarming(ds4Health.state) ||
    ds4NeedsMaintenance(ds4Health);
  const [addToMemoryLoading, setAddToMemoryLoading] = useState(false);
  const [addToMemoryOpen, setAddToMemoryOpen] = useState(false);
  const { visible, hideModal, documentId, selectedChunk, clickDocumentButton } =
    useClickDrawer();

  const showInternet = useShowInternet();

  const activeLoadingConversationIdRef = useRef<string | undefined>();

  function handleConversationLoadingChange(
    sessionId: string,
    loading: boolean,
  ) {
    if (loading) {
      activeLoadingConversationIdRef.current = sessionId;
    }
    onLoadingChange?.(loading, sessionId);
  }

  const {
    value,
    scrollRef,
    messageContainerRef,
    sendLoading,
    derivedMessages,
    isUploading,
    handleInputChange,
    handlePressEnter,
    regenerateMessage,
    continueMessage,
    removeMessageById,
    handleUploadFile,
    removeFile,
    setDerivedMessages,
  } = useSendMessage(controller, handleConversationLoadingChange);
  const sendDisabled = useSendButtonDisabled(value);
  const isCurrentConversationLoading =
    sendLoading &&
    activeLoadingConversationIdRef.current !== undefined &&
    activeLoadingConversationIdRef.current === conversationId;

  // When streaming ends the thinking panel expands from preview to full content,
  // pushing the answer below the viewport. Scroll back to the bottom so the
  // answer remains visible without requiring a manual drag.
  const scrollPrevSendLoadingRef = useRef(false);
  useEffect(() => {
    if (scrollPrevSendLoadingRef.current && !sendLoading) {
      const refreshConversationId =
        activeLoadingConversationIdRef.current ?? conversationId;
      if (refreshConversationId) {
        void onConversationRefresh?.(refreshConversationId);
      }
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          if (messageContainerRef.current) {
            messageContainerRef.current.scrollTo({
              top: messageContainerRef.current.scrollHeight,
              behavior: 'auto',
            });
          }
        });
      });
      activeLoadingConversationIdRef.current = undefined;
    }
    scrollPrevSendLoadingRef.current = sendLoading;
  }, [conversationId, onConversationRefresh, sendLoading, messageContainerRef]);

  useEffect(() => {
    const messages = conversation?.messages;
    if (isNew === 'true') return;
    if (!conversationId) return;

    if (!Array.isArray(messages)) {
      return;
    }

    setDerivedMessages((localMessages) => {
      const localByKey = new Map(
        localMessages
          .filter((m) => m.id !== undefined && m.id !== null && m.id !== '')
          .map((m) => [buildMessageUuidWithRole(m), m]),
      );
      const serverKeys = new Set(
        messages
          .filter((m) => m.id !== undefined && m.id !== null && m.id !== '')
          .map((m) => buildMessageUuidWithRole(m)),
      );
      // Preserve uploaded file objects from local state that the server doesn't
      // persist (e.g. File instances). Build a map of message id -> files from
      // the current local state so they survive when server data is applied.
      const filesMap = new Map(
        localMessages
          .filter((m) => m.files?.length)
          .map((m) => [m.id, m.files]),
      );
      const mergedMessages = messages.map((m) => {
        const hasStableId = m.id !== undefined && m.id !== null && m.id !== '';
        const localMessage = hasStableId
          ? localByKey.get(buildMessageUuidWithRole(m))
          : undefined;
        const localContent = String(localMessage?.content ?? '');
        const serverContent = String(m.content ?? '');

        return {
          ...m,
          ...(m.role === MessageType.Assistant &&
          hasProcessBlocks(localContent) &&
          !hasProcessBlocks(serverContent)
            ? {
                content: mergeFinalAnswerWithProcess(
                  localContent,
                  serverContent,
                ),
              }
            : {}),
          reference: m.reference ?? localMessage?.reference,
          files: filesMap.get(m.id) ?? m.files,
        };
      });
      const pendingLocalMessages = localMessages.filter((m) => {
        const key = buildMessageUuidWithRole(m);
        return !serverKeys.has(key);
      });
      return [...mergedMessages, ...pendingLocalMessages];
    });
  }, [conversation?.messages, conversationId, isNew, setDerivedMessages]);

  const openAddToMemoryDialog = useCallback(() => {
    if (!currentDialog.id || !conversationId) {
      toast.info(t('chat.addToMemoryPreparing'));
      return;
    }
    setAddToMemoryOpen(true);
  }, [conversationId, currentDialog.id]);

  const handleAddToMemory = useCallback(
    async (topic: string) => {
      setAddToMemoryLoading(true);
      try {
        const { data } = await request.post(api.memorizeChat, {
          chat_id: currentDialog.id,
          session_id: conversationId,
          topic,
        });
        if (data?.code === 0) {
          toast.success(t('chat.addToMemorySuccess'));
          setAddToMemoryOpen(false);
        } else {
          toast.error(data?.message || 'Failed to add memo');
        }
      } finally {
        setAddToMemoryLoading(false);
      }
    },
    [conversationId, currentDialog.id],
  );

  // Latest assistant message (skip the prologue at index 0) and its reference,
  // used to feed the right-side recall panel.
  const latestAssistant = useMemo(() => {
    for (let i = (derivedMessages?.length ?? 0) - 1; i >= 0; i -= 1) {
      const m = derivedMessages[i];
      if (m.role === MessageType.Assistant && i !== 0) return m;
    }
    return undefined;
  }, [derivedMessages]);

  const [selectedReferenceMessageId, setSelectedReferenceMessageId] = useState<
    IClientConversation['messages'][number] | undefined
  >();

  useEffect(() => {
    setSelectedReferenceMessageId(undefined);
  }, [conversationId]);

  const activeReferenceMessage = useMemo(() => {
    if (selectedReferenceMessageId) {
      if (selectedReferenceMessageId.role === MessageType.Assistant) {
        return selectedReferenceMessageId;
      }
    }
    return latestAssistant;
  }, [latestAssistant, selectedReferenceMessageId]);

  const activeReference = useMemo(
    () =>
      activeReferenceMessage
        ? buildMessageItemReference(
            { messages: derivedMessages, reference: conversation.reference },
            activeReferenceMessage,
          )
        : undefined,
    [activeReferenceMessage, derivedMessages, conversation.reference],
  );

  // Only split out the recall panel on wide screens (≥1200px). On narrower
  // screens we keep the references inline inside the message (single column).
  const responsive = useResponsive();
  const wideEnough = Boolean(responsive.xl);
  const hasRecallContent =
    isCurrentConversationLoading ||
    (activeReference?.chunks?.length ?? 0) > 0 ||
    Boolean(activeReference?.evidence_audit);
  const showRecallPanel = wideEnough && hasRecallContent;

  // Draggable splitter width for the recall panel.
  const RECALL_MIN_WIDTH = 280;
  const RECALL_MAX_WIDTH = 640;
  const RECALL_EXPANDED_WIDTH = 760;
  const [recallWidth, setRecallWidth] = useState(360);
  const [recallExpanded, setRecallExpanded] = useState(false);
  const [recallCollapsed, setRecallCollapsed] = useState(false);
  const recallWidthRef = useRef(360);
  const recallWidthBeforeCollapseRef = useRef(360);
  const collapsedRecallWidth = 56;
  const effectiveRecallWidth = recallExpanded
    ? RECALL_EXPANDED_WIDTH
    : recallCollapsed
      ? collapsedRecallWidth
      : recallWidth;
  const handleToggleRecallCollapse = useCallback(() => {
    setRecallCollapsed((current) => {
      if (!current) {
        recallWidthBeforeCollapseRef.current = recallWidthRef.current;
      } else {
        const restoreWidth = recallWidthBeforeCollapseRef.current || 360;
        recallWidthRef.current = restoreWidth;
        setRecallWidth(restoreWidth);
      }
      return !current;
    });
    setRecallExpanded(false);
  }, []);
  const handleRecallResizeStart = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    // Dragging takes over from the maximized state.
    setRecallExpanded(false);
    setRecallCollapsed(false);
    const startX = e.clientX;
    const startWidth = recallWidthRef.current;
    const onMove = (ev: PointerEvent) => {
      // Panel is on the right: dragging left widens it.
      const next = Math.min(
        RECALL_MAX_WIDTH,
        Math.max(RECALL_MIN_WIDTH, startWidth + (startX - ev.clientX)),
      );
      recallWidthRef.current = next;
      setRecallWidth(next);
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, []);

  return (
    <div className="flex h-full min-h-0">
      <section className="flex flex-col h-full min-w-0 flex-1 gap-4">
        <div
          ref={messageContainerRef}
          className="p-5 flex-1 overflow-auto min-h-0 scrollbar-auto"
        >
          <div className="w-full pr-5">
            {derivedMessages?.map((message, i) => (
              <MessageItem
                key={buildMessageUuidWithRole(message)}
                loading={
                  message.role === MessageType.Assistant &&
                  isCurrentConversationLoading &&
                  derivedMessages.length - 1 === i
                }
                item={message}
                nickname={userInfo.nickname}
                avatar={userInfo.avatar}
                avatarDialog={currentDialog.icon}
                ttsConfig={currentDialog.prompt_config?.tts_config}
                reference={buildMessageItemReference(
                  {
                    messages: derivedMessages,
                    reference: conversation.reference,
                  },
                  message,
                )}
                clickDocumentButton={clickDocumentButton}
                index={i}
                removeMessageById={removeMessageById}
                regenerateMessage={regenerateMessage}
                continueMessage={continueMessage}
                onSelectReferenceMessage={(selectedMessage) => {
                  if (selectedMessage?.role === MessageType.Assistant) {
                    setSelectedReferenceMessageId(selectedMessage);
                  }
                }}
                sendLoading={isCurrentConversationLoading}
                hideInlineReferences={showRecallPanel}
              />
            ))}
            {/* DS4 KV maintenance status — hidden by the component when idle. */}
            <DS4CompactingBanner
              avatarDialog={currentDialog.icon}
              health={ds4Health}
            />
          </div>
          <div ref={scrollRef} />
        </div>

        <div className="p-5 pt-0">
          <TtsPlaybackConsent
            enabled={Boolean(currentDialog?.prompt_config?.tts)}
            className="mb-3"
          />
          <NextMessageInput
            disabled={disabled || ds4Busy}
            sendDisabled={sendDisabled || ds4Busy}
            sendLoading={sendLoading}
            value={value}
            resize="vertical"
            onInputChange={handleInputChange}
            onPressEnter={handlePressEnter}
            conversationId={conversationId}
            createConversationBeforeUploadDocument={
              createConversationBeforeUploadDocument
            }
            stopOutputMessage={stopOutputMessage}
            onUpload={handleUploadFile}
            isUploading={isUploading}
            removeFile={removeFile}
            onAddToMemory={openAddToMemoryDialog}
            addToMemoryLoading={addToMemoryLoading}
            showReasoning
            showInternet={showInternet}
          />
          <AddToMemoryDialog
            open={addToMemoryOpen}
            loading={addToMemoryLoading}
            onOpenChange={setAddToMemoryOpen}
            onSubmit={handleAddToMemory}
          />
          {visible && (
            <PdfSheet
              visible={visible}
              hideModal={hideModal}
              documentId={documentId}
              chunk={selectedChunk}
            ></PdfSheet>
          )}
        </div>
      </section>
      {showRecallPanel && (
        <>
          <div
            role="separator"
            aria-orientation="vertical"
            className="w-1 shrink-0 cursor-col-resize bg-border transition-colors hover:bg-primary/40"
            onPointerDown={handleRecallResizeStart}
            data-testid="chat-recall-resizer"
          />
          <RecallPanel
            reference={activeReference}
            loading={isCurrentConversationLoading}
            width={effectiveRecallWidth}
            expanded={recallExpanded}
            collapsed={recallCollapsed}
            onToggleExpand={() => setRecallExpanded((v) => !v)}
            onToggleCollapse={handleToggleRecallCollapse}
          />
        </>
      )}
    </div>
  );
}
