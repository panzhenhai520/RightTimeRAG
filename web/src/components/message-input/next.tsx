'use client';

import {
  FileUpload,
  FileUploadDropzone,
  FileUploadItem,
  FileUploadItemDelete,
  FileUploadItemMetadata,
  FileUploadItemPreview,
  FileUploadItemProgress,
  FileUploadList,
  FileUploadTrigger,
  type FileUploadProps,
} from '@/components/file-upload';
import { Button } from '@/components/ui/button';
import { RAGFlowSelect, RAGFlowSelectOptionType } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { useFetchKnowledgeList } from '@/hooks/use-knowledge-request';
import { cn } from '@/lib/utils';
import { t } from 'i18next';
import {
  Atom,
  ArrowUp,
  BookMarked,
  CircleStop,
  Globe,
  Paperclip,
  Upload,
  X,
} from 'lucide-react';
import * as React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { AudioButton } from '../ui/audio-button';

const DEFAULT_KB_SELECTION = '__default__';
const NO_KB_SELECTION = '__none__';

export type NextMessageInputOnPressEnterParameter = {
  enableThinking: boolean;
  enableInternet: boolean;
  selectedKnowledgeBaseId?: string;
};

interface NextMessageInputProps {
  disabled: boolean;
  value: string;
  sendDisabled: boolean;
  sendLoading: boolean;
  conversationId: string;
  uploadMethod?: string;
  isShared?: boolean;
  showUploadIcon?: boolean;
  isUploading?: boolean;
  onPressEnter({
    enableThinking,
    enableInternet,
  }: NextMessageInputOnPressEnterParameter): void;
  onInputChange: React.ChangeEventHandler<HTMLTextAreaElement>;
  createConversationBeforeUploadDocument?(message: string): Promise<any>;
  stopOutputMessage?(): void;
  onAddToMemory?(): void;
  onUpload?: NonNullable<FileUploadProps['onUpload']>;
  removeFile?(file: File): void;
  showReasoning?: boolean;
  showInternet?: boolean;
  addToMemoryLoading?: boolean;
  resize?: 'none' | 'vertical' | 'horizontal' | 'both';
}

