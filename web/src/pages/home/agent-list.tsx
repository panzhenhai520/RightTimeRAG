import { HomeCard } from '@/components/home-card';
import { AgentCategory } from '@/constants/agent';
import { useNavigatePage } from '@/hooks/logic-hooks/navigate-hooks';
import { useFetchAgentListByPage } from '@/hooks/use-agent-request';
import { useEffect, useMemo } from 'react';

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
  const { data, loading } = useFetchAgentListByPage(
    pageSize ? { page: 1, pageSize } : undefined,
  );
  const { navigateToAgent } = useNavigatePage();
  const publishedAgents = useMemo(
    () => data.filter((agent) => agent.release || agent.release_time),
    [data],
  );

  useEffect(() => {
    setListLength(publishedAgents.length);
    setLoading?.(loading || false);
  }, [publishedAgents.length, setListLength, loading, setLoading]);

  return (
    <>
      {publishedAgents.slice(0, displayLimit ?? pageSize ?? 10).map((x) => (
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
