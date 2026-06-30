import { IAgentRunState } from '@/interfaces/database/agent';
import { fetchAgentRun } from '@/services/agent-service';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

const STORAGE_KEY = 'ragflow:agent-explore-running-runs';

type RunningRunRecord = {
  runId?: string;
  status?: IAgentRunState['status'];
  progressPercent?: number;
  currentNodeName?: string;
  updatedAt: number;
};

interface ExploreRunContextValue {
  runningSessionIds: Set<string>;
  runningRunsBySession: Record<string, RunningRunRecord>;
  getSessionRunId: (sessionId: string | null | undefined) => string | undefined;
  setSessionRunning: (
    sessionId: string | null | undefined,
    running: boolean,
    runId?: string | null,
    runState?: Partial<IAgentRunState> | null,
  ) => void;
}

const ExploreRunContext = createContext<ExploreRunContextValue>({
  runningSessionIds: new Set<string>(),
  runningRunsBySession: {},
  getSessionRunId: () => undefined,
  setSessionRunning: () => {},
});

const readStoredRunningRuns = (): Record<string, RunningRunRecord> => {
  if (typeof window === 'undefined') {
    return {};
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
};

const writeStoredRunningRuns = (
  value: Record<string, RunningRunRecord>,
): void => {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  } catch {
    // Ignore storage quota or privacy-mode errors. Runtime state still works in memory.
  }
};

export function ExploreRunProvider({ children }: { children: ReactNode }) {
  const [runningRunsBySession, setRunningRunsBySession] = useState<
    Record<string, RunningRunRecord>
  >(() => readStoredRunningRuns());

  const runningSessionIds = useMemo(
    () => new Set(Object.keys(runningRunsBySession)),
    [runningRunsBySession],
  );

  const setSessionRunning = useCallback(
    (
      sessionId: string | null | undefined,
      running: boolean,
      runId?: string | null,
      runState?: Partial<IAgentRunState> | null,
    ) => {
      if (!sessionId) {
        return;
      }
      setRunningRunsBySession((prev) => {
        const next = { ...prev };
        if (running) {
          const currentNode = runState?.progress?.current_nodes?.[0];
          next[sessionId] = {
            runId: runId || next[sessionId]?.runId,
            status: runState?.status || next[sessionId]?.status,
            progressPercent:
              typeof runState?.progress?.percent === 'number'
                ? runState.progress.percent
                : next[sessionId]?.progressPercent,
            currentNodeName:
              currentNode?.component_name ||
              currentNode?.component_type ||
              next[sessionId]?.currentNodeName,
            updatedAt: Date.now(),
          };
        } else {
          delete next[sessionId];
        }
        writeStoredRunningRuns(next);
        return next;
      });
    },
    [],
  );

  const getSessionRunId = useCallback(
    (sessionId: string | null | undefined) => {
      if (!sessionId) {
        return undefined;
      }
      return runningRunsBySession[sessionId]?.runId;
    },
    [runningRunsBySession],
  );

  useEffect(() => {
    const entries = Object.entries(runningRunsBySession).filter(
      ([, item]) => item.runId,
    );
    if (entries.length === 0) {
      return;
    }

    let cancelled = false;
    const poll = async () => {
      const finishedSessionIds: string[] = [];
      await Promise.all(
        entries.map(async ([sessionId, item]) => {
          try {
            const response = await fetchAgentRun(item.runId!);
            const run = (response as any).data?.data ?? (response as any).data;
            const status = run?.status;
            if (
              status &&
              !['queued', 'running', 'cancel_requested'].includes(status)
            ) {
              finishedSessionIds.push(sessionId);
            } else if (status) {
              setRunningRunsBySession((prev) => {
                if (!prev[sessionId]) {
                  return prev;
                }
                const currentNode = run?.progress?.current_nodes?.[0];
                const next = {
                  ...prev,
                  [sessionId]: {
                    ...prev[sessionId],
                    status,
                    progressPercent:
                      typeof run?.progress?.percent === 'number'
                        ? run.progress.percent
                        : prev[sessionId].progressPercent,
                    currentNodeName:
                      currentNode?.component_name ||
                      currentNode?.component_type ||
                      prev[sessionId].currentNodeName,
                    updatedAt: Date.now(),
                  },
                };
                writeStoredRunningRuns(next);
                return next;
              });
            }
          } catch {
            // Keep the indicator until a later poll succeeds.
          }
        }),
      );

      if (cancelled || finishedSessionIds.length === 0) {
        return;
      }
      setRunningRunsBySession((prev) => {
        const next = { ...prev };
        finishedSessionIds.forEach((sessionId) => {
          delete next[sessionId];
        });
        writeStoredRunningRuns(next);
        return next;
      });
    };

    poll();
    const timer = window.setInterval(poll, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [runningRunsBySession]);

  const value = useMemo(
    () => ({
      runningSessionIds,
      runningRunsBySession,
      getSessionRunId,
      setSessionRunning,
    }),
    [
      runningRunsBySession,
      runningSessionIds,
      getSessionRunId,
      setSessionRunning,
    ],
  );

  return (
    <ExploreRunContext.Provider value={value}>
      {children}
    </ExploreRunContext.Provider>
  );
}

export function useExploreRunContext() {
  return useContext(ExploreRunContext);
}