export function NextMessageInput({
  isUploading = false,
  value,
  sendDisabled,
  sendLoading,
  disabled,
  showUploadIcon = true,
  onUpload,
  onInputChange,
  stopOutputMessage,
  onAddToMemory,
  onPressEnter,
  removeFile,
  showReasoning = false,
  showInternet = false,
  addToMemoryLoading = false,
}: NextMessageInputProps) {
  const [files, setFiles] = React.useState<File[]>([]);
  const [audioInputValue, setAudioInputValue] = React.useState<string | null>(
    null,
  );

  const [enableThinking, setEnableThinking] = useState(false);
  const [enableInternet, setEnableInternet] = useState(false);
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] =
    useState(DEFAULT_KB_SELECTION);
  const { list: knowledgeBaseList } = useFetchKnowledgeList(true);

  const knowledgeBaseOptions = useMemo<RAGFlowSelectOptionType[]>(
    () => [
      {
        value: DEFAULT_KB_SELECTION,
        label: `${t('chat.knowledgeBases')}: ${t('knowledgeConfiguration.default')}`,
      },
      {
        value: NO_KB_SELECTION,
        label: `${t('chat.knowledgeBases')}: ${t('datasetOverview.none')}`,
      },
      ...knowledgeBaseList.map((kb) => ({
        value: kb.id,
        label: kb.name,
      })),
    ],
    [knowledgeBaseList],
  );

  const handleThinkingToggle = useCallback(() => {
    setEnableThinking((prev) => !prev);
  }, []);

  const handleInternetToggle = useCallback(() => {
    setEnableInternet((prev) => !prev);
  }, []);

  const pressEnter = useCallback(() => {
    onPressEnter({
      enableThinking,
      enableInternet: showInternet ? enableInternet : false,
      selectedKnowledgeBaseId:
        selectedKnowledgeBaseId === DEFAULT_KB_SELECTION
          ? undefined
          : selectedKnowledgeBaseId,
    });
  }, [
    onPressEnter,
    enableThinking,
    enableInternet,
    showInternet,
    selectedKnowledgeBaseId,
  ]);

  useEffect(() => {
    if (audioInputValue !== null) {
      onInputChange({
        target: { value: audioInputValue },
      } as React.ChangeEvent<HTMLTextAreaElement>);

      setTimeout(() => {
        pressEnter();
        setAudioInputValue(null);
      }, 0);
    }
  }, [
    audioInputValue,
    onInputChange,
    onPressEnter,
    enableThinking,
    enableInternet,
    showInternet,
    pressEnter,
  ]);

  const onFileReject = React.useCallback((file: File, message: string) => {
    toast(message, {
      description: `"${file.name.length > 20 ? `${file.name.slice(0, 20)}...` : file.name}" has been rejected`,
    });
  }, []);

  const submit = React.useCallback(() => {
    if (isUploading) return;
    pressEnter();
    setFiles([]);
  }, [isUploading, pressEnter]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const onSubmit = React.useCallback(
    (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      submit();
    },
    [submit],
  );

  const handleRemoveFile = React.useCallback(
    (file: File) => () => {
      removeFile?.(file);
    },
    [removeFile],
  );

  return (
    <FileUpload
      value={files}
      onValueChange={setFiles}
      onUpload={onUpload}
      onFileReject={onFileReject}
      className="relative w-full items-center"
      disabled={isUploading || disabled}
    >
      <FileUploadDropzone
        tabIndex={-1}
        // Prevents the dropzone from triggering on click
        onClick={(event) => event.preventDefault()}
        className="absolute top-0 left-0 z-0 flex size-full items-center justify-center rounded-none border-none bg-background/50 p-0 opacity-0 backdrop-blur transition-opacity duration-200 ease-out data-[dragging]:z-10 data-[dragging]:opacity-100"
      >
        <div className="flex flex-col items-center gap-1 text-center">
          <div className="flex items-center justify-center rounded-full border p-2.5">
            <Upload className="size-6 text-muted-foreground" />
          </div>
          <p className="font-medium text-sm">Drag & drop files here</p>
          <p className="text-muted-foreground text-xs">
            Upload max 5 files each up to 5MB
          </p>
        </div>
      </FileUploadDropzone>

      <form
        onSubmit={onSubmit}
        className="
          relative flex w-full flex-col gap-2.5 rounded-2xl
          border border-border-default bg-white/58 p-3 outline-none shadow-sm backdrop-blur transition-colors
          dark:border-[#9fd0ea]/34 dark:bg-[#dceef8]/8 dark:shadow-[0_12px_34px_rgba(4,25,39,0.2)]
          has-[textarea:focus]:border-[#895668]/55 has-[textarea:focus]:shadow-[0_0_0_3px_rgba(137,86,104,0.12)]
          dark:has-[textarea:focus]:border-[#80bddf]/60 dark:has-[textarea:focus]:shadow-[0_0_0_3px_rgba(91,159,199,0.18)]
        "
      >
        <FileUploadList
          orientation="horizontal"
          className="overflow-x-auto px-0 py-1"
        >
          {files.map((file, index) => (
            <FileUploadItem key={index} value={file} className="max-w-52 p-1.5">
              <FileUploadItemPreview className="size-8 [&>svg]:size-5">
                <FileUploadItemProgress variant="fill" />
              </FileUploadItemPreview>
              <FileUploadItemMetadata size="sm" />
              <FileUploadItemDelete asChild>
                <Button
                  variant="secondary"
                  size="icon"
                  className="-top-1 -right-1 absolute size-4 shrink-0 cursor-pointer rounded-full"
                  onClick={handleRemoveFile(file)}
                >
                  <X className="size-2.5" />
                </Button>
              </FileUploadItemDelete>
            </FileUploadItem>
          ))}
        </FileUploadList>

        <Textarea
          data-testid="chat-textarea"
          value={value}
          onChange={onInputChange}
          placeholder={t('chat.messagePlaceholder')}
          className="
            min-h-10 max-h-40 w-full p-0 overflow-auto text-[#132330] placeholder:text-[#758894]
            dark:text-[#edf7fb] dark:placeholder:text-[#a9c4d3]
            !outline-none !border-transparent !bg-transparent !shadow-none !ring-transparent !ring-offset-transparent
          "
          disabled={isUploading || disabled || sendLoading}
          onKeyDown={handleKeyDown}
          autoSize={{ minRows: 2, maxRows: 8 }}
        />

        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            {showUploadIcon && (
              <FileUploadTrigger asChild>
                <Button
                  type="button"
                  size="icon-xs"
                  variant="transparent"
                  className="rounded-full border-0 text-[#425867] hover:bg-[#e6edf1] dark:text-[#cfe6f2] dark:hover:bg-[#dceef8]/14"
                  disabled={isUploading || sendLoading}
                  data-testid="chat-detail-attach"
                >
                  <Paperclip className="size-3.5" />
                  <span className="sr-only">Attach file</span>
                </Button>
              </FileUploadTrigger>
            )}

            {showReasoning && (
              <Button
                type="button"
                size="sm"
                variant={'outline'}
                className={cn(
                  'h-7 border-0 bg-[#8b4c36]/8 text-sm text-[#6f3f2f] hover:bg-[#8b4c36]/14 dark:bg-[#dceef8]/10 dark:text-[#d6eefb] dark:hover:bg-[#dceef8]/16',
                  {
                    'bg-[#79394d] text-white hover:bg-[#8f4660] dark:bg-[#2d5f80] dark:text-white dark:hover:bg-[#376f94]':
                      enableThinking,
                  },
                )}
                onClick={handleThinkingToggle}
                data-testid="chat-detail-thinking-toggle"
              >
                <Atom />
                <span>{t('chat.deepThinking')}</span>
              </Button>
            )}

            <RAGFlowSelect
              value={selectedKnowledgeBaseId}
              onChange={setSelectedKnowledgeBaseId}
              options={knowledgeBaseOptions}
              triggerClassName="h-7 w-44 border-0 bg-[#8b4c36]/8 text-xs text-[#6f3f2f] hover:bg-[#8b4c36]/14 dark:bg-[#dceef8]/10 dark:text-[#d6eefb] dark:hover:bg-[#dceef8]/16"
              contentProps={{ className: 'max-w-80' }}
              triggerTestId="chat-detail-kb-select"
              optionTestIdPrefix="chat-detail-kb-option"
            />

            {onAddToMemory && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-7 border-[#8b4c36]/25 bg-[#8b4c36]/8 px-2 text-sm text-[#6f3f2f] hover:bg-[#8b4c36]/14 dark:border-[#9fd0ea]/30 dark:bg-[#dceef8]/10 dark:text-[#d6eefb] dark:hover:bg-[#dceef8]/16"
                onClick={onAddToMemory}
                disabled={addToMemoryLoading || sendLoading}
                title={t('chat.addToMemory')}
                data-testid="chat-detail-add-memory"
              >
                <BookMarked />
                <span>{t('chat.addToMemory')}</span>
              </Button>
            )}

            {showInternet && (
              <Button
                type="button"
                variant={enableInternet ? 'accent' : 'transparent'}
                size="icon-xs"
                className="border-0"
                onClick={handleInternetToggle}
                data-testid="chat-detail-internet-toggle"
              >
                <Globe />
              </Button>
            )}
          </div>

          {sendLoading ? (
            <Button
              data-testid="chat-stream-status"
              onClick={stopOutputMessage}
                size="icon-xs"
                className="rounded-full bg-[#79394d] hover:bg-[#8f4660] dark:bg-[#2d5f80] dark:hover:bg-[#376f94]"
            >
              <CircleStop />
            </Button>
          ) : (
            <div className="flex items-center gap-3">
              <AudioButton
                onOk={(value) => {
                  setAudioInputValue(value);
                }}
                testId="chat-detail-audio-toggle"
              />

              <Button
                size="icon"
                className="
                  size-8 rounded-full bg-[#79394d] text-white shadow-sm
                  hover:bg-[#8f4660] disabled:bg-[#c9d3d9] disabled:text-white
                  dark:bg-[#2d5f80] dark:hover:bg-[#376f94] dark:disabled:bg-[#486273] dark:disabled:text-[#c0d2dc]
                "
                disabled={
                  sendDisabled || isUploading || sendLoading || !value.trim()
                }
                data-testid="chat-detail-send"
              >
                <ArrowUp className="size-4 stroke-[2.4]" />
                <span className="sr-only">Send message</span>
              </Button>
            </div>
          )}
        </div>
      </form>
    </FileUpload>
  );
}
