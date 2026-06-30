import { NextMessageInputOnPressEnterParameter } from '@/components/message-input/next';
import sonnerMessage from '@/components/ui/message';
import { MessageType } from '@/constants/chat';
import {
  useHandleMessageInputChange,
  useSelectDerivedMessages,
} from '@/hooks/logic-hooks';
import {
  IAttachment,
  IEventList,
  IMessageEndData,
  IMessageEndEvent,
  IMessageEvent,
  MessageEventType,
  useSendMessageBySSE,
} from '@/hooks/use-send-message';
import { IDocumentDownloadInfo, Message } from '@/interfaces/database/chat';
import i18n from '@/locales/config';
import {
  createBackgroundAgentRun,
  fetchAgentRunEvents,
} from '@/services/agent-service';
import api from '@/utils/api';
import {
  buildLongTaskPreview,
  classify_generation_task,
} from '@/utils/generation-task';
import { get } from 'lodash';
import trim from 'lodash/trim';
import {
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useParams, useSearchParams } from 'react-router';
import { v4 as uuid } from 'uuid';
import { BeginId } from '../constant';
import { MessageWaitSuffix } from '../constant/chat';
import { AgentChatLogContext } from '../context';
import { transferInputsArrayToObject } from '../form/begin-form/use-watch-change';
import {
  useIsTaskMode,
  useSelectBeginNodeDataInputs,
} from '../hooks/use-get-begin-query';
import { useStopMessage } from '../hooks/use-stop-message';
import { BeginQuery } from '../interface';
import useGraphStore from '../store';
import { receiveMessageError } from '../utils';
import { shouldSplitMessage } from '../utils/chat';

const normalizeDownloads = (downloads?: unknown): IDocumentDownloadInfo[] => {
  if (!Array.isArray(downloads)) {
    return [];
  }

  return downloads.filter((item): item is IDocumentDownloadInfo => {
    return Boolean(item?.doc_id && item?.filename);
  });
};

