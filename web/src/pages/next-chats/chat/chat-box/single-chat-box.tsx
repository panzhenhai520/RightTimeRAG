import { NextMessageInput } from '@/components/message-input/next';
import MessageItem from '@/components/message-item';
import PdfSheet from '@/components/pdf-drawer';
import { useClickDrawer } from '@/components/pdf-drawer/hooks';
import { TtsPlaybackConsent } from '@/components/tts-playback-consent';
import { MessageType } from '@/constants/chat';
import { useFetchChat, useGetChatSearchParams } from '@/hooks/use-chat-request';
import { useFetchUserInfo } from '@/hooks/use-user-setting-request';
import { IClientConversation } from '@/interfaces/database/chat';
import api from '@/utils/api';
import {
  buildMessageUuidWithRole,
  mergeFinalAnswerWithProcess,
} from '@/utils/chat';
import request from '@/utils/next-request';
import { t } from 'i18next';
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import {
  useGetSendButtonDisabled,
  useSendButtonDisabled,
} from '../../hooks/use-button-disabled';
import { useCreateConversationBeforeUploadDocument } from '../../hooks/use-create-conversation';
import { useSendMessage } from '../../hooks/use-send-chat-message';
import { buildMessageItemReference } from '../../utils';
import { useShowInternet } from '../use-show-internet';

const hasProcessBlocks = (content: unknown) =>
  typeof content === 'string' && /<(?:retrieving|think)>/i.test(content);

interface IProps {
  controller: AbortController;
  stopOutputMessage(): void;
  conversation: IClientConversation;
}

export function SingleChatBox({
  controller,
  stopOutputMessage,
  conversation,
}: IProps) {
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
  } = useSendMessage(controller);
  const { data: userInfo } = useFetchUserInfo();
  const { data: currentDialog } = useFetchChat();
  const { createConversationBeforeUploadDocument } =
    useCreateConversationBeforeUploadDocument();
  const { conversationId } = useGetChatSearchParams();
  const disabled = useGetSendButtonDisabled();
  const sendDisabled = useSendButtonDisabled(value);
  const [addToMemoryLoading, setAddToMemoryLoading] = useState(false);
  const { visible, hideModal, documentId, selectedChunk, clickDocumentButton } =
    useClickDrawer();

  const showInternet = useShowInternet();

  useEffect(() => {
    const messages = conversation?.messages;
    if (Array.isArray(messages)) {
      setDerivedMessages((prevMessages) => {
        const localById = new Map(prevMessages.map((m) => [m.id, m]));
        const localAssistants = prevMessages.filter(
          (m) => m.role === MessageType.Assistant,
        );
        let assistantIndex = -1;
        // Preserve uploaded file objects from local state that the server doesn't
        // persist (e.g. File instances). Build a map of message id → files from
        // the current local state so they survive when server data is applied.
        const filesMap = new Map(
          prevMessages
            .filter((m) => m.files?.length)
            .map((m) => [m.id, m.files]),
        );
        return messages.map((m) => {
          const sameIdLocal = localById.get(m.id);
          let sameOrderLocal: typeof sameIdLocal | undefined;
          let serverReference = m.reference;
          if (m.role === MessageType.Assistant) {
            assistantIndex += 1;
            sameOrderLocal = localAssistants[assistantIndex];
            if (!serverReference && assistantIndex > 0) {
              serverReference = conversation.reference?.[assistantIndex - 1];
            }
          }
          const localMessage = sameIdLocal ?? sameOrderLocal;
          const localContent = String(localMessage?.content ?? '');
          const serverContent = String(m.content ?? '');

          return {
            ...m,
            ...(hasProcessBlocks(localContent) &&
            !hasProcessBlocks(serverContent)
              ? {
                  content: mergeFinalAnswerWithProcess(
                    localContent,
                    serverContent,
                  ),
                }
              : {}),
            reference: serverReference ?? localMessage?.reference,
            files: filesMap.get(m.id) ?? m.files,
          };
        });
      });
    }
  }, [conversation?.messages, conversation.reference, setDerivedMessages]);

  const handleAddToMemory = useCallback(async () => {
    if (!currentDialog.id || !conversationId) {
      toast.info(t('chat.addToMemoryPreparing'));
      return;
    }
    setAddToMemoryLoading(true);
    try {
      const { data } = await request.post(api.memorizeChat, {
        chat_id: currentDialog.id,
        session_id: conversationId,
      });
      if (data?.code === 0) {
        toast.success(t('chat.addToMemorySuccess'));
      } else {
        toast.error(data?.message || 'Failed to add memo');
      }
    } finally {
      setAddToMemoryLoading(false);
    }
  }, [conversationId, currentDialog.id]);

  useEffect(() => {
    // Clear the message list after deleting the conversation.
    if (conversationId === '') {
      setDerivedMessages([]);
    }
  }, [conversationId, setDerivedMessages]);

  return (
    <section className="flex flex-col h-full gap-4">
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
                sendLoading &&
                derivedMessages.length - 1 === i
              }
              item={message}
              nickname={userInfo.nickname}
              avatar={userInfo.avatar}
              avatarDialog={currentDialog.icon}
              ttsConfig={
                currentDialog.prompt_config?.tts
                  ? currentDialog.prompt_config?.tts_config
                  : undefined
              }
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
              sendLoading={sendLoading}
            />
          ))}
        </div>
        <div ref={scrollRef} />
      </div>

      <div className="p-5 pt-0">
        <TtsPlaybackConsent
          enabled={Boolean(currentDialog?.prompt_config?.tts)}
          className="mb-3"
        />
        <NextMessageInput
          disabled={disabled}
          sendDisabled={sendDisabled}
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
          onAddToMemory={handleAddToMemory}
          addToMemoryLoading={addToMemoryLoading}
          showReasoning
          showInternet={showInternet}
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
  );
}
