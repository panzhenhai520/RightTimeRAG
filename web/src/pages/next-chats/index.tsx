import { EmptyCardType } from '@/components/empty/constant';
import { EmptyAppCard } from '@/components/empty/empty';
import { MoreButton } from '@/components/more-button';
import { RAGFlowAvatar } from '@/components/ragflow-avatar';
import { RenameDialog } from '@/components/rename-dialog';
import { Button } from '@/components/ui/button';
import { SearchInput } from '@/components/ui/input';
import { Spin } from '@/components/ui/spin';
import { ChatSearchParams } from '@/constants/chat';
import { ChatApiAction, useFetchChatList } from '@/hooks/use-chat-request';
import { IConversation, IDialog } from '@/interfaces/database/chat';
import { cn } from '@/lib/utils';
import { Routes } from '@/routes';
import chatService from '@/services/next-chat-service';
import api from '@/utils/api';
import { formatDate } from '@/utils/date';
import { useQuery } from '@tanstack/react-query';
import { MessageSquareText, Plus } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router';
import { ChatDropdown } from './chat-dropdown';
import { useRenameChat } from './hooks/use-rename-chat';

const getChatDescription = (chat?: IDialog) =>
  chat?.description || chat?.kb_names?.join(' / ') || '';

const getSessionPreview = (session: IConversation) => {
  const messages = session.messages ?? [];
  const latest = messages[messages.length - 1]?.content || session.name;
  return typeof latest === 'string' ? latest.replace(/\s+/g, ' ') : '';
};

