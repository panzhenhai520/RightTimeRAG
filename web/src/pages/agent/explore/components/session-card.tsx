import { MoreButton } from '@/components/more-button';
import { Card, CardContent } from '@/components/ui/card';
import { IAgentLogResponse } from '@/interfaces/database/agent';
import { cn } from '@/lib/utils';
import { Activity } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { RunTraceDialog } from './run-trace-dialog';
import { SessionDropdown } from './session-dropdown';

interface SessionCardProps {
  session: IAgentLogResponse & { is_new?: boolean };
  selected?: boolean;
  running?: boolean;
  runningRun?: {
    runId?: string;
    status?: string;
    progressPercent?: number;
    currentNodeName?: string;
  };
  onClick: () => void;
  removeTemporarySession?: (sessionId: string) => void;
}

export function SessionCard({
  session,
  selected,
  running,
  runningRun,
  onClick,
  removeTemporarySession,
}: SessionCardProps) {
  const { t } = useTranslation();
  const [traceOpen, setTraceOpen] = useState(false);
  const isNewSession = session.is_new;

  const displayName = isNewSession ? t('explore.newSession') : session.name;
  const progressPercent =
    typeof runningRun?.progressPercent === 'number'
      ? Math.round(runningRun.progressPercent * 100)
      : undefined;
  const runningTitle = running
    ? [
        runningRun?.status,
        progressPercent !== undefined ? `${progressPercent}%` : undefined,
        runningRun?.currentNodeName,
      ]
        .filter(Boolean)
        .join(' · ')
    : undefined;

  return (
    <>
      <Card
        onClick={onClick}
        className={cn(
          'cursor-pointer hover:shadow-md transition-shadow',
          selected && 'bg-bg-card',
        )}
      >
        <CardContent className="p-3 flex justify-between items-center gap-2 group">
          <div className="flex items-center gap-2 flex-1 min-w-0">
            {running && (
              <span className="h-3 w-3 shrink-0 animate-spin rounded-full border border-current border-t-transparent text-accent-primary" />
            )}
            <div className="flex-1 min-w-0">
              <div
                className="text-sm font-medium truncate"
                title={runningTitle}
              >
                {displayName}
              </div>
            </div>
          </div>
          {runningRun?.runId && (
            <button
              type="button"
              title="Run details"
              className="shrink-0 rounded p-1 text-text-secondary hover:text-text-primary"
              onClick={(event) => {
                event.stopPropagation();
                setTraceOpen(true);
              }}
            >
              <Activity className="h-4 w-4" />
            </button>
          )}
          <SessionDropdown
            session={session}
            removeTemporarySession={removeTemporarySession}
          >
            <MoreButton />
          </SessionDropdown>
        </CardContent>
      </Card>
      <RunTraceDialog
        runId={runningRun?.runId}
        open={traceOpen}
        onOpenChange={setTraceOpen}
      />
    </>
  );
}