const uniqDownloads = (
  downloads: IDocumentDownloadInfo[],
): IDocumentDownloadInfo[] => {
  const seen = new Set<string>();

  return downloads.filter((item) => {
    const key = item.doc_id || `${item.filename}-${item.size ?? ''}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
};

export function findMessageFromList(eventList: IEventList) {
  const messageEventList = eventList.filter(
    (x) => x.event === MessageEventType.Message,
  ) as IMessageEvent[];
  const messageEndEventList = eventList.filter(
    (x) => x.event === MessageEventType.MessageEnd,
  ) as IMessageEndEvent[];

  let nextContent = '';

  let startIndex = -1;
  let endIndex = -1;
  let audioBinary = undefined;
  messageEventList.forEach((x, idx) => {
    const { data } = x;
    const { content, start_to_think, end_to_think, audio_binary } = data;
    if (audio_binary) {
      audioBinary = audio_binary;
    }
    if (start_to_think === true) {
      nextContent += '<think>' + content;
      startIndex = idx;
      return;
    }

    if (end_to_think === true) {
      endIndex = idx;
      nextContent += content + '</think>';
      return;
    }

    nextContent += content;
  });

  const currentIdx = messageEventList.length - 1;

  // Make sure that after start_to_think === true and before end_to_think === true, add a </think> tag at the end.
  if (startIndex >= 0 && startIndex <= currentIdx && endIndex === -1) {
    nextContent += '</think>';
  }

  const workflowFinished = eventList.find(
    (x) => x.event === MessageEventType.WorkflowFinished,
  ) as IMessageEvent;
  const workflowAttachment = workflowFinished?.data?.outputs?.attachment;
  const messageEndAttachment = messageEndEventList.find(
    (x) => x.data?.attachment,
  )?.data?.attachment;
  const workflowDownloads = normalizeDownloads(
    workflowFinished?.data?.outputs?.downloads,
  );
  const messageEndDownloads = messageEndEventList.flatMap((x) =>
    normalizeDownloads(x.data?.downloads),
  );

  return {
    id: eventList[0]?.message_id,
    content: nextContent,
    audio_binary: audioBinary,
    attachment: workflowAttachment?.doc_id
      ? workflowAttachment
      : messageEndAttachment || {},
    downloads: uniqDownloads([...messageEndDownloads, ...workflowDownloads]),
  };
}

export function findInputFromList(eventList: IEventList) {
  const inputEvent = eventList.find(
    (x) => x.event === MessageEventType.UserInputs,
  );

  if (!inputEvent) {
    return {};
  }

  return {
    id: inputEvent?.message_id,
    data: inputEvent?.data,
  };
}

export function getLatestError(eventList: IEventList) {
  const latest = eventList.at(-1) as
    | { code?: number; message?: string }
    | undefined;
  return (
    get(latest, 'data.outputs._ERROR') ||
    (latest?.code && latest.code !== 0 ? latest?.message : undefined)
  );
}

export const useGetBeginNodePrologue = () => {
  const getNode = useGraphStore((state) => state.getNode);
  const formData = get(getNode(BeginId), 'data.form', {});

  return useMemo(() => {
    if (formData?.enablePrologue) {
      return formData?.prologue;
    }
  }, [formData?.enablePrologue, formData?.prologue]);
};

export function useFindMessageReference(answerList: IEventList) {
  const [messageEndEventList, setMessageEndEventList] = useState<
    IMessageEndEvent[]
  >([]);

  const findReferenceByMessageId = useCallback(
    (messageId: string) => {
      const event = messageEndEventList.find(
        (item) => item.message_id === messageId,
      );
      if (event) {
        return (event?.data as IMessageEndData)?.reference;
      }
    },
    [messageEndEventList],
  );

  useEffect(() => {
    const messageEndEvent = answerList.find(
      (x) => x.event === MessageEventType.MessageEnd,
    );
    if (messageEndEvent) {
      setMessageEndEventList((list) => {
        const nextList = [...list];
        if (
          nextList.every((x) => x.message_id !== messageEndEvent.message_id)
        ) {
          nextList.push(messageEndEvent as IMessageEndEvent);
        }
        return nextList;
      });
    }
  }, [answerList]);

  return { findReferenceByMessageId };
}

interface UploadResponseDataType {
  created_at: number;
  created_by: string;
  extension: string;
  id: string;
  mime_type: string;
  name: string;
  preview_url: null;
  size: number;
}

export function useSetUploadResponseData() {
  const [uploadResponseList, setUploadResponseList] = useState<
    UploadResponseDataType[]
  >([]);
  const [fileList, setFileList] = useState<File[]>([]);

  const append = useCallback((data: UploadResponseDataType, files: File[]) => {
    setUploadResponseList((prev) => [...prev, data]);
    setFileList((pre) => [...pre, ...files]);
  }, []);

  const clear = useCallback(() => {
    setUploadResponseList([]);
    setFileList([]);
  }, []);

  const removeFile = useCallback((file: File) => {
    setFileList((prev) => prev.filter((f) => f !== file));
    setUploadResponseList((prev) =>
      prev.filter((item) => item.name !== file.name),
    );
  }, []);

  return {
    uploadResponseList,
    fileList,
    setUploadResponseList,
    appendUploadResponseList: append,
    clearUploadResponseList: clear,
    removeFile,
  };
}

export const buildRequestBody = (value: string = '') => {
  const id = uuid();
  const msgBody = {
    id,
    content: value.trim(),
    role: MessageType.User,
  };

  return msgBody;
};

export const useSendAgentMessage = ({
  url,
  addEventList,
  beginParams,
  isShared,
  refetch,
  isTaskMode: isTask,
  releaseMode,
  activeSessionId,
  recoveredRunId,
  onRunStatusChange,
  useBackgroundRun,
}: {
  url?: string;
  addEventList?: (data: IEventList, messageId: string) => void;
  beginParams?: BeginQuery[];
  isShared?: boolean;
  refetch?: () => void;
  isTaskMode?: boolean;
  releaseMode?: string | null;
  activeSessionId?: string;
  recoveredRunId?: string;
  onRunStatusChange?: (
    sessionId: string | null | undefined,
    running: boolean,
    runId?: string | null,
    runState?: Record<string, any> | null,
  ) => void;
  useBackgroundRun?: boolean;
}) => {
  const { id: agentId } = useParams();
  const { handleInputChange, value, setValue } = useHandleMessageInputChange();
  const inputs = useSelectBeginNodeDataInputs();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const {
    send,
    answerList,
    done,
    stopOutputMessage,
    resetAnswerList,
    replaceAnswerList,
  } = useSendMessageBySSE(url || api.agentChatCompletion);
  const firstAnswer = answerList[0];
  const messageId = useMemo(() => {
    return firstAnswer?.message_id;
  }, [firstAnswer]);
  const [streamSessionId, setStreamSessionId] = useState<string | null>(null);
  const [streamRunId, setStreamRunId] = useState<string | null>(null);
  const answerSessionId = firstAnswer?.session_id || streamSessionId;
  const answerRunId = firstAnswer?.run_id || streamRunId;
  const hasTerminalRunEvent = answerList.some(
    (event) =>
      event.event === MessageEventType.WorkflowFinished ||
      String(event.event) === 'workflow_failed' ||
      String(event.event) === 'workflow_canceled',
  );
  const isRecoveringRun = Boolean(answerRunId && done && !hasTerminalRunEvent);
  const isActiveAnswerVisible =
    !activeSessionId || !answerSessionId || activeSessionId === answerSessionId;

  const isTaskMode = useIsTaskMode(isTask);

  const { findReferenceByMessageId } = useFindMessageReference(answerList);
  const prologue = useGetBeginNodePrologue();
  const {
    derivedMessages,
    scrollRef,
    messageContainerRef,
    removeLatestMessage,
    removeMessageById,
    addNewestOneQuestion,
    addNewestOneAnswer,
    removeAllMessages,
    removeAllMessagesExceptFirst,
    scrollToBottom,
    addPrologue,
    setDerivedMessages,
  } = useSelectDerivedMessages();
  const { addEventList: addEventListFun } = useContext(AgentChatLogContext);
  const {
    appendUploadResponseList,
    clearUploadResponseList,
    uploadResponseList,
    fileList,
    removeFile,
  } = useSetUploadResponseData();

  const [searchParams] = useSearchParams();

  const userId = searchParams.get('userId');

  const { stopMessage } = useStopMessage();

  const stopConversation = useCallback(() => {
    const taskId = firstAnswer?.task_id;
    stopOutputMessage();
    if (!isShared) {
      stopMessage(taskId);
    }
  }, [firstAnswer, isShared, stopMessage, stopOutputMessage]);

  const sendMessage = useCallback(
    async ({
      message,
      beginInputs,
      exploreSessionId,
    }: {
      message: Message;
      messages?: Message[];
      beginInputs?: BeginQuery[];
      exploreSessionId?: string;
    }) => {
      const params: Record<string, unknown> = { agent_id: agentId };

      params.running_hint_text = i18n.t('flow.runningHintText', {
        defaultValue: 'is running...🕞',
      });
      params['openai-compatible'] = false;
      if (typeof message.content === 'string') {
        const query = inputs;

        params.query = message.content;
        // params.message_id = message.id;
        params.inputs = transferInputsArrayToObject(
          beginInputs || beginParams || query,
        ); // begin operator inputs

        params.files = uploadResponseList;

        // Prefer the session selected by the outer page state.
        // The hook keeps its own session cache for streamed replies, but that cache
        // can lag behind when the user switches sessions in Explore.
        const nextSessionId = exploreSessionId || sessionId;
        params.session_id = nextSessionId;
        setStreamSessionId(nextSessionId || null);
        if (releaseMode) {
          params.release = releaseMode;
        }

        if (userId) {
          params.user_id = userId;
        }
      }

      try {
        if (useBackgroundRun) {
          const res = await createBackgroundAgentRun(agentId!, params);
          const run = (res as any).data?.data ?? (res as any).data;
          if (!run?.run_id || !run?.session_id) {
            throw new Error('Failed to create background run');
          }
          setStreamSessionId(run.session_id);
          setStreamRunId(run.run_id);
          replaceAnswerList([]);
          onRunStatusChange?.(run.session_id, true, run.run_id, run);
          clearUploadResponseList();
          refetch?.();
          return;
        }

        const res = await send(params);

        clearUploadResponseList();

        if (receiveMessageError(res)) {
          sonnerMessage.error((res?.data as any)?.message);

          // cancel loading
          setValue(message.content);
          removeLatestMessage();
        } else {
          refetch?.(); // pull the message list after sending the message successfully
        }
      } catch {
        sonnerMessage.error(
          i18n.t('message.sendFailed', {
            defaultValue: 'Failed to send message',
          }),
        );
      }
    },
    [
      agentId,
      inputs,
      beginParams,
      uploadResponseList,
      sessionId,
      releaseMode,
      userId,
      send,
      clearUploadResponseList,
      setValue,
      removeLatestMessage,
      refetch,
      onRunStatusChange,
      replaceAnswerList,
      useBackgroundRun,
    ],
  );

  const sendFormMessage = useCallback(
    async (body: { inputs: Record<string, BeginQuery> }) => {
      addNewestOneQuestion({
        content: Object.entries(body.inputs)
          .map(([, val]) => `${val.name}: ${val.value}`)
          .join('<br/>'),
        role: MessageType.User,
      });
      await send({
        ...body,
        ...(isShared ? {} : { agent_id: agentId }),
        session_id: sessionId,
        ...(releaseMode ? { release: releaseMode } : {}),
      });
      refetch?.();
    },
    [
      addNewestOneQuestion,
      agentId,
      isShared,
      refetch,
      releaseMode,
      send,
      sessionId,
    ],
  );

  // reset session
  const resetSession = useCallback(() => {
    stopConversation();
    resetAnswerList();
    setSessionId(null);
    if (isTaskMode) {
      removeAllMessages();
    } else {
      removeAllMessagesExceptFirst();
    }
  }, [
    stopConversation,
    resetAnswerList,
    isTaskMode,
    removeAllMessages,
    removeAllMessagesExceptFirst,
  ]);

  const handlePressEnter = useCallback(
    ({
      exploreSessionId,
    }: Partial<NextMessageInputOnPressEnterParameter> & {
      exploreSessionId?: string;
    } = {}) => {
      if (trim(value) === '') return;
      const msgBody = buildRequestBody(value);
      const classification = classify_generation_task(value);
      addNewestOneQuestion({ ...msgBody, files: fileList });
      if (done) {
        setValue('');
        if (classification.shouldGenerateDocument) {
          addNewestOneAnswer({
            id: msgBody.id,
            answer: buildLongTaskPreview(classification),
            data: {
              longTask: {
                ...classification,
                query: value.trim(),
                agentId,
                source: 'agent',
              },
            },
          });
          clearUploadResponseList();
          setTimeout(() => {
            scrollToBottom();
          }, 100);
          return;
        }

        sendMessage({
          message: msgBody,
          exploreSessionId,
        });
      }
      setTimeout(() => {
        scrollToBottom();
      }, 100);
    },
    [
      value,
      done,
      addNewestOneQuestion,
      addNewestOneAnswer,
      fileList,
      setValue,
      sendMessage,
      scrollToBottom,
      agentId,
      clearUploadResponseList,
    ],
  );

  const continueMessage = useCallback(() => {
    if (!done) return;

    const msgBody = buildRequestBody(
      i18n.t('chat.continueInstruction', {
        defaultValue:
          'Continue from where the previous answer stopped. Do not repeat content already shown.',
      }),
    );
    addNewestOneQuestion(msgBody);
    sendMessage({ message: msgBody });
    setTimeout(() => {
      scrollToBottom();
    }, 100);
  }, [addNewestOneQuestion, done, scrollToBottom, sendMessage]);

  const sendedTaskMessage = useRef(false);

  const sendMessageInTaskMode = useCallback(() => {
    if (isShared || !isTaskMode || sendedTaskMessage.current) {
      return;
    }
    const msgBody = buildRequestBody('');

    sendMessage({
      message: msgBody,
    });
    sendedTaskMessage.current = true;
  }, [isShared, isTaskMode, sendMessage]);

  useEffect(() => {
    sendMessageInTaskMode();
  }, [sendMessageInTaskMode]);

  useEffect(() => {
    if (!isActiveAnswerVisible) {
      return;
    }
    const { content, id, attachment, audio_binary, downloads } =
      findMessageFromList(answerList);
    const inputAnswer = findInputFromList(answerList);
    const answer = content || getLatestError(answerList);

    if (answerList.length > 0) {
      const shouldSplit = shouldSplitMessage(answerList, content);

      if (shouldSplit) {
        addNewestOneAnswer({
          answer: answer ?? '',
          audio_binary: audio_binary,
          attachment: attachment as IAttachment,
          downloads,
          id,
        });
        addNewestOneAnswer({
          answer: '',
          ...inputAnswer,
          id: `${id}${MessageWaitSuffix}`,
        });
      } else {
        addNewestOneAnswer({
          answer: answer ?? '',
          audio_binary: audio_binary,
          attachment: attachment as IAttachment,
          downloads,
          id,
          ...inputAnswer,
        });
      }
    }
  }, [answerList, addNewestOneAnswer, isActiveAnswerVisible]);

  useEffect(() => {
    if (isTaskMode) {
      return;
    }
    if (prologue) {
      addPrologue(prologue);
    }
  }, [
    addNewestOneAnswer,
    addPrologue,
    agentId,
    isTaskMode,
    prologue,
    send,
    sendFormMessage,
  ]);

  useEffect(() => {
    if (typeof addEventList === 'function') {
      addEventList(answerList, messageId);
    } else if (typeof addEventListFun === 'function') {
      addEventListFun(answerList, messageId);
    }
  }, [addEventList, answerList, addEventListFun, messageId]);

  useEffect(() => {
    if (firstAnswer?.session_id) {
      setSessionId(firstAnswer.session_id);
      setStreamSessionId(firstAnswer.session_id);
    }
    if (firstAnswer?.run_id) {
      setStreamRunId(firstAnswer.run_id);
    }
  }, [firstAnswer]);

  useEffect(() => {
    if (!activeSessionId) {
      return;
    }
    if (recoveredRunId) {
      setStreamRunId(recoveredRunId);
      setStreamSessionId(activeSessionId);
      return;
    }
    setStreamRunId(null);
    setStreamSessionId(activeSessionId);
    replaceAnswerList([]);
  }, [activeSessionId, recoveredRunId, replaceAnswerList]);

  useEffect(() => {
    onRunStatusChange?.(answerSessionId, !done || isRecoveringRun, answerRunId);
  }, [answerRunId, answerSessionId, done, isRecoveringRun, onRunStatusChange]);

  useEffect(() => {
    if (!answerRunId || !done || !isActiveAnswerVisible) {
      return;
    }
    if (hasTerminalRunEvent) {
      return;
    }

    let cancelled = false;
    let clearRecoveryTimer = () => {};
    const fetchSnapshot = async () => {
      try {
        const response = await fetchAgentRunEvents(answerRunId, -1);
        const data = (response as any).data?.data ?? (response as any).data;
        if (cancelled || !data?.events?.length) {
          return;
        }
        replaceAnswerList(
          data.events.map(
            (item: { event: Record<string, any> }) => item.event,
          ) as IEventList,
        );
        if (data.state?.session_id) {
          setStreamSessionId(data.state.session_id);
        }
        if (data.state?.run_id) {
          setStreamRunId(data.state.run_id);
        }
        if (data.state?.session_id && data.state?.run_id) {
          const running = ['queued', 'running', 'cancel_requested'].includes(
            data.state.status,
          );
          onRunStatusChange?.(
            data.state.session_id,
            running,
            data.state.run_id,
            data.state,
          );
        }
        if (
          data.state?.status &&
          !['queued', 'running', 'cancel_requested'].includes(data.state.status)
        ) {
          cancelled = true;
          clearRecoveryTimer();
        }
      } catch {
        // Keep polling; transient recovery failures should not interrupt the chat UI.
      }
    };

    fetchSnapshot();
    const timer = window.setInterval(fetchSnapshot, 3000);
    clearRecoveryTimer = () => window.clearInterval(timer);
    return () => {
      cancelled = true;
      clearRecoveryTimer();
    };
  }, [
    answerList,
    answerRunId,
    done,
    hasTerminalRunEvent,
    isActiveAnswerVisible,
    onRunStatusChange,
    replaceAnswerList,
  ]);

  return {
    value,
    sendLoading: (!done || isRecoveringRun) && isActiveAnswerVisible,
    backgroundSendLoading: (!done || isRecoveringRun) && !isActiveAnswerVisible,
    derivedMessages,
    scrollRef,
    messageContainerRef,
    handlePressEnter,
    continueMessage,
    handleInputChange,
    removeMessageById,
    stopOutputMessage: stopConversation,
    send,
    sendFormMessage,
    resetSession,
    findReferenceByMessageId,
    appendUploadResponseList,
    addNewestOneAnswer,
    sendMessage,
    removeFile,
    setDerivedMessages,
    addPrologue,
  };
};
