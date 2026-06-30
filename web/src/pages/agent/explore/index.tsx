import { PageHeader } from '@/components/page-header';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { useNavigatePage } from '@/hooks/logic-hooks/navigate-hooks';
import { useFetchSessionManually } from '@/hooks/use-agent-request';
import { listAgentActiveRuns } from '@/services/agent-service';
import { useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router';
import { useFetchDataOnMount } from '../hooks/use-fetch-data';
import { SessionChat } from './components/session-chat';
import { SessionList } from './components/session-list';
import { useExploreUrlParams } from './hooks/use-explore-url-params';
import { ExploreRunProvider, useExploreRunContext } from './run-context';

function AgentExploreContent() {
  const { sessionId, setSessionId } = useExploreUrlParams();
  const { navigateToAgent, navigateToHome } = useNavigatePage();
  const { t } = useTranslation();
  const { id } = useParams();
  const { flowDetail: agentDetail } = useFetchDataOnMount();
  const { fetchSessionManually, data: session } = useFetchSessionManually();
  const { runningSessionIds, runningRunsBySession, setSessionRunning } =
    useExploreRunContext();

  const handleBackToAgent = useCallback(() => {
    const navigateFn = navigateToAgent(id as string);
    navigateFn();
  }, [id, navigateToAgent]);

  const handleSessionSelect = useCallback(
    (id: string, isNew?: boolean) => {
      setSessionId(id, isNew);
      fetchSessionManually(id);
    },
    [fetchSessionManually, setSessionId],
  );

  useEffect(() => {
    if (!id) {
      return;
    }
    let cancelled = false;
    const restoreActiveRuns = async () => {
      try {
        const response = await listAgentActiveRuns(id);
        const payload = (response as any).data?.data ?? (response as any).data;
        const runs = payload?.runs || [];
        if (cancelled) {
          return;
        }
        runs.forEach((run: any) => {
          setSessionRunning(run.session_id, true, run.run_id, run);
        });
      } catch {
        // Active run restoration is opportunistic; local session state still works.
      }
    };
    restoreActiveRuns();
    return () => {
      cancelled = true;
    };
  }, [id, setSessionRunning]);

  return (
    <section className="h-full flex flex-col">
      <PageHeader>
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink onClick={navigateToHome}>
                {t('header.home')}
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbLink onClick={handleBackToAgent}>
                {t('header.flow')}
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>
                {agentDetail?.title || t('explore.title')}
              </BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
      </PageHeader>

      <section className="flex flex-1 min-h-0">
        <div className="w-[296px] border-r min-w-0">
          <SessionList
            selectedSessionId={sessionId}
            runningSessionIds={runningSessionIds}
            runningRunsBySession={runningRunsBySession}
            onSelectSession={handleSessionSelect}
          />
        </div>

        <div className="flex-1 min-w-0">
          <SessionChat session={session} />
        </div>
      </section>
    </section>
  );
}

export default function AgentExplore() {
  return (
    <ExploreRunProvider>
      <AgentExploreContent />
    </ExploreRunProvider>
  );
}
