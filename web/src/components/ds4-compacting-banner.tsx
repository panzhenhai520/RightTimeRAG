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
  if (state === 'maintenance') return '正在压缩上下文…';
  if (state === 'restarting') return '正在重启推理引擎…';
  if (state === 'warming' || state === 'starting')
    return '推理引擎预热中，请稍候…';
  if (state === 'degraded') return '推理引擎响应异常';
  return '';
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
  const label = statusLabel(health.state) || '正在准备压缩上下文…';

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
            'inline-flex flex-col gap-1 rounded-lg px-3 py-2 max-w-sm',
            isError
              ? 'bg-red-50 dark:bg-red-950/40'
              : 'bg-sky-50 dark:bg-sky-950/30',
          )}
        >
          {/* Text + pulse dot row */}
          <div
            className={cn(
              'flex items-center gap-2 text-xs',
              isError
                ? 'text-red-700 dark:text-red-300'
                : 'text-sky-700 dark:text-sky-300',
            )}
          >
            {isActive && (
              <span className="inline-block h-2 w-2 shrink-0 animate-pulse rounded-full bg-sky-400" />
            )}
            <span>{label}</span>
          </div>

          {/* Animated progress track */}
          {isActive && (
            <div className="relative h-[3px] w-48 overflow-hidden rounded-full bg-sky-100 dark:bg-sky-900/50">
              <div className="absolute inset-y-0 w-1/2 animate-compacting-slide bg-gradient-to-r from-transparent via-sky-400 to-transparent" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
