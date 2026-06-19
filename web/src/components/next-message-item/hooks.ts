// import { useDeleteMessage, useFeedback } from '@/hooks/chat-hooks';
import { useSetModalState } from '@/hooks/common-hooks';
import {
  IRemoveMessageById,
  useSpeechSyncJob,
  useSpeechWithSse,
} from '@/hooks/logic-hooks';
import { useDeleteMessage, useFeedback } from '@/hooks/use-chat-request';
import { IFeedbackRequestBody } from '@/interfaces/request/chat';
import { getTtsReadableContent } from '@/utils/chat';
import { hexStringToUint8Array } from '@/utils/common-util';
import { useCallback, useEffect, useRef, useState } from 'react';

const TTS_SYNC_POLL_INTERVAL_MS = 600;
const TTS_SYNC_MAX_POLLS = 240;

type TtsSyncSegment = {
  index?: number;
  text?: string;
  status?: string;
  mimetype?: string;
  audio_hex?: string;
};

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export const useSendFeedback = (messageId: string) => {
  const { visible, hideModal, showModal } = useSetModalState();
  const { feedback, loading } = useFeedback();

  const onFeedbackOk = useCallback(
    async (params: IFeedbackRequestBody) => {
      const ret = await feedback({
        ...params,
        messageId: messageId,
      });

      if (ret === 0) {
        hideModal();
      }
    },
    [feedback, hideModal, messageId],
  );

  return {
    loading,
    onFeedbackOk,
    visible,
    hideModal,
    showModal,
  };
};

export const useRemoveMessage = (
  messageId: string,
  removeMessageById?: IRemoveMessageById['removeMessageById'],
) => {
  const { deleteMessage, loading } = useDeleteMessage();

  const onRemoveMessage = useCallback(async () => {
    if (messageId) {
      const code = await deleteMessage(messageId);
      if (code === 0) {
        removeMessageById?.(messageId);
      }
    }
  }, [deleteMessage, messageId, removeMessageById]);

  return { onRemoveMessage, loading };
};

