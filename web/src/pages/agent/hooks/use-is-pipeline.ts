import { AgentCategory, AgentQuery } from '@/constants/agent';
import { useFetchAgent } from '@/hooks/use-agent-request';
import { useSearchParams } from 'react-router';

export function useIsPipeline() {
  const [queryParameters] = useSearchParams();
  const { data } = useFetchAgent();

  return (
    queryParameters.get(AgentQuery.Category) === AgentCategory.DataflowCanvas ||
    data?.canvas_category === AgentCategory.DataflowCanvas
  );
}
