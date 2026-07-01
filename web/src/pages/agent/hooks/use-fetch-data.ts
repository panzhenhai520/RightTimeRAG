import { useFetchAgent } from '@/hooks/use-agent-request';
import { DSLComponents, IGraph } from '@/interfaces/database/agent';
import { useEffect } from 'react';
import { useSetGraphInfo } from './use-set-graph';

function isEmptyForm(form: unknown) {
  return (
    !form ||
    (typeof form === 'object' &&
      !Array.isArray(form) &&
      Object.keys(form).length === 0)
  );
}

function hydrateGraphForms(graph?: IGraph, components?: DSLComponents): IGraph {
  if (!graph?.nodes?.length) return (graph ?? {}) as IGraph;

  return {
    ...graph,
    nodes: graph.nodes.map((node) => {
      const componentParams = components?.[node.id]?.obj?.params;
      if (!componentParams || !isEmptyForm(node.data?.form)) return node;

      return {
        ...node,
        data: {
          ...node.data,
          form: componentParams,
        },
      };
    }),
  };
}

export const useFetchDataOnMount = () => {
  const { loading, data, refetch } = useFetchAgent();
  const setGraphInfo = useSetGraphInfo();

  useEffect(() => {
    setGraphInfo(hydrateGraphForms(data?.dsl?.graph, data?.dsl?.components));
  }, [setGraphInfo, data]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { loading, flowDetail: data };
};
