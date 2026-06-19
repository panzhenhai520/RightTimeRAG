import { MessageType } from '@/constants/chat';

import { useSendAgentMessage } from './use-send-agent-message';

import { FileUploadProps } from '@/components/file-upload';
import { NextMessageInput } from '@/components/message-input/next';
import MarkdownContent from '@/components/next-markdown-content';
import MessageItem from '@/components/next-message-item';
import PdfSheet from '@/components/pdf-drawer';
import { useClickDrawer } from '@/components/pdf-drawer/hooks';
import { TtsPlaybackConsent } from '@/components/tts-playback-consent';
import {
  useFetchAgent,
  useUploadAgentFileWithProgress,
} from '@/hooks/use-agent-request';
import { usePanythonTtsEngineSettings } from '@/hooks/use-panython-tts-settings';
import { useFetchUserInfo } from '@/hooks/use-user-setting-request';
import { buildMessageUuidWithRole } from '@/utils/chat';
import { memo, useCallback, useContext, useMemo } from 'react';
import { AgentChatContext } from '../context';
import DebugContent from '../debug-content';
import { useAwaitComponentData } from '../hooks/use-chat-logic';
import { useIsTaskMode } from '../hooks/use-get-begin-query';
import { useGetFileIcon } from './use-get-file-icon';

function AgentChatBox() {
  const { data: canvasInfo, refetch } = useFetchAgent();
  const {
    value,
    scrollRef,
    messageContainerRef,
    sendLoading,
    derivedMessages,
    handleInputChange,
    handlePressEnter,
    continueMessage,
    stopOutputMessage,
    sendFormMessage,
    findReferenceByMessageId,
    appendUploadResponseList,
    removeFile,
  } = useSendAgentMessage({ refetch });

  const { visible, hideModal, documentId, selectedChunk, clickDocumentButton } =
    useClickDrawer();
  useGetFileIcon();
  const { data: userInfo } = useFetchUserInfo();
  const { settings: ttsEngineSettings } = usePanythonTtsEngineSettings();
  const agentTtsConfig = useMemo(() => {
    if (!ttsEngineSettings.tts_enabled) return undefined;
    return {
      speed: ttsEngineSettings.default_speed,
      emotion: ttsEngineSettings.default_emotion,
      dialect: ttsEngineSettings.default_dialect,
      gender: ttsEngineSettings.default_gender,
      voice_profile: ttsEngineSettings.default_voice_profile,
      sync_caption: ttsEngineSettings.supports_sync_caption,
    };
  }, [ttsEngineSettings]);
  const { uploadAgentFile, loading } = useUploadAgentFileWithProgress();

  const { buildInputList, handleOk, isWaiting } = useAwaitComponentData({
    derivedMessages,
    sendFormMessage,
  });

  const { setDerivedMessages } = useContext(AgentChatContext);
  setDerivedMessages?.(derivedMessages);

  const isTaskMode = useIsTaskMode();

  const handleUploadFile: NonNullable<FileUploadProps['onUpload']> =
    useCallback(
      async (files, options) => {
        const ret = await uploadAgentFile({ files, options });
        appendUploadResponseList(ret.data, files);
      },
      [appendUploadResponseList, uploadAgentFile],
    );

  return (
    <>
      <section className="flex flex-1 flex-col px-5 min-h-0 pb-4">
        <div className="flex-1 overflow-auto" ref={messageContainerRef}>
          <div>
            {!sendLoading && <div data-testid="agent-run-idle" />}
            {/* <Spin spinning={sendLoading}> */}
            {derivedMessages?.map((message, i) => {
              return (
                <MessageItem
                  loading={
                    message.role === MessageType.Assistant &&
                    sendLoading &&
                    derivedMessages.length - 1 === i
                  }
                  key={buildMessageUuidWithRole(message)}
                  nickname={userInfo.nickname}
                  avatar={userInfo.avatar}
                  avatarDialog={canvasInfo.avatar}
                  ttsConfig={agentTtsConfig}
                  item={message}
                  reference={findReferenceByMessageId(message.id)}
                  clickDocumentButton={clickDocumentButton}
                  index={i}
                  showLikeButton={false}
                  sendLoading={sendLoading}
                  continueMessage={continueMessage}
                >
                  {message.role === MessageType.Assistant &&
                    derivedMessages.length - 1 === i && (
                      <DebugContent
                        parameters={buildInputList(message)}
                        message={message}
                        ok={handleOk(message)}
                        isNext={false}
                        btnText={'Submit'}
                      ></DebugContent>
                    )}
                  {message.role === MessageType.Assistant &&
                    derivedMessages.length - 1 !== i && (
                      <div>
                        <MarkdownContent
                          content={message?.data?.tips}
                          loading={false}
                        ></MarkdownContent>
                        <div>
                          {buildInputList(message)?.map((item) => item.value)}
                        </div>
                      </div>
                    )}
                </MessageItem>
              );
            })}
            {/* </Spin> */}
          </div>
          <div ref={scrollRef} />
        </div>
        {isTaskMode || (
          <>
            <TtsPlaybackConsent
              enabled={ttsEngineSettings.tts_enabled}
              className="mb-3"
            />
            <NextMessageInput
              value={value}
              sendLoading={sendLoading}
              disabled={isWaiting}
              sendDisabled={sendLoading || isWaiting}
              isUploading={loading || isWaiting}
              resize="vertical"
              onPressEnter={handlePressEnter}
              onInputChange={handleInputChange}
              stopOutputMessage={stopOutputMessage}
              onUpload={handleUploadFile}
              removeFile={removeFile}
              conversationId=""
            />
          </>
        )}
      </section>
      {visible && (
        <PdfSheet
          visible={visible}
          hideModal={hideModal}
          documentId={documentId}
          chunk={selectedChunk}
        ></PdfSheet>
      )}
    </>
  );
}

export default memo(AgentChatBox);
