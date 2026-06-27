import { NextMessageInputOnPressEnterParameter } from '@/components/message-input/next';
import { MessageType } from '@/constants/chat';
import {
  hasAnswerPayload,
  useHandleMessageInputChange,
  useSelectDerivedMessages,
  useSendMessageWithSse,
} from '@/hooks/logic-hooks';
import { useGetChatSearchParams } from '@/hooks/use-chat-request';
import { IMessage } from '@/interfaces/database/chat';
import i18n from '@/locales/config';
import api from '@/utils/api';
import {
  buildLongTaskPreview,
  classify_generation_task,
} from '@/utils/generation-task';
import { useCallback, useEffect } from 'react';
import { useParams } from 'react-router';
import { v4 as uuid } from 'uuid';
import { CreateConversationBeforeSendMessageReturnType } from './use-chat-url';
import { useUploadFile } from './use-upload-file';

export type UseSendSingleMessageParameter = {
  controller: AbortController;
} & Pick<ReturnType<typeof useHandleMessageInputChange>, 'value' | 'setValue'> &
  Pick<ReturnType<typeof useUploadFile>, 'files' | 'clearFiles'>;

export function useSendSingleMessage({
  controller,
  value,
  setValue,
  files,
  clearFiles,
}: {
  controller: AbortController;
} & Pick<ReturnType<typeof useHandleMessageInputChange>, 'value' | 'setValue'> &
  Pick<ReturnType<typeof useUploadFile>, 'files' | 'clearFiles'>) {
  const { conversationId } = useGetChatSearchParams();
  const { id: chatId } = useParams();

  const { send, answer, done } = useSendMessageWithSse();

  const {
    scrollRef,
    messageContainerRef,
    setDerivedMessages,
    derivedMessages,
    addNewestAnswer,
    addNewestQuestion,
    removeLatestMessage,
    removeMessageById,
    removeMessagesAfterCurrentMessage,
  } = useSelectDerivedMessages();

  useEffect(() => {
    if (hasAnswerPayload(answer)) {
      addNewestAnswer(answer);
    }
  }, [answer, addNewestAnswer]);

  const sendMessage = useCallback(
    async ({
      message,
      currentConversationId,
      messages,
      enableInternet,
      enableThinking,
      selectedKnowledgeBaseId,
      ...params
    }: {
      message: IMessage;
      currentConversationId?: string;
      messages?: IMessage[];
    } & NextMessageInputOnPressEnterParameter) => {
      const sessionId = currentConversationId ?? conversationId;
      const res = await send(
        api.completionUrl,
        {
          chat_id: chatId,
          session_id: sessionId,
          messages: [
            ...(Array.isArray(messages) && messages?.length > 0
              ? messages
              : (derivedMessages ?? [])),
            message,
          ],
          reasoning: enableThinking,
          internet: enableInternet,
          selected_kb_ids:
            selectedKnowledgeBaseId === '__none__'
              ? []
              : selectedKnowledgeBaseId
                ? [selectedKnowledgeBaseId]
                : undefined,
          ...params,
          pass_all_history_messages: true,
        },
        controller,
      );

      if (res && (res?.response.status !== 200 || res?.data?.code !== 0)) {
        // cancel loading
        setValue(message.content);
        console.info('removeLatestMessage111');
        removeLatestMessage();
      }
    },
    [
      derivedMessages,
      conversationId,
      chatId,
      removeLatestMessage,
      setValue,
      send,
      controller,
    ],
  );

  const handlePressEnter = useCallback(
    async ({
      enableThinking,
      enableInternet,
      currentMessages,
      targetConversationId,
      ...params
    }: NextMessageInputOnPressEnterParameter &
      CreateConversationBeforeSendMessageReturnType) => {
      const id = uuid();

      addNewestQuestion({
        content: value,
        files: files as IMessage['files'],
        id,
        role: MessageType.User,
        conversationId: targetConversationId,
      });

      if (done) {
        const classification = classify_generation_task(value);
        setValue('');
        if (classification.shouldGenerateDocument) {
          addNewestAnswer({
            id,
            conversationId: targetConversationId,
            answer: buildLongTaskPreview(classification),
            data: {
              longTask: {
                ...classification,
                query: value.trim(),
                chatId,
                source: 'chat',
              },
            },
          });
          clearFiles();
          return;
        }

        sendMessage({
          currentConversationId: targetConversationId,
          messages: currentMessages,
          message: {
            id,
            content: value.trim(),
            role: MessageType.User,
            files: files as IMessage['files'],
            conversationId: targetConversationId,
          },
          enableInternet,
          enableThinking,
          ...params,
        });
      }
      clearFiles();
    },
    [
      addNewestQuestion,
      addNewestAnswer,
      value,
      files,
      done,
      clearFiles,
      setValue,
      sendMessage,
      chatId,
    ],
  );

  const continueMessage = useCallback(() => {
    if (!done || !conversationId) return;

    const id = uuid();
    const content = i18n.t('chat.continueInstruction', {
      defaultValue:
        'Continue from where the previous answer stopped. Do not repeat content already shown.',
    });

    addNewestQuestion({
      content,
      id,
      role: MessageType.User,
      conversationId,
    });

    sendMessage({
      currentConversationId: conversationId,
      messages: derivedMessages,
      message: {
        id,
        content,
        role: MessageType.User,
        conversationId,
      },
      enableThinking: false,
      enableInternet: false,
    });
  }, [addNewestQuestion, conversationId, derivedMessages, done, sendMessage]);

  return {
    scrollRef,
    messageContainerRef,
    setDerivedMessages,
    derivedMessages,
    addNewestAnswer,
    addNewestQuestion,
    removeLatestMessage,
    removeMessageById,
    removeMessagesAfterCurrentMessage,
    handlePressEnter,
    continueMessage,
    sendLoading: !done,
  };
}

export type HandlePressEnterType = ReturnType<
  typeof useSendSingleMessage
>['handlePressEnter'];
