import { HomeIcon } from '@/components/svg-icon';
import { Routes } from '@/routes';
import { ReactNode, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { Agents } from './agent-list';
import { ChatList } from './chat-list';
import { MemoryList } from './memory-list';
import { SearchList } from './search-list';

type WorkspaceSectionProps = {
  title: string;
  description: string;
  icon: string;
  route?: Routes;
  emptyActionRoute?: string;
  children: ReactNode;
  listLength: number;
  loading: boolean;
};

function WorkspaceSection({
  title,
  description,
  icon,
  route,
  emptyActionRoute,
  children,
  listLength,
  loading,
}: WorkspaceSectionProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <section className="min-w-0 rounded-xl bg-bg-base/70 p-4 shadow-sm ring-1 ring-border-default/20 dark:bg-bg-component/45">
      <header className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="flex items-center text-base font-semibold leading-6">
            <HomeIcon imgClass="me-2" name={icon} width={18} />
            {title}
          </h2>
          <p className="mt-1 line-clamp-2 text-xs leading-5 text-text-secondary">
            {description}
          </p>
        </div>

        {route && listLength > 0 && (
          <button
            type="button"
            className="shrink-0 rounded-full px-2.5 py-1 text-xs text-text-secondary transition hover:bg-bg-card hover:text-text-primary"
            onClick={() => navigate(route)}
          >
            {t('common.seeAll')}
          </button>
        )}
      </header>

      <div
        className={
          listLength <= 0 && !loading
            ? 'hidden'
            : 'grid gap-3 [&>article]:h-[112px] [&>article]:min-h-0 [&>article]:overflow-hidden'
        }
      >
        {children}
      </div>

      {listLength <= 0 && !loading && (
        <div className="rounded-lg bg-bg-card/45 px-4 py-8 text-center text-sm text-text-secondary">
          <div>{t('homeDashboard.emptySection')}</div>
          {emptyActionRoute && (
            <button
              type="button"
              className="mt-4 rounded-full bg-accent-primary px-4 py-2 text-sm font-medium text-white transition hover:opacity-90"
              onClick={() => navigate(emptyActionRoute)}
            >
              {t('homeDashboard.manageOrCreate')}
            </button>
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
    <section className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <WorkspaceSection
        title={t('homeDashboard.chatAssistants')}
        description={t('homeDashboard.chatAssistantsDescription')}
        icon="chats"
        route={Routes.Chats}
        emptyActionRoute={Routes.DevSettingPanython}
        listLength={chatLength}
        loading={chatLoading}
      >
        <ChatList
          pageSize={8}
          displayLimit={2}
          setListLength={(length: number) => setChatLength(length)}
          setLoading={(loading: boolean) => setChatLoading(loading)}
        />
      </WorkspaceSection>

      <WorkspaceSection
        title={t('homeDashboard.recentMemos')}
        description={t('homeDashboard.recentMemosDescription')}
        icon="memory"
        route={Routes.Memories}
        emptyActionRoute={Routes.DevSettingPanython}
        listLength={memoryLength}
        loading={memoryLoading}
      >
        <MemoryList
          pageSize={8}
          displayLimit={2}
          setListLength={(length: number) => setMemoryLength(length)}
          setLoading={(loading: boolean) => setMemoryLoading(loading)}
        />
      </WorkspaceSection>

      <WorkspaceSection
        title={t('homeDashboard.searchTools')}
        description={t('homeDashboard.searchToolsDescription')}
        icon="searches"
        route={Routes.Searches}
        emptyActionRoute={Routes.DevSettingPanython}
        listLength={searchLength}
        loading={searchLoading}
      >
        <SearchList
          pageSize={8}
          displayLimit={2}
          setListLength={(length: number) => setSearchLength(length)}
          setLoading={(loading: boolean) => setSearchLoading(loading)}
        />
      </WorkspaceSection>

      <WorkspaceSection
        title={t('homeDashboard.publishedAgents')}
        description={t('homeDashboard.publishedAgentsDescription')}
        icon="agents"
        route={Routes.Agents}
        emptyActionRoute={Routes.DevSettingPanython}
        listLength={agentLength}
        loading={agentLoading}
      >
        <Agents
          pageSize={8}
          displayLimit={2}
          setListLength={(length: number) => setAgentLength(length)}
          setLoading={(loading: boolean) => setAgentLoading(loading)}
        />
      </WorkspaceSection>
    </section>
  );
}
