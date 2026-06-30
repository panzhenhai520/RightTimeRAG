import message from '@/components/ui/message';
import { useFetchUserInfo } from '@/hooks/use-user-setting-request';
import { IFlow } from '@/interfaces/database/agent';
import { useCallback, useEffect, useMemo, useState } from 'react';

const HOME_AGENT_STORAGE_PREFIX = 'righttime.homeAgentIds';
const HOME_AGENT_SELECTION_EVENT = 'righttime-home-agent-selection-change';
const MAX_HOME_AGENTS = 2;

type ToggleResult = 'added' | 'removed' | 'full';

function uniqFirstTwo(ids: string[]) {
  return Array.from(new Set(ids.filter(Boolean))).slice(0, MAX_HOME_AGENTS);
}

function readHomeAgentIds(storageKey: string) {
  if (typeof window === 'undefined') {
    return [];
  }

  try {
    const value = window.localStorage.getItem(storageKey);
    const parsed = value ? JSON.parse(value) : [];
    return Array.isArray(parsed) ? uniqFirstTwo(parsed) : [];
  } catch {
    return [];
  }
}

function writeHomeAgentIds(storageKey: string, ids: string[]) {
  const nextIds = uniqFirstTwo(ids);
  window.localStorage.setItem(storageKey, JSON.stringify(nextIds));
  window.dispatchEvent(
    new CustomEvent(HOME_AGENT_SELECTION_EVENT, {
      detail: { storageKey, ids: nextIds },
    }),
  );
  return nextIds;
}

export function useHomeAgentSelection() {
  const { data: userInfo } = useFetchUserInfo();
  const userKey = userInfo?.id || userInfo?.email || 'anonymous';
  const storageKey = useMemo(
    () => `${HOME_AGENT_STORAGE_PREFIX}:${userKey}`,
    [userKey],
  );
  const [selectedIds, setSelectedIds] = useState<string[]>(() =>
    readHomeAgentIds(storageKey),
  );

  useEffect(() => {
    setSelectedIds(readHomeAgentIds(storageKey));

    const handleChange = (event: Event) => {
      const detail = (event as CustomEvent).detail;
      if (!detail || detail.storageKey === storageKey) {
        setSelectedIds(readHomeAgentIds(storageKey));
      }
    };

    window.addEventListener('storage', handleChange);
    window.addEventListener(HOME_AGENT_SELECTION_EVENT, handleChange);
    return () => {
      window.removeEventListener('storage', handleChange);
      window.removeEventListener(HOME_AGENT_SELECTION_EVENT, handleChange);
    };
  }, [storageKey]);

  const isHomeAgent = useCallback(
    (agentId?: string) => Boolean(agentId && selectedIds.includes(agentId)),
    [selectedIds],
  );

  const toggleHomeAgent = useCallback(
    (agent: Pick<IFlow, 'id' | 'title'>): ToggleResult => {
      if (selectedIds.includes(agent.id)) {
        const nextIds = writeHomeAgentIds(
          storageKey,
          selectedIds.filter((id) => id !== agent.id),
        );
        setSelectedIds(nextIds);
        message.success('已从首页移除');
        return 'removed';
      }

      if (selectedIds.length >= MAX_HOME_AGENTS) {
        message.warning('首页最多显示两个智能体');
        return 'full';
      }

      const nextIds = writeHomeAgentIds(storageKey, [...selectedIds, agent.id]);
      setSelectedIds(nextIds);
      message.success('已设为首页显示');
      return 'added';
    },
    [selectedIds, storageKey],
  );

  return {
    selectedIds,
    isHomeAgent,
    toggleHomeAgent,
    maxHomeAgents: MAX_HOME_AGENTS,
  };
}
