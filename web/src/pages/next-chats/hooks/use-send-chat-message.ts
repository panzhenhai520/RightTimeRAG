import { NextMessageInputOnPressEnterParameter } from '@/components/message-input/next';
import { MessageType } from '@/constants/chat';
import {
  hasAnswerPayload,
  useHandleMessageInputChange,
  useRegenerateMessage,
  useScrollToBottom,
  useSendMessageWithSse,
} from '@/hooks/logic-hooks';
import { useGetChatSearchParams } from '@/hooks/use-chat-request';
import { IAnswer, IMessage } from '@/interfaces/database/chat';
import i18n from '@/locales/config';
import api from '@/utils/api';
import { buildMessageUuid } from '@/utils/chat';
import {
  buildLongTaskPreview,
  classify_generation_task,
} from '@/utils/generation-task';
import { omit, trim } from 'lodash';
import {
  SetStateAction,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useParams, useSearchParams } from 'react-router';
import { v4 as uuid } from 'uuid';
import { useCreateConversationBeforeSendMessage } from './use-chat-url';
import { useFindPrologueFromDialogList } from './use-select-conversation-list';
import { useUploadFile } from './use-upload-file';

const resolveMessages = (
  previousMessages: IMessage[],
  nextMessages: SetStateAction<IMessage[]>,
) =>
  typeof nextMessages === 'function'
    ? nextMessages(previousMessages)
    : nextMessages;

const normalizePrologueContent = (content: unknown) =>
  String(content ?? '')
    .replace(/\s+/g, ' ')
    .trim();

const buildPrologueMessageId = (conversationId: string) =>
  `prologue_${conversationId}`;

const isPrologueMessage = (
  message: IMessage,
  prologue: string | undefined,
  conversationId: string,
) => {
  if (message.role !== MessageType.Assistant) return false;
  if (message.id === buildPrologueMessageId(conversationId)) return true;
  return (
    normalizePrologueContent(message.content) !== '' &&
    normalizePrologueContent(message.content) ===
      normalizePrologueContent(prologue)
  );
};

const normalizePrologueMessages = (
  messages: IMessage[],
  prologue: string | undefined,
  conversationId: string,
  ensureLeading = false,
) => {
  const content = String(prologue ?? '').trim();
  if (!content) return messages;

  const nonPrologueMessages = messages.filter(
    (message) => !isPrologueMessage(message, prologue, conversationId),
  );

  if (!ensureLeading && nonPrologueMessages.length === messages.length) {
    return messages;
  }

  return [
    {
      role: MessageType.Assistant,
      content,
      id: buildPrologueMessageId(conversationId),
      conversationId,
    } as IMessage,
    ...nonPrologueMessages,
  ];
};