export const useSpeech = (
  content: string,
  audioBinary?: string,
  ttsConfig?: Record<string, unknown>,
) => {
  const ref = useRef<HTMLAudioElement>(null);
  const { read } = useSpeechWithSse();
  const { create: createSyncJob, poll: pollSyncJob } = useSpeechSyncJob();
  const audioUrlRef = useRef<string>();
  const requestIdRef = useRef(0);
  const loadingTimerRef = useRef<number>();
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const clearLoadingTimer = useCallback(() => {
    if (loadingTimerRef.current) {
      window.clearTimeout(loadingTimerRef.current);
      loadingTimerRef.current = undefined;
    }
  }, []);

  const revokeAudioUrl = useCallback(() => {
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = undefined;
    }
  }, []);

  const pause = useCallback(() => {
    requestIdRef.current += 1;
    ref.current?.pause();
    clearLoadingTimer();
    setIsLoading(false);
    setIsPlaying(false);
  }, [clearLoadingTimer]);

  const playAudioBlob = useCallback(
    async (blob: Blob, requestId: number) => {
      if (requestIdRef.current !== requestId || !blob.size) return;
      revokeAudioUrl();
      const audioUrl = URL.createObjectURL(blob);
      audioUrlRef.current = audioUrl;
      const audio = ref.current;
      if (!audio) throw new Error('Audio element is not ready.');
      audio.src = audioUrl;
      audio.load();

      await new Promise<void>((resolve, reject) => {
        let cleanup = () => {};
        const handlePlaying = () => {
          if (requestIdRef.current === requestId) {
            clearLoadingTimer();
            setIsLoading(false);
            setIsPlaying(true);
          }
        };
        const handleFinished = () => {
          cleanup();
          resolve();
        };
        const handleError = () => {
          cleanup();
          reject(new Error('Audio playback failed.'));
        };
        cleanup = () => {
          audio.removeEventListener('ended', handleFinished);
          audio.removeEventListener('pause', handleFinished);
          audio.removeEventListener('error', handleError);
          audio.removeEventListener('playing', handlePlaying);
        };

        audio.addEventListener('ended', handleFinished);
        audio.addEventListener('pause', handleFinished);
        audio.addEventListener('error', handleError);
        audio.addEventListener('playing', handlePlaying);
        audio.play().catch((error) => {
          cleanup();
          reject(error);
        });
      });
    },
    [clearLoadingTimer, revokeAudioUrl],
  );

  const playSyncSegment = useCallback(
    async (segment: TtsSyncSegment, requestId: number) => {
      if (!segment.audio_hex || requestIdRef.current !== requestId) return;
      const units = hexStringToUint8Array(segment.audio_hex);
      if (!units) return;
      await playAudioBlob(
        new Blob([units], { type: segment.mimetype || 'audio/wav' }),
        requestId,
      );
    },
    [playAudioBlob],
  );

  const speechSync = useCallback(
    async (readableContent: string, requestId: number) => {
      const payload = await createSyncJob({
        text: readableContent,
        tts_config: ttsConfig || { sync_caption: true },
      });
      if (requestIdRef.current !== requestId || payload?.code !== 0) {
        return false;
      }

      const jobId = payload?.data?.job_id;
      if (!jobId) return false;

      let nextSegmentIndex = 0;
      for (let pollCount = 0; pollCount < TTS_SYNC_MAX_POLLS; pollCount += 1) {
        if (requestIdRef.current !== requestId) return true;
        const jobPayload = await pollSyncJob(jobId);
        const job = jobPayload?.data;
        const segments = (job?.segments || []) as TtsSyncSegment[];

        while (
          requestIdRef.current === requestId &&
          nextSegmentIndex < segments.length &&
          segments[nextSegmentIndex]?.status === 'ready' &&
          segments[nextSegmentIndex]?.audio_hex
        ) {
          await playSyncSegment(segments[nextSegmentIndex], requestId);
          nextSegmentIndex += 1;
        }

        if (job?.status === 'complete' && nextSegmentIndex >= segments.length) {
          return true;
        }
        if (job?.status === 'error') return false;
        await wait(TTS_SYNC_POLL_INTERVAL_MS);
      }

      return false;
    },
    [createSyncJob, pollSyncJob, playSyncSegment, ttsConfig],
  );

  const speech = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    clearLoadingTimer();
    setIsLoading(true);
    setIsPlaying(false);
    loadingTimerRef.current = window.setTimeout(() => {
      if (requestIdRef.current === requestId) {
        ref.current?.pause();
        setIsLoading(false);
        setIsPlaying(false);
      }
    }, 120000);

    try {
      const readableContent = getTtsReadableContent(content);
      if (!readableContent) {
        setIsPlaying(false);
        setIsLoading(false);
        clearLoadingTimer();
        return;
      }

      if ((ttsConfig as any)?.sync_caption) {
        const synchronized = await speechSync(readableContent, requestId);
        if (requestIdRef.current !== requestId) return;
        if (synchronized) {
          clearLoadingTimer();
          setIsLoading(false);
          setIsPlaying(false);
          return;
        }
      }

      const response = await read({
        text: readableContent,
        ...(ttsConfig ? { tts_config: ttsConfig } : {}),
      });
      if (requestIdRef.current !== requestId) return;
      if (!response || !response.ok) {
        setIsPlaying(false);
        setIsLoading(false);
        clearLoadingTimer();
        return;
      }

      const blob = await response.blob();
      if (requestIdRef.current !== requestId) return;
      if (!blob.size) {
        setIsPlaying(false);
        setIsLoading(false);
        clearLoadingTimer();
        return;
      }

      await playAudioBlob(blob, requestId);
      if (requestIdRef.current === requestId) {
        clearLoadingTimer();
        setIsLoading(false);
        setIsPlaying(true);
      }
    } catch (error) {
      console.error('Speech request failed:', error);
      if (requestIdRef.current === requestId) {
        clearLoadingTimer();
        setIsPlaying(false);
        setIsLoading(false);
      }
    }
  }, [clearLoadingTimer, read, content, playAudioBlob, speechSync, ttsConfig]);

  const handleRead = useCallback(async () => {
    if (isPlaying || isLoading) {
      setIsPlaying(false);
      pause();
    } else {
      speech();
    }
  }, [setIsPlaying, speech, isPlaying, isLoading, pause]);

  useEffect(() => {
    if (audioBinary) {
      const units = hexStringToUint8Array(audioBinary);
      if (units) {
        try {
          revokeAudioUrl();
          const audioUrl = URL.createObjectURL(
            new Blob([units], { type: 'audio/wav' }),
          );
          audioUrlRef.current = audioUrl;
          const audio = ref.current;
          if (audio) {
            audio.src = audioUrl;
            audio.load();
            audio.play().catch((error) => {
              console.warn(error);
            });
          }
        } catch (error) {
          console.warn(error);
        }
      }
    }
  }, [audioBinary, revokeAudioUrl]);

  useEffect(() => {
    const audio = ref.current;
    if (!audio) return;

    const handlePlaying = () => {
      clearLoadingTimer();
      setIsLoading(false);
      setIsPlaying(true);
    };
    const handleFinished = () => {
      clearLoadingTimer();
      setIsLoading(false);
      setIsPlaying(false);
    };

    audio.addEventListener('playing', handlePlaying);
    audio.addEventListener('pause', handleFinished);
    audio.addEventListener('ended', handleFinished);
    audio.addEventListener('error', handleFinished);

    return () => {
      audio.removeEventListener('playing', handlePlaying);
      audio.removeEventListener('pause', handleFinished);
      audio.removeEventListener('ended', handleFinished);
      audio.removeEventListener('error', handleFinished);
      clearLoadingTimer();
      revokeAudioUrl();
    };
  }, [clearLoadingTimer, revokeAudioUrl]);

  return {
    ref,
    handleRead,
    isPlaying,
    isLoading,
    speechState: isLoading ? 'loading' : isPlaying ? 'playing' : 'idle',
  };
};
