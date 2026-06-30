import { HomeCard } from '@/components/home-card';
import { AgentCategory } from '@/constants/agent';
import { useNavigatePage } from '@/hooks/logic-hooks/navigate-hooks';
import { useFetchAgentListByPage } from '@/hooks/use-agent-request';
import { useEffect, useMemo } from 'react';
import { useHomeAgentSelection } from '../agents/hooks/use-home-agent-selection';

export function Agents({
  setListLength,
  setLoading,
  pageSize,
  displayLimit,
}: {
  setListLength: (length: number) => void;
  setLoading?: (loading: boolean) => void;
  pageSize?: number;
  displayLimit?: number;
}) {
  const { data, loading } = useFetchAgentListByPage({
    page: 1,
    pageSize: 100000,
  });
  const { navigateToAgent } = useNavigatePage();
  const { selectedIds } = useHomeAgentSelection();
  const publishedAgents = useMemo(
    () => data.filter((agent) => agent.release || agent.release_time),
    [data],
  );
  const selectedHomeAgents = useMemo(
    () =>
      selectedIds
        .map((id) => data.find((agent) => agent.id === id))
        .filter((agent): agent is (typeof data)[number] => Boolean(agent)),
    [data, selectedIds],
  );
  const visibleAgents =
    selectedHomeAgents.length > 0 ? selectedHomeAgents : publishedAgents;

  useEffect(() => {
    setListLength(visibleAgents.length);
    setLoading?.(loading || false);
  }, [visibleAgents.length, setListLength, loading, setLoading]);

  return (
    <>
      {visibleAgents.slice(0, displayLimit ?? pageSize ?? 10).map((x) => (
        <HomeCard
          key={x.id}
          data={{ name: x.title, ...x } as any}
          onClick={navigateToAgent(x.id, x.canvas_category as AgentCategory)}
          moreDropdown={null}
        ></HomeCard>
      ))}
    </>
  );
}
