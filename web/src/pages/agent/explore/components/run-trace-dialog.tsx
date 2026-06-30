import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { IAgentRunTraceResponse } from '@/interfaces/database/agent';
import { fetchAgentRunTrace } from '@/services/agent-service';
import { useEffect, useMemo, useState } from 'react';

interface RunTraceDialogProps {
  runId?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const statusClassName: Record<string, string> = {
  running: 'text-accent-primary',
  succeeded: 'text-green-600',
  failed: 'text-red-600',
  canceled: 'text-text-secondary',
};

function formatDuration(seconds?: number | null) {
  if (typeof seconds !== 'number') {
    return '-';
  }
  if (seconds < 60) {
    return `${seconds.toFixed(1)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes}m ${rest}s`;
}

export function RunTraceDialog({
  runId,
  open,
  onOpenChange,
}: RunTraceDialogProps) {
  const [trace, setTrace] = useState<IAgentRunTraceResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open || !runId) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError('');
    fetchAgentRunTrace(runId)
      .then((response) => {
        if (cancelled) return;
        const data = (response as any).data?.data ?? (response as any).data;
        setTrace(data || null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message || 'Failed to load run details');
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [open, runId]);

  const timeline = trace?.timeline || [];
  const nodes = trace?.nodes || [];
  const downloads = trace?.downloads || [];
  const errors = trace?.errors || [];
  const title = useMemo(() => {
    const status = trace?.state?.status;
    const duration = formatDuration(trace?.duration);
    return ['Run details', status, duration].filter(Boolean).join(' · ');
  }, [trace]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[82vh] overflow-hidden">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>

        {loading && (
          <div className="py-10 text-center text-text-secondary">
            Loading...
          </div>
        )}
        {error && <div className="py-6 text-sm text-red-600">{error}</div>}

        {!loading && !error && (
          <div className="grid grid-cols-1 md:grid-cols-[1fr_1.2fr] gap-4 overflow-auto pr-1">
            <section className="space-y-3">
              <div>
                <div className="mb-2 text-sm font-medium">Timeline</div>
                <div className="space-y-2">
                  {timeline.map((item) => (
                    <div
                      key={`${item.seq}-${item.event_type}`}
                      className="rounded border border-border px-3 py-2 text-xs"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span>{item.event_type}</span>
                        <span
                          className={
                            statusClassName[item.status || ''] ||
                            'text-text-secondary'
                          }
                        >
                          {item.status || ''}
                        </span>
                      </div>
                      {(item.component_name || item.component_id) && (
                        <div className="mt-1 truncate text-text-secondary">
                          {item.component_name || item.component_id}
                        </div>
                      )}
                      {item.error && (
                        <div className="mt-1 text-red-600">{item.error}</div>
                      )}
                    </div>
                  ))}
                  {timeline.length === 0 && (
                    <div className="text-sm text-text-secondary">
                      No timeline events.
                    </div>
                  )}
                </div>
              </div>
            </section>

            <section className="space-y-4">
              <div>
                <div className="mb-2 text-sm font-medium">Nodes</div>
                <div className="space-y-2">
                  {nodes.map((node) => (
                    <div
                      key={node.component_id}
                      className="rounded border border-border px-3 py-2 text-xs"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate">
                          {node.component_name || node.component_id}
                        </span>
                        <span
                          className={
                            statusClassName[node.status || ''] ||
                            'text-text-secondary'
                          }
                        >
                          {node.status || ''}
                        </span>
                      </div>
                      {node.elapsed_time !== undefined && (
                        <div className="mt-1 text-text-secondary">
                          {formatDuration(node.elapsed_time)}
                        </div>
                      )}
                      {node.error && (
                        <div className="mt-1 text-red-600">{node.error}</div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {errors.length > 0 && (
                <div>
                  <div className="mb-2 text-sm font-medium">Errors</div>
                  <div className="space-y-2">
                    {errors.map((item, index) => (
                      <div
                        key={`${item.component_id || 'workflow'}-${index}`}
                        className="rounded border border-red-200 px-3 py-2 text-xs text-red-600"
                      >
                        {item.component_name || item.component_id || 'workflow'}
                        : {item.error}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {downloads.length > 0 && (
                <div>
                  <div className="mb-2 text-sm font-medium">Artifacts</div>
                  <div className="space-y-2">
                    {downloads.map((item) => (
                      <div
                        key={item.doc_id}
                        className="flex items-center justify-between gap-3 rounded border border-border px-3 py-2 text-xs"
                      >
                        <span className="truncate">
                          {item.filename || item.doc_id}
                        </span>
                        {item.download_url && (
                          <Button asChild size="sm" variant="outline">
                            <a href={item.download_url}>Download</a>
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </section>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
