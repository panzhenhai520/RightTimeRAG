import { useSystemConfig } from './use-system-request';

type FeatureFlags = {
  memoSpacetime?: boolean;
  memoProfile?: boolean;
  memoryContext?: boolean;
  evidenceAudit?: boolean;
  structuredExtraction?: boolean;
  semanticRouter?: boolean;
};

export const useFeatureFlags = () => {
  const { config, loading } = useSystemConfig();
  const flags = (config?.featureFlags || {}) as FeatureFlags;

  const enabled = (name: keyof FeatureFlags) => flags[name] !== false;

  return { flags, enabled, loading };
};
