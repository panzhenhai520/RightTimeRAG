import SvgIcon from '@/components/svg-icon';
import {
  DS4HealthState,
  ds4IsCompacting,
  ds4IsWarming,
  ds4NeedsMaintenance,
} from '@/hooks/use-ds4-health';
import { cn } from '@/lib/utils';
import { RAGFlowAvatar } from './ragflow-avatar';

function statusLabel(state: DS4HealthState['state']): string {
  if (state === 'maintenance') return 'AI 引擎正在清理上下文缓存';
  if (state === 'restarting') return 'AI 引擎正在重启';
  if (state === 'warming' || state === 'starting') return 'AI 引擎正在预热';
  if (state === 'degraded') return '推理引擎响应异常';
  return '';
}

function clampProgress(value: number | null | undefined) {
  if (typeof value !== 'number' || Number.isNaN(value)) return null;
  return Math.max(0, Math.min(100, Math.round(value)));
}

function formatPercent(value: number | null | undefined) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '--';
  return `${value.toFixed(1)}%`;
}

/**
 * Rendered as a pseudo-chat-row at the bottom of the message list.
 * Assistant icon on the left, status bar on the right — matching the
 * visual style of a regular assistant message.
 */
export function DS4CompactingBanner({
  avatarDialog,
  health,
}: {
  avatarDialog?: string | null;
  health: DS4HealthState;
}) {
  const isCompacting = ds4IsCompacting(health.state);
  const isWarming = ds4IsWarming(health.state);
  const needsMaintenance = ds4NeedsMaintenance(health);
  const isError = health.state === 'degraded';
  const isActive = isCompacting || isWarming || needsMaintenance;
  const isVisible = isActive || isError;
  const label =
    statusLabel(health.state) ||
    (needsMaintenance ? '上下文占用达到清理阈值' : '');
  const progress = clampProgress(
    health.maintenance_progress ?? (needsMaintenance ? 0 : null),
  );
  const displayProgress = progress ?? 0;
  const threshold =
    health.restart_usage_percent ??
    (typeof health.restart_threshold === 'number' &&
    typeof health.context_length === 'number' &&
    health.context_length > 0
      ? (health.restart_threshold / health.context_length) * 100
      : null);

  if (!isVisible || !label) return null;

  return (
    /* Same outer structure as MessageItem's messageItemLeft row */
    <div className="flex items-start gap-3 py-3 px-1 my-1">
      {avatarDialog ? (
        <RAGFlowAvatar
          className="size-20 shrink-0"
          avatar={avatarDialog}
          isPerson
        />
      ) : (
        <SvgIcon
          name="assistant"
          width="100%"
          className="size-20 shrink-0 fill-current"
        />
      )}

      {/* Status content area */}
      <div className="flex-1 min-w-0 pt-1">
        <div
          className={cn(
            'inline-flex w-full max-w-md flex-col gap-2 rounded-lg px-3 py-2',
            isError
              ? 'bg-red-50 dark:bg-red-950/40'
              : 'bg-sky-50 text-sky-900 dark:bg-sky-950/30 dark:text-sky-100',
          )}
          role="status"
          aria-live="polite"
        >
          <div
            className={cn(
              'flex items-center justify-between gap-3 text-xs',
              isError
                ? 'text-red-700 dark:text-red-300'
                : 'text-sky-700 dark:text-sky-300',
            )}
          >
            <span className="truncate">{label}</span>
            <span className="shrink-0 tabular-nums">{displayProgress}%</span>
          </div>

          <div
            className={cn(
              'h-2 w-full overflow-hidden rounded-full',
              isError
                ? 'bg-red-100 dark:bg-red-900/50'
                : 'bg-sky-100 dark:bg-sky-900/60',
            )}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={displayProgress}
            role="progressbar"
          >
            <div
              className={cn(
                'h-full rounded-full transition-all duration-500',
                isError ? 'bg-red-500' : 'bg-sky-500 dark:bg-sky-400',
              )}
              style={{ width: `${displayProgress}%` }}
            />
          </div>

          {!isError && (
            <div className="flex justify-between gap-3 text-[11px] leading-4 text-sky-700/80 dark:text-sky-200/75">
              <span>上下文占用 {formatPercent(health.usage_percent)}</span>
              <span>清理阈值 {formatPercent(threshold)}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