export const useSelectNextMessages = () => {
  const { isNew, conversationId } = useGetChatSearchParams();
  const { id: dialogId } = useParams();
  const prologue = useFindPrologueFromDialogList();
  const [sessionMessages, setSessionMessages] = useState<
    Record<string, IMessage[]>
  >({});
  const [emptyConversationMessages, setEmptyConversationMessages] = useState<
    IMessage[]
  >([]);

  const messageContainerRef = useRef<HTMLDivElement>(null);
  const derivedMessages = useMemo(
    () =>
      conversationId
        ? (sessionMessages[conversationId] ?? [])
        : emptyConversationMessages,
    [conversationId, emptyConversationMessages, sessionMessages],
  );
  const { scrollRef } = useScrollToBottom(derivedMessages, messageContainerRef);

  const setSessionMessagesById = useCallback(
    (sessionId: string, nextMessages: SetStateAction<IMessage[]>) => {
      if (!sessionId) {
        setEmptyConversationMessages((previousMessages) =>
          resolveMessages(previousMessages, nextMessages),
        );
        return;
      }

      setSessionMessages((previousState) => {
        const previousMessages = previousState[sessionId] ?? [];
        const messages = normalizePrologueMessages(
          resolveMessages(previousMessages, nextMessages),
          prologue,
          sessionId,
        );
        return {
          ...previousState,
          [sessionId]: messages,
        };
      });
    },
    [prologue],
  );

  const setDerivedMessages = useCallback(
    (nextMessages: SetStateAction<IMessage[]>) => {
      setSessionMessagesById(conversationId, nextMessages);
    },
    [conversationId, setSessionMessagesById],
  );

  const addPrologue = useCallback(() => {
    if (dialogId !== '' && prologue && (isNew === 'true' || !conversationId)) {
      const targetConversationId = conversationId || '';
      setSessionMessagesById(targetConversationId, (previousMessages) =>
        normalizePrologueMessages(
          previousMessages,
          prologue,
          targetConversationId,
          true,
        ),
      );
    }
  }, [conversationId, dialogId, isNew, prologue, setSessionMessagesById]);

  useEffect(() => {
    addPrologue();
  }, [addPrologue]);

  const withLeadingPrologue = useCallback(
    (messages: IMessage[], sessionId: string) =>
      normalizePrologueMessages(messages, prologue, sessionId, true),
    [prologue],
  );

  const addNewestQuestion = useCallback(
    (message: IMessage, answer: string = '') => {
      const sessionId = message.conversationId ?? conversationId;
      setSessionMessagesById(sessionId, (previousMessages) => [
        ...previousMessages,
        {
          ...message,
          id: buildMessageUuid(message),
        },
        {
          role: MessageType.Assistant,
          content: answer,
          conversationId: sessionId,
          id: buildMessageUuid({ ...message, role: MessageType.Assistant }),
        },
      ]);
    },
    [conversationId, setSessionMessagesById],
  );

  const addNewestAnswer = useCallback(
    (answer: IAnswer) => {
      const sessionId = answer.conversationId ?? conversationId;
      if (!sessionId) return;

      setSessionMessagesById(sessionId, (previousMessages) => [
        ...(previousMessages?.slice(0, -1) ?? []),
        {
          role: MessageType.Assistant,
          content: answer.answer,
          reference: answer.reference,
          id: buildMessageUuid({
            id: answer.id,
            role: MessageType.Assistant,
          }),
          prompt: answer.prompt,
          audio_binary: answer.audio_binary,
          conversationId: sessionId,
          ...omit(answer, 'reference'),
        },
      ]);
    },
    [conversationId, setSessionMessagesById],
  );

  const removeLatestMessageBySessionId = useCallback(
    (sessionId?: string) => {
      setSessionMessagesById(
        sessionId ?? conversationId,
        (previousMessages) => previousMessages?.slice(0, -2) ?? [],
      );
    },
    [conversationId, setSessionMessagesById],
  );

  const removeMessageById = useCallback(
    (messageId: string) => {
      setDerivedMessages(
        (previousMessages) =>
          previousMessages?.filter((x) => x.id !== messageId) ?? [],
      );
    },
    [setDerivedMessages],
  );

  const removeMessagesAfterCurrentMessage = useCallback(
    (messageId: string) => {
      setDerivedMessages((previousMessages) => {
        const index = previousMessages.findIndex((x) => x.id === messageId);
        if (index !== -1) {
          let nextMessages = previousMessages.slice(0, index + 2) ?? [];
          const latestMessage = nextMessages.at(-1);
          nextMessages = latestMessage
            ? [
                ...nextMessages.slice(0, -1),
                {
                  ...latestMessage,
                  content: '',
                  reference: undefined,
                  prompt: undefined,
                },
              ]
            : nextMessages;
          return nextMessages;
        }
        return previousMessages;
      });
    },
    [setDerivedMessages],
  );

  return {
    scrollRef,
    messageContainerRef,
    derivedMessages,
    addNewestAnswer,
    addNewestQuestion,
    removeLatestMessageBySessionId,
    removeMessageById,
    removeMessagesAfterCurrentMessage,
    setDerivedMessages,
    setSessionMessagesById,
    withLeadingPrologue,
  };
};