export default function ChatList() {
  const { data, handleInputChange, searchString } = useFetchChatList({
    page: 1,
    pageSize: 1000,
  });
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [selectedChatId, setSelectedChatId] = useState('');
  const {
    initialChatName,
    chatRenameVisible,
    showChatRenameModal,
    hideChatRenameModal,
    onChatRenameOk,
    chatRenameLoading,
  } = useRenameChat();

  const handleShowCreateModal = useCallback(() => {
    showChatRenameModal();
  }, [showChatRenameModal]);

  const [searchParams, setSearchParams] = useSearchParams();
  const isCreate = searchParams.get('isCreate') === 'true';
  useEffect(() => {
    if (isCreate) {
      handleShowCreateModal();
      searchParams.delete('isCreate');
      setSearchParams(searchParams);
    }
  }, [isCreate, handleShowCreateModal, searchParams, setSearchParams]);

  const chats = data.chats ?? [];
  const chatCount = data.total ?? chats.length;

  useEffect(() => {
    if (!chats.length) {
      setSelectedChatId('');
      return;
    }
    if (!selectedChatId || !chats.some((chat) => chat.id === selectedChatId)) {
      setSelectedChatId(chats[0].id);
    }
  }, [chats, selectedChatId]);

  const selectedChat = useMemo(
    () => chats.find((chat) => chat.id === selectedChatId),
    [chats, selectedChatId],
  );

  const { data: sessions = [], isFetching: sessionsLoading } = useQuery<
    IConversation[]
  >({
    queryKey: [ChatApiAction.FetchSessionList, selectedChatId, 'overview'],
    initialData: [],
    gcTime: 0,
    enabled: !!selectedChatId,
    refetchOnWindowFocus: false,
    queryFn: async () => {
      const { data } = await chatService.listSessions(
        { url: api.listSessions(selectedChatId) },
        true,
      );
      return data?.data ?? [];
    },
  });

  const handleOpenChat = useCallback(
    (chatId?: string, sessionId?: string, isNew?: boolean) => {
      if (!chatId) return;
      if (!sessionId) {
        navigate(`${Routes.Chat}/${chatId}`);
        return;
      }

      const params = new URLSearchParams();
      params.set(ChatSearchParams.ConversationId, sessionId);
      params.set(ChatSearchParams.isNew, isNew ? 'true' : '');
      navigate(`${Routes.Chat}/${chatId}?${params.toString()}`);
    },
    [navigate],
  );

  return (
    <>
      {chats.length || searchString ? (
        <article
          className="size-full flex flex-col px-5 py-6"
          data-testid="chats-list"
        >
          <div className="flex min-h-0 flex-1 overflow-hidden rounded-xl border border-border bg-bg-base shadow-sm">
            <aside className="flex w-[360px] shrink-0 flex-col border-r border-border bg-bg-card/45">
              <header className="space-y-3 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h1 className="text-lg font-semibold text-text-primary">
                      {t('chat.chatAssistantCount', { count: chatCount })}
                    </h1>
                    <p className="text-xs text-text-secondary">
                      {t('chat.conversations')}
                    </p>
                  </div>
                  <Button
                    data-testid="create-chat"
                    size="sm"
                    onClick={handleShowCreateModal}
                  >
                    <Plus className="size-[1em]" />
                    {t('chat.createChatAssistant')}
                  </Button>
                </div>
                <SearchInput
                  value={searchString}
                  onChange={handleInputChange}
                />
              </header>

              {chats.length ? (
                <>
                  <nav className="min-h-0 flex-1 overflow-auto px-3 pb-3">
                    <ul className="space-y-1">
                      {chats.map((chat) => {
                        const selected = chat.id === selectedChatId;
                        return (
                          <li
                            key={chat.id}
                            className={cn(
                              'group flex items-center gap-2 rounded-lg border border-transparent px-2 py-2 transition-colors',
                              selected
                                ? 'border-[#d4a3b1] bg-[#f7eef1] text-[#5b2737] dark:border-[#416b83] dark:bg-[#143047] dark:text-[#d7e7f0]'
                                : 'hover:bg-bg-base',
                            )}
                          >
                            <button
                              type="button"
                              className="flex min-w-0 flex-1 items-center gap-2 text-left"
                              onClick={() => setSelectedChatId(chat.id)}
                            >
                              <RAGFlowAvatar
                                avatar={chat.icon}
                                name={chat.name}
                                className="size-10 shrink-0"
                              />
                              <span className="min-w-0 flex-1">
                                <span className="block truncate text-sm font-semibold">
                                  {chat.name}
                                </span>
                                <span className="block truncate text-xs text-text-secondary">
                                  {getChatDescription(chat) ||
                                    t('chat.assistantSetting')}
                                </span>
                              </span>
                            </button>
                            <ChatDropdown
                              chat={chat}
                              showChatRenameModal={showChatRenameModal}
                            >
                              <MoreButton />
                            </ChatDropdown>
                          </li>
                        );
                      })}
                    </ul>
                  </nav>
                  <footer className="border-t border-border px-4 py-3 text-xs text-text-secondary">
                    {t('common.total')} {chatCount}
                  </footer>
                </>
              ) : (
                <div className="flex flex-1 items-center justify-center p-5">
                  <EmptyAppCard
                    showIcon
                    size="large"
                    className="w-full p-8"
                    isSearch
                    type={EmptyCardType.Chat}
                    testId="chats-empty-create"
                  />
                </div>
              )}
            </aside>

            <main className="min-w-0 flex-1 overflow-auto bg-bg-base">
              {selectedChat ? (
                <div className="mx-auto flex min-h-full max-w-5xl flex-col px-8 py-7">
                  <header className="mb-6 flex items-start justify-between gap-5">
                    <div className="flex min-w-0 items-start gap-4">
                      <RAGFlowAvatar
                        avatar={selectedChat.icon}
                        name={selectedChat.name}
                        className="size-16 shrink-0"
                      />
                      <div className="min-w-0">
                        <h2 className="truncate text-2xl font-semibold text-text-primary">
                          {selectedChat.name}
                        </h2>
                        <p className="mt-1 line-clamp-2 max-w-3xl text-sm leading-6 text-text-secondary">
                          {getChatDescription(selectedChat) ||
                            t('chat.chatConfigurationDescription')}
                        </p>
                      </div>
                    </div>
                    <Button
                      className="mt-6 shrink-0"
                      onClick={() => handleOpenChat(selectedChat.id)}
                    >
                      <MessageSquareText className="size-[1em]" />
                      {t('chat.startChat')}
                    </Button>
                  </header>

                  <section className="min-h-0 flex-1">
                    <div className="mb-3 flex items-center justify-between">
                      <h3 className="text-base font-semibold text-text-primary">
                        {t('chat.historySessionCount', {
                          count: sessions.length,
                        })}
                      </h3>
                    </div>

                    {sessionsLoading ? (
                      <div className="flex min-h-[120px] items-center justify-center rounded-lg border border-border bg-bg-card p-5">
                        <Spin />
                      </div>
                    ) : sessions.length ? (
                      <ul className="space-y-2">
                        {sessions.map((session) => (
                          <li key={session.id}>
                            <button
                              type="button"
                              className="w-full rounded-lg border border-border bg-[#fdfbfc] px-4 py-3 text-left transition-colors hover:border-[#d4a3b1] hover:bg-[#faf5f7] dark:bg-[#203747]/55 dark:hover:border-[#416b83] dark:hover:bg-[#132c41]"
                              onClick={() =>
                                handleOpenChat(
                                  selectedChat.id,
                                  session.id,
                                  session.is_new,
                                )
                              }
                            >
                              <div className="flex items-center justify-between gap-4">
                                <span className="truncate text-sm font-semibold text-text-primary">
                                  {session.name}
                                </span>
                                <span className="shrink-0 text-xs text-text-secondary">
                                  {formatDate(
                                    session.update_date ||
                                      session.update_time ||
                                      session.create_date,
                                  )}
                                </span>
                              </div>
                              <p className="mt-1 line-clamp-2 text-xs leading-5 text-text-secondary">
                                {getSessionPreview(session)}
                              </p>
                            </button>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <div className="flex min-h-[260px] flex-col items-center justify-center rounded-lg border border-dashed border-border bg-bg-card/60 p-8 text-center">
                        <MessageSquareText className="mb-3 size-10 text-text-secondary" />
                        <p className="mb-4 text-sm text-text-secondary">
                          {t('message.noData')}
                        </p>
                        <Button onClick={() => handleOpenChat(selectedChat.id)}>
                          {t('chat.newConversation')}
                        </Button>
                      </div>
                    )}
                  </section>
                </div>
              ) : (
                <div className="flex h-full items-center justify-center">
                  <EmptyAppCard
                    showIcon
                    size="large"
                    className="w-[480px] p-14"
                    isSearch={!!searchString}
                    type={EmptyCardType.Chat}
                    testId="chats-empty-create"
                  />
                </div>
              )}
            </main>
          </div>
        </article>
      ) : (
        <article
          className="size-full flex items-center justify-center"
          data-testid="chats-list"
        >
          <EmptyAppCard
            showIcon
            size="large"
            className="w-[480px] p-14"
            type={EmptyCardType.Chat}
            onClick={() => handleShowCreateModal()}
            testId="chats-empty-create"
          />
        </article>
      )}

      {chatRenameVisible && (
        <RenameDialog
          hideModal={hideChatRenameModal}
          onOk={onChatRenameOk}
          initialName={initialChatName}
          loading={chatRenameLoading}
          title={initialChatName || t('chat.createChatAssistant')}
        ></RenameDialog>
      )}
    </>
  );
}
