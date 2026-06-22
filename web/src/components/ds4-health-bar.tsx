import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import api from '@/utils/api';
import request from '@/utils/next-request';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

type Ds4HealthLevel = 'healthy' | 'watch' | 'warning' | 'critical' | 'unknown';

type Ds4HealthStatus = {
  state?: string;
  reason?: string;
  ready?: boolean;
  context_length?: number;
  live_tokens?: number | null;
  remaining_tokens?: number | null;
  usage_percent?: number | null;
  restart_threshold?: number | null;
  stale?: boolean;
  level?: Ds4HealthLevel;
};

const levelColors: Record<Ds4HealthLevel, string> = {
  healthy: '#2f9e44',
  watch: '#3875d7',
  warning: '#c07a00',
  critical: '#d8494b',
  unknown: '#8a8f98',
};

const levelClasses: Record<Ds4HealthLevel, string> = {
  healthy: 'border-state-success/25 bg-state-success/5',
  watch: 'border-accent-primary/25 bg-accent-primary/5',
  warning: 'border-state-warning/25 bg-state-warning/10',
  critical: 'border-state-error/25 bg-state-error/10',
  unknown: 'border-border bg-bg-card',
};

function formatTokenCount(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '--';
  }
  return new Intl.NumberFormat().format(Math.max(0, Math.round(value)));
}

function clampPercent(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 0;
  }
  return Math.max(0, Math.min(100, value));
}

function useDs4Status() {
  return useQuery({
    queryKey: ['ds4HealthStatus'],
    queryFn: async () => {
      const response = await request.get(api.ds4Status);
      return (response.data?.data || {}) as Ds4HealthStatus;
    },
    refetchInterval: 5000,
    retry: false,
  });
}

export function Ds4HealthBar({ className }: { className?: string }) {
  const { t } = useTranslation();
  const { data } = useDs4Status();
  const level = (data?.level || 'unknown') as Ds4HealthLevel;
  const percent = clampPercent(data?.usage_percent);
  const color = levelColors[level] || levelColors.unknown;
  const state = data?.state || 'unknown';
  const statusLabel = t(`chat.ds4HealthState_${state}`, {
    defaultValue: state,
  });
  const reason = data?.reason || '';
  const isBusy = ['starting', 'warming', 'maintenance', 'restarting'].includes(
    state,
  );
  const ringSize = 32;
  const radius = 13;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - percent / 100);
  const percentLabel =
    typeof data?.usage_percent === 'number' &&
    Number.isFinite(data.usage_percent)
      ? `${Math.round(percent)}%`
      : '--';
  const helperText =
    state === 'maintenance' || state === 'restarting'
      ? t('chat.ds4HealthMaintenance')
      : state === 'warming' || state === 'starting'
        ? t('chat.ds4HealthWarming')
        : level === 'critical'
          ? t('chat.ds4HealthCritical')
          : level === 'warning'
            ? t('chat.ds4HealthWarning')
            : t('chat.ds4HealthReady');

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className={cn(
            'relative inline-flex size-8 items-center justify-center rounded-full border transition-colors',
            levelClasses[level] || levelClasses.unknown,
            isBusy && 'animate-pulse',
            className,
          )}
          aria-label={t('chat.ds4HealthTitle')}
          data-testid="ds4-health-ring"
        >
          <svg
            width={ringSize}
            height={ringSize}
            viewBox={`0 0 ${ringSize} ${ringSize}`}
            className="-rotate-90"
            aria-hidden="true"
          >
            <circle
              cx={ringSize / 2}
              cy={ringSize / 2}
              r={radius}
              stroke="currentColor"
              strokeWidth="3"
              fill="none"
              className="text-border"
              opacity="0.45"
            />
            <circle
              cx={ringSize / 2}
              cy={ringSize / 2}
              r={radius}
              stroke={color}
              strokeWidth="3"
              fill="none"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={dashOffset}
              className="transition-all duration-500"
            />
          </svg>
          <span
            className="absolute text-[8px] font-semibold leading-none"
            style={{ color }}
          >
            {percentLabel}
          </span>
        </button>
      </TooltipTrigger>
      <TooltipContent className="w-72 text-xs leading-5">
        <div className="font-medium text-text-primary">
          {t('chat.ds4HealthTitle')}
        </div>
        <div className="mt-1 text-text-secondary">{helperText}</div>
        <div className="mt-2 grid gap-1 text-text-secondary">
          <div className="flex justify-between gap-3">
            <span>{t('chat.ds4HealthState')}</span>
            <span className="font-medium text-text-primary">{statusLabel}</span>
          </div>
          <div className="flex justify-between gap-3">
            <span>{t('chat.ds4HealthContextUsage')}</span>
            <span className="font-medium text-text-primary">
              {formatTokenCount(data?.live_tokens)} /{' '}
              {formatTokenCount(data?.context_length)}
            </span>
          </div>
          <div className="flex justify-between gap-3">
            <span>{t('chat.ds4HealthUsageRatio')}</span>
            <span className="font-medium text-text-primary">
              {percent.toFixed(1)}%
            </span>
          </div>
          <div className="flex justify-between gap-3">
            <span>{t('chat.ds4HealthAvailableContext')}</span>
            <span className="font-medium text-text-primary">
              {formatTokenCount(data?.remaining_tokens)}
            </span>
          </div>
          <div className="flex justify-between gap-3">
            <span>{t('chat.ds4HealthMaintenanceThreshold')}</span>
            <span className="font-medium text-text-primary">
              {formatTokenCount(data?.restart_threshold)}
            </span>
          </div>
        </div>
        {reason && (
          <div className="mt-2 border-t border-border pt-2 text-text-secondary">
            {t('chat.ds4HealthReason')}: {reason}
          </div>
        )}
      </TooltipContent>
    </Tooltip>
  );
}
