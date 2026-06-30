import { RAGFlowAvatar } from '@/components/ragflow-avatar';
import { Button, ButtonLoading } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  IAgentValidationIssue,
  IAgentValidationResponse,
  IFlow,
} from '@/interfaces/database/agent';
import { IDataset } from '@/interfaces/database/dataset';
import { formatDate } from '@/utils/date';
import { AlertTriangle, BookPlus, CheckCircle2 } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useIsPipeline } from '../hooks/use-is-pipeline';

interface PublishConfirmDialogProps {
  agentDetail: IFlow;
  loading: boolean;
  onPublish: () => void | Promise<void>;
  onValidate?: () => Promise<IAgentValidationResponse>;
}

function AssociatedDataset({
  associatedDatasets,
}: {
  associatedDatasets: Pick<IDataset, 'id' | 'name' | 'avatar'>[];
}) {
  const { t } = useTranslation();

  return (
    <div className="space-y-2 pl-10 pt-3">
      <div className="text-sm font-medium text-text-secondary">
        {t('flow.linkedDataset')}
      </div>
      {associatedDatasets.length > 0 ? (
        <div className="space-y-2 max-h-32 overflow-y-auto">
          {associatedDatasets.map((dataset) => (
            <div
              key={dataset.id}
              className="flex items-center gap-2 px-2 py-2 bg-bg-card rounded text-sm text-text-primary"
            >
              <RAGFlowAvatar
                avatar={dataset.avatar}
                name={dataset.name}
                className="size-4 text-xs"
              />
              <span className="truncate text-text-secondary">
                {dataset.name}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-sm text-text-disabled">{t('common.noData')}</div>
      )}
    </div>
  );
}

function PublishIssueList({
  title,
  issues,
  tone,
}: {
  title: string;
  issues: IAgentValidationIssue[];
  tone: 'error' | 'warning';
}) {
  if (issues.length === 0) {
    return null;
  }

  const toneClass =
    tone === 'error'
      ? 'border-red-200 bg-red-50 text-red-900 dark:border-red-900/60 dark:bg-red-950/25 dark:text-red-100'
      : 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/25 dark:text-amber-100';

  return (
    <section className={`rounded border px-3 py-2 ${toneClass}`}>
      <div className="mb-1 flex items-center gap-2 text-sm font-medium">
        <AlertTriangle className="size-4" />
        <span>{title}</span>
      </div>
      <div className="max-h-32 space-y-1 overflow-y-auto pl-6 text-xs leading-5">
        {issues.map((issue, index) => (
          <div key={`${issue.code}-${issue.component_id}-${index}`}>
            <span>{issue.message}</span>
            {issue.component_name && (
              <span className="ml-1 opacity-75">({issue.component_name})</span>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

export function PublishConfirmDialog({
  agentDetail,
  loading,
  onPublish,
  onValidate,
}: PublishConfirmDialogProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [validating, setValidating] = useState(false);
  const [validation, setValidation] = useState<IAgentValidationResponse>();
  const [validationError, setValidationError] = useState('');
  const isPipeline = useIsPipeline();

  const lastPublished = useMemo(() => {
    if (agentDetail?.last_publish_time) {
      return formatDate(agentDetail.last_publish_time);
    }
    return '';
  }, [agentDetail.last_publish_time]);

  // Get datasets associated with this pipeline from API response
  const associatedDatasets = useMemo(() => {
    return agentDetail?.datasets || [];
  }, [agentDetail?.datasets]);

  const runValidation = useCallback(async () => {
    if (!onValidate) {
      return undefined;
    }
    setValidating(true);
    setValidationError('');
    try {
      const result = await onValidate();
      setValidation(result);
      return result;
    } catch (error) {
      setValidationError(
        error instanceof Error
          ? error.message
          : t('flow.publishValidationFailed'),
      );
      return undefined;
    } finally {
      setValidating(false);
    }
  }, [onValidate, t]);

  useEffect(() => {
    if (open) {
      runValidation();
    }
  }, [open, runValidation]);

  const handleOpenChange = useCallback((nextOpen: boolean) => {
    setOpen(nextOpen);
    if (!nextOpen) {
      setValidation(undefined);
      setValidationError('');
    }
  }, []);

  const handleConfirmPublish = useCallback(async () => {
    const result = validation ?? (await runValidation());
    if (result?.errors?.length) {
      return;
    }
    await onPublish();
    handleOpenChange(false);
  }, [handleOpenChange, onPublish, runValidation, validation]);

  const hasValidationErrors = (validation?.errors?.length || 0) > 0;
  const hasValidationWarnings = (validation?.warnings?.length || 0) > 0;

  if (isPipeline) {
    return null;
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <ButtonLoading variant={'secondary'} loading={loading}>
          <BookPlus /> {t('flow.release')}
        </ButtonLoading>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('flow.confirmPublish')}</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          <div className="space-y-3">
            <div className="text-sm text-text-secondary">
              {t(
                `flow.${isPipeline ? 'publishIngestionPipeline' : 'publishAgent'}`,
              )}
            </div>

            <section className="bg-bg-input px-2.5 py-4 rounded border border-border-default">
              <div className="flex gap-2.5 items-center">
                <RAGFlowAvatar
                  avatar={agentDetail.avatar}
                  name={agentDetail.title}
                  className="size-8"
                />
                <span className="text-text-primary text-lg">
                  {agentDetail.title}
                </span>
              </div>

              {isPipeline && (
                <AssociatedDataset
                  associatedDatasets={associatedDatasets}
                ></AssociatedDataset>
              )}
            </section>

            <div className="flex flex-col gap-2">
              {lastPublished && (
                <div className="flex items-center text-sm text-text-secondary gap-2">
                  <span>{t('flow.lastPublished')}:</span>
                  <span>{lastPublished}</span>
                </div>
              )}
            </div>

            <div className="space-y-2">
              <div className="text-sm font-medium text-text-primary">
                {t('flow.publishValidation')}
              </div>
              {validating ? (
                <div className="rounded border border-border-default bg-bg-card px-3 py-2 text-sm text-text-secondary">
                  {t('flow.publishValidating')}
                </div>
              ) : validationError ? (
                <section className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/25 dark:text-amber-100">
                  {validationError}
                </section>
              ) : validation ? (
                <div className="space-y-2">
                  {!hasValidationErrors && !hasValidationWarnings && (
                    <section className="flex items-center gap-2 rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900 dark:border-emerald-900/60 dark:bg-emerald-950/25 dark:text-emerald-100">
                      <CheckCircle2 className="size-4" />
                      <span>{t('flow.publishValidationPassed')}</span>
                    </section>
                  )}
                  <PublishIssueList
                    title={t('flow.publishValidationErrors')}
                    issues={validation.errors}
                    tone="error"
                  />
                  <PublishIssueList
                    title={t('flow.publishValidationWarnings')}
                    issues={validation.warnings}
                    tone="warning"
                  />
                </div>
              ) : null}
            </div>
          </div>
        </DialogDescription>
        <DialogFooter className="gap-2 mt-4">
          <Button variant="outline" onClick={() => setOpen(false)}>
            {t('common.cancel')}
          </Button>
          <ButtonLoading
            onClick={handleConfirmPublish}
            loading={loading || validating}
            disabled={hasValidationErrors}
          >
            {t('common.confirm')}
          </ButtonLoading>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
