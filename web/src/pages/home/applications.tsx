import { HomeIcon } from '@/components/svg-icon';
import { Routes } from '@/routes';
import { ReactNode, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { Agents } from './agent-list';
import { SeeAllAppCard } from './application-card';
import { ChatList } from './chat-list';
import { MemoryList } from './memory-list';
import { SearchList } from './search-list';

type WorkspaceSectionProps = {
  title: string;
  description: string;
  icon: string;
  route?: Routes;
  children: ReactNode;
  listLength: number;
  loading: boolean;
};

function WorkspaceSection({
  title,
  description,
  icon,
  route,
  children,
  listLength,
  loading,
}: WorkspaceSectionProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <section className="rounded-xl bg-bg-base/70 p-5 shadow-sm ring-1 ring-border-default/20 dark:bg-bg-component/45">
      <header className="mb-4 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="flex items-center text-xl font-semibold leading-7">
            <HomeIcon imgClass="me-2.5" name={icon} width={22} />
            {title}
          </h2>
          <p className="mt-1 text-sm leading-6 text-text-secondary">
            {description}
          </p>
        </div>

        {route && listLength > 0 && (
          <button
            type="button"
            className="shrink-0 rounded-full px-3 py-1.5 text-sm text-text-secondary transition hover:bg-bg-card hover:text-text-primary"
            onClick={() => navigate(route)}
          >
            {t('common.seeAll')}
          </button>
        )}
      </header>

      {listLength <= 0 && !loading ? (
        <div className="rounded-lg bg-bg-card/45 px-4 py-8 text-center text-sm text-text-secondary">
          {t('homeDashboard.emptySection')}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {children}
          {route && listLength > 0 && (
            <SeeAllAppCard click={() => navigate(route)} />
          )}
        </div>
      )}
    </section>
  );
}

export function Applications() {
  const { t } = useTranslation();
  const [chatLength, setChatLength] = useState(0);
  const [chatLoading, setChatLoading] = useState(false);
  const [searchLength, setSearchLength] = useState(0);
  const [searchLoading, setSearchLoading] = useState(false);
  const [agentLength, setAgentLength] = useState(0);
  const [agentLoading, setAgentLoading] = useState(false);
  const [memoryLength, setMemoryLength] = useState(0);
  const [memoryLoading, setMemoryLoading] = useState(false);

  return (
    <section className="mt-8 grid gap-6">
      <WorkspaceSection
        title={t('homeDashboard.chatAssistants')}
        description={t('homeDashboard.chatAssistantsDescription')}
        icon="chats"
        route={Routes.Chats}
        listLength={chatLength}
        loading={chatLoading}
      >
        <ChatList
          setListLength={(length: number) => setChatLength(length)}
          setLoading={(loading: boolean) => setChatLoading(loading)}
        />
      </WorkspaceSection>

      <WorkspaceSection
        title={t('homeDashboard.searchTools')}
        description={t('homeDashboard.searchToolsDescription')}
        icon="searches"
        route={Routes.Searches}
        listLength={searchLength}
        loading={searchLoading}
      >
        <SearchList
          setListLength={(length: number) => setSearchLength(length)}
          setLoading={(loading: boolean) => setSearchLoading(loading)}
        />
      </WorkspaceSection>

      <WorkspaceSection
        title={t('homeDashboard.publishedAgents')}
        description={t('homeDashboard.publishedAgentsDescription')}
        icon="agents"
        listLength={agentLength}
        loading={agentLoading}
      >
        <Agents
          setListLength={(length: number) => setAgentLength(length)}
          setLoading={(loading: boolean) => setAgentLoading(loading)}
        />
      </WorkspaceSection>

      <WorkspaceSection
        title={t('homeDashboard.recentMemos')}
        description={t('homeDashboard.recentMemosDescription')}
        icon="memory"
        listLength={memoryLength}
        loading={memoryLoading}
      >
        <MemoryList
          setListLength={(length: number) => setMemoryLength(length)}
          setLoading={(loading: boolean) => setMemoryLoading(loading)}
        />
      </WorkspaceSection>
    </section>
  );
}