export const useSendMessage = (
  controller: AbortController,
  onConversationLoadingChange?: (
    conversationId: string,
    loading: boolean,
  ) => void,
) => {
  const { conversationId, isNew, suggestedQuestion } = useGetChatSearchParams();
  const { handleInputChange, value, setValue } = useHandleMessageInputChange();
  const [searchParams, setSearchParams] = useSearchParams();
  const suggestedQuestionSentRef = useRef('');

  const { handleUploadFile, isUploading, removeFile, files, clearFiles } =
    useUploadFile();

  const { id: chatId } = useParams();
  const { send, answer, done } = useSendMessageWithSse();
  const {
    scrollRef,
    messageContainerRef,
    derivedMessages,
    addNewestAnswer,
    addNewestQuestion,
    removeLatestMessageBySessionId,
    removeMessageById,
    removeMessagesAfterCurrentMessage,
    setDerivedMessages,
    setSessionMessagesById,
    withLeadingPrologue,
  } = useSelectNextMessages();

  const sendMessage = useCallback(
    async ({
      message,
      currentConversationId,
      messages,
      enableInternet,
      enableThinking,
      selectedKnowledgeBaseId,
    }: {
      message: IMessage;
      currentConversationId?: string;
      messages?: IMessage[];
    } & NextMessageInputOnPressEnterParameter) => {
      const sessionId = currentConversationId ?? conversationId;
      if (sessionId) {
        onConversationLoadingChange?.(sessionId, true);
      }
      try {
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
            pass_all_history_messages: true,
            reasoning: enableThinking,
            internet: enableInternet,
            selected_kb_ids:
              selectedKnowledgeBaseId === '__none__'
                ? []
                : selectedKnowledgeBaseId
                  ? [selectedKnowledgeBaseId]
                  : undefined,
          },
          controller,
        );

        if (res && (res?.response.status !== 200 || res?.data?.code !== 0)) {
          // cancel loading
          setValue(message.content);
          removeLatestMessageBySessionId(sessionId);
        }
      } finally {
        if (sessionId) {
          onConversationLoadingChange?.(sessionId, false);
        }
      }
    },
    [
      derivedMessages,
      conversationId,
      chatId,
      removeLatestMessageBySessionId,
      setValue,
      send,
      controller,
      onConversationLoadingChange,
    ],
  );

  const { regenerateMessage } = useRegenerateMessage({
    removeMessagesAfterCurrentMessage,
    sendMessage,
    messages: derivedMessages,
  });

  const { createConversationBeforeSendMessage } =
    useCreateConversationBeforeSendMessage();

  const handlePressEnter = useCallback(
    async ({
      enableThinking,
      enableInternet,
      selectedKnowledgeBaseId,
    }: NextMessageInputOnPressEnterParameter) => {
      if (trim(value) === '') return;

      const data = await createConversationBeforeSendMessage(value);

      if (data === undefined) {
        return;
      }

      const { targetConversationId, currentMessages } = data;

      const id = uuid();
      const sendingFromNewConversation =
        conversationId === '' || isNew === 'true';
      if (currentMessages?.length || sendingFromNewConversation) {
        setSessionMessagesById(
          targetConversationId,
          sendingFromNewConversation
            ? withLeadingPrologue(currentMessages ?? [], targetConversationId)
            : currentMessages,
        );
      }

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
          selectedKnowledgeBaseId,
        });
      }

      clearFiles();

      // Auto scroll to bottom when sending new message
      if (messageContainerRef.current) {
        const el = messageContainerRef.current;

        requestAnimationFrame(() => {
          el.scrollTo({
            top: el.scrollHeight,
          });
        });
      }
    },
    [
      value,
      createConversationBeforeSendMessage,
      addNewestQuestion,
      addNewestAnswer,
      files,
      done,
      clearFiles,
      setValue,
      sendMessage,
      messageContainerRef,
      chatId,
      setSessionMessagesById,
      withLeadingPrologue,
      conversationId,
      isNew,
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
      message: {
        id,
        content,
        role: MessageType.User,
        conversationId,
      },
      messages: derivedMessages,
      enableThinking: false,
      enableInternet: false,
    });

    if (messageContainerRef.current) {
      const el = messageContainerRef.current;
      requestAnimationFrame(() => {
        el.scrollTo({ top: el.scrollHeight });
      });
    }
  }, [
    addNewestQuestion,
    conversationId,
    derivedMessages,
    done,
    messageContainerRef,
    sendMessage,
  ]);

  useEffect(() => {
    const question = (suggestedQuestion ?? '').trim();
    if (
      !question ||
      !done ||
      !chatId ||
      suggestedQuestionSentRef.current === question
    ) {
      return;
    }

    suggestedQuestionSentRef.current = question;
    const nextParams = new URLSearchParams(searchParams);
    nextParams.delete('suggestedQuestion');
    setSearchParams(nextParams, { replace: true });

    const sendSuggestedQuestion = async () => {
      const data = await createConversationBeforeSendMessage(question);
      if (data === undefined) return;

      const { targetConversationId, currentMessages } = data;
      const id = uuid();
      const sendingFromNewConversation =
        conversationId === '' || isNew === 'true';
      if (currentMessages?.length || sendingFromNewConversation) {
        setSessionMessagesById(
          targetConversationId,
          sendingFromNewConversation
            ? withLeadingPrologue(currentMessages ?? [], targetConversationId)
            : currentMessages,
        );
      }
      addNewestQuestion({
        content: question,
        id,
        role: MessageType.User,
        conversationId: targetConversationId,
      });

      sendMessage({
        currentConversationId: targetConversationId,
        messages: currentMessages,
        message: {
          id,
          content: question,
          role: MessageType.User,
          conversationId: targetConversationId,
        },
        enableThinking: false,
        enableInternet: false,
      });
    };

    sendSuggestedQuestion();
  }, [
    addNewestQuestion,
    chatId,
    createConversationBeforeSendMessage,
    done,
    searchParams,
    sendMessage,
    setSessionMessagesById,
    setSearchParams,
    suggestedQuestion,
    withLeadingPrologue,
    conversationId,
    isNew,
  ]);

  useEffect(() => {
    // Only apply streamed chunks to the session that originated them.
    // This prevents a background stream from overwriting a different
    // conversation after the user switches history sessions.
    if (hasAnswerPayload(answer) && answer.conversationId) {
      addNewestAnswer(answer);
    }
  }, [answer, addNewestAnswer]);

  return {
    handlePressEnter,
    handleInputChange,
    value,
    setValue,
    regenerateMessage,
    continueMessage,
    sendLoading: !done,
    scrollRef,
    messageContainerRef,
    derivedMessages,
    removeMessageById,
    handleUploadFile,
    isUploading,
    removeFile,
    setDerivedMessages,
  };
};
