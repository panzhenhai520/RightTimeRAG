import { useEffect, useRef, useState } from 'react';

export interface DS4HealthState {
  state:
    | 'ready'
    | 'maintenance'
    | 'restarting'
    | 'warming'
    | 'starting'
    | 'degraded'
    | 'unknown';
  ready: boolean;
  usage_percent: number | null;
  live_tokens: number | null;
  remaining_tokens: number | null;
  context_length: number | null;
  restart_threshold: number | null;
  restart_count: number;
}

const POLL_INTERVAL_MS = 4000;
const INITIAL_STATE: DS4HealthState = {
  state: 'unknown',
  ready: true,
  usage_percent: null,
  live_tokens: null,
  remaining_tokens: null,
  context_length: null,
  restart_threshold: null,
  restart_count: 0,
};

export function useDS4Health(): DS4HealthState {
  const [health, setHealth] = useState<DS4HealthState>(INITIAL_STATE);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeRef = useRef(true);

  useEffect(() => {
    activeRef.current = true;

    async function poll() {
      try {
        const resp = await fetch('/api/v1/dev/ds4-health', {
          credentials: 'include',
        });
        if (resp.ok) {
          const json = await resp.json();
          if (activeRef.current) {
            setHealth({
              state: json.data?.state ?? 'unknown',
              ready: json.data?.ready ?? true,
              usage_percent: json.data?.usage_percent ?? null,
              live_tokens: json.data?.live_tokens ?? null,
              remaining_tokens: json.data?.remaining_tokens ?? null,
              context_length: json.data?.context_length ?? null,
              restart_threshold: json.data?.restart_threshold ?? null,
              restart_count: json.data?.restart_count ?? 0,
            });
          }
        }
      } catch {
        // silently ignore fetch errors; backend may be starting
      }
      if (activeRef.current) {
        timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
      }
    }

    poll();

    return () => {
      activeRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return health;
}

export function ds4IsCompacting(state: DS4HealthState['state']): boolean {
  return state === 'maintenance' || state === 'restarting';
}

export function ds4IsWarming(state: DS4HealthState['state']): boolean {
  return state === 'warming' || state === 'starting';
}

export function ds4NeedsMaintenance(health: DS4HealthState): boolean {
  if (
    typeof health.live_tokens !== 'number' ||
    typeof health.restart_threshold !== 'number'
  ) {
    return false;
  }

  return (
    health.restart_threshold > 0 &&
    health.live_tokens >= health.restart_threshold
  );
}
