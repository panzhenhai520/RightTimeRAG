import { DocumentDownloadButton } from '@/components/document-download-button';
import { Button } from '@/components/ui/button';
import message from '@/components/ui/message';
import { IDocumentDownloadInfo, IMessage } from '@/interfaces/database/chat';
import i18n from '@/locales/config';
import api from '@/utils/api';
import { isAnswerTruncated } from '@/utils/generation-task';
import request from '@/utils/next-request';
import { FileDown, Loader2, RefreshCcw } from 'lucide-react';
import { useCallback, useMemo, useState } from 'react';

type GenerationTaskActionsProps = {
  item: IMessage;
  loading?: boolean;
  onContinue?: (item: IMessage) => void;
};

export function GenerationTaskActions({
  item,
  loading,
  onContinue,
}: GenerationTaskActionsProps) {
  const longTask = item.data?.longTask;
  const [generating, setGenerating] = useState(false);
  const [downloadInfo, setDownloadInfo] =
    useState<IDocumentDownloadInfo | null>(null);

  const truncated = useMemo(
    () => !loading && isAnswerTruncated(String(item.content ?? '')),
    [item.content, loading],
  );

  const handleGenerateMarkdown = useCallback(async () => {
    if (!longTask || generating) return;

    setGenerating(true);
    try {
      const response = await request.post(api.generationMarkdown, {
        data: {
          query: longTask.query,
          task_type: longTask.taskType,
          outline: longTask.outline,
          summary: longTask.summary,
          chat_id: longTask.chatId,
          agent_id: longTask.agentId,
          source: longTask.source,
        },
      });
      const nextDownload = response.data?.data?.download;
      if (nextDownload) {
        setDownloadInfo(nextDownload);
        message.success(
          i18n.t('chat.markdownDocumentReady', {
            defaultValue: 'Markdown document is ready.',
          }),
        );
      } else {
        message.error(
          response.data?.message ||
            i18n.t('chat.markdownDocumentFailed', {
              defaultValue: 'Failed to generate Markdown document.',
            }),
        );
      }
    } catch (error) {
      console.error('Generate Markdown failed:', error);
      message.error(
        i18n.t('chat.markdownDocumentFailed', {
          defaultValue: 'Failed to generate Markdown document.',
        }),
      );
    } finally {
      setGenerating(false);
    }
  }, [generating, longTask]);

  if (!longTask && !truncated) {
    return null;
  }

  return (
    <div className="mt-3 flex flex-col items-start gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {longTask && (
          <Button
            size="sm"
            onClick={handleGenerateMarkdown}
            disabled={generating}
            className="gap-2"
          >
            {generating ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <FileDown className="h-4 w-4" />
            )}
            {i18n.t('chat.generateMarkdownDocument', {
              defaultValue: 'Generate Markdown document',
            })}
          </Button>
        )}
        {truncated && onContinue && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => onContinue(item)}
            className="gap-2"
          >
            <RefreshCcw className="h-4 w-4" />
            {i18n.t('chat.continueGenerating', {
              defaultValue: 'Continue generating',
            })}
          </Button>
        )}
      </div>
      {downloadInfo && (
        <div className="w-full max-w-2xl">
          <DocumentDownloadButton downloadInfo={downloadInfo} />
        </div>
      )}
    </div>
  );
}
