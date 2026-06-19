import { useSetModalState } from '@/hooks/common-hooks';
import { IRemoveMessageById, useSpeechWithSse } from '@/hooks/logic-hooks';
import { useDeleteMessage, useFeedback } from '@/hooks/use-chat-request';
import { IFeedbackRequestBody } from '@/interfaces/request/chat';
import { getTtsReadableContent } from '@/utils/chat';
import { hexStringToUint8Array } from '@/utils/common-util';
import { useCallback, useEffect, useRef, useState } from 'react';

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

export const useSpeech = (content: string, audioBinary?: string) => {
  const ref = useRef<HTMLAudioElement>(null);
  const { read } = useSpeechWithSse();
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

      const response = await read({ text: readableContent });
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

      revokeAudioUrl();
      const audioUrl = URL.createObjectURL(blob);
      audioUrlRef.current = audioUrl;
      const audio = ref.current;
      if (!audio) throw new Error('Audio element is not ready.');
      audio.src = audioUrl;
      audio.load();
      await audio.play();
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
  }, [clearLoadingTimer, read, content, revokeAudioUrl]);

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
