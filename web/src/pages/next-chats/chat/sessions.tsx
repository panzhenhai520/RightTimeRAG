import { ConfirmDeleteDialog } from '@/components/confirm-delete-dialog';
import EmbedDialog from '@/components/embed-dialog';
import { useShowEmbedModal } from '@/components/embed-dialog/use-show-embed-dialog';
import { MoreButton } from '@/components/more-button';
import { RAGFlowAvatar } from '@/components/ragflow-avatar';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { SearchInput } from '@/components/ui/input';
import message from '@/components/ui/message';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { SharedFrom } from '@/constants/chat';
import { useSetModalState } from '@/hooks/common-hooks';
import {
  useFetchChat,
  useGetChatSearchParams,
  useOrganizeSessions,
  useRemoveSessions,
} from '@/hooks/use-chat-request';
import {
  Divide,
  Loader2,
  LucideListChecks,
  LucideMinus,
  LucidePanelLeftClose,
  LucidePlus,
  LucideSend,
  LucideTrash2,
  LucideUndo2,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router';
import { useChatUrlParams } from '../hooks/use-chat-url';
import { useHandleClickConversationCard } from '../hooks/use-click-card';
import { useSelectDerivedConversationList } from '../hooks/use-select-conversation-list';
import { ConversationDropdown } from './conversation-dropdown';

type SessionProps = Pick<
  ReturnType<typeof useHandleClickConversationCard>,
  'handleConversationCardClick' | 'stopOutputMessage'
> & {
  /** Auto-collapse the session list while an answer is generating. */
  autoCollapsed?: boolean;
  loadingConversationIds?: string[];
  onConversationRefresh?: (conversationId: string) => void | Promise<void>;
  onConversationsRemoved?: (conversationIds: string[]) => void;
};
export function Sessions({
  handleConversationCardClick,
  stopOutputMessage,
  autoCollapsed = false,
  loadingConversationIds = [],
  onConversationRefresh,
  onConversationsRemoved,
}: SessionProps) {
  const { t } = useTranslation();
  const {
    list: conversationList,
    addTemporaryConversation,
    removeTemporaryConversation,
    handleInputChange,
    searchString,
  } = useSelectDerivedConversationList();
  const { data } = useFetchChat();
  const { visible, switchVisible, hideModal } = useSetModalState(true);

  // Auto-collapse when generation starts, and keep it collapsed afterwards to
  // preserve horizontal space for the chat + recall area. The user can re-open
  // the session list manually via the toggle. Only acts on the false→true
  // transition so a manual toggle is never clobbered.
  const prevAutoCollapsedRef = useRef(autoCollapsed);
  useEffect(() => {
    if (autoCollapsed && !prevAutoCollapsedRef.current) {
      hideModal();
    }
    prevAutoCollapsedRef.current = autoCollapsed;
  }, [autoCollapsed, hideModal]);
  const { removeSessions } = useRemoveSessions();
  const { organizeSessions } = useOrganizeSessions();
  const { setConversationBoth } = useChatUrlParams();
  const { conversationId } = useGetChatSearchParams();

  // Selection mode state
  const [selectionMode, setSelectionMode] = useState(false);
  const [organizeMode, setOrganizeMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Toggle selection mode (click batch delete icon)
  const toggleSelectionMode = useCallback(() => {
    setSelectionMode(true);
    setOrganizeMode(false);
    setSelectedIds(new Set());
  }, []);

  const toggleOrganizeMode = useCallback(() => {
    setOrganizeMode(true);
    setSelectionMode(false);
    setSelectedIds(new Set());
  }, []);

  // Exit selection mode (click return icon)
  const exitSelectionMode = useCallback(() => {
    setSelectionMode(false);
    setOrganizeMode(false);
    setSelectedIds(new Set());
  }, []);

  // Toggle single item selection
  const toggleSelection = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  }, []);

  // Toggle select all
  const toggleSelectAll = useCallback(() => {
    setSelectedIds((prev) => {
      if (prev.size === conversationList.length) {
        return new Set();
      }
      return new Set(conversationList.map((x) => x.id));
    });
  }, [conversationList]);

  // Batch delete
  const handleBatchDelete = useCallback(async () => {
    if (selectedIds.size === 0) {
      return;
    }

    const selectedIdList = Array.from(selectedIds);
    const deletingLoadingConversation = selectedIdList.some((id) =>
      loadingConversationIds.includes(id),
    );
    if (deletingLoadingConversation) {
      stopOutputMessage?.();
    }
    const currentConversationDeleted = conversationId
      ? selectedIdList.includes(conversationId)
      : false;
    const temporaryIdSet = new Set(
      conversationList.filter((item) => item.is_new).map((item) => item.id),
    );
    const persistedIds: string[] = [];
    const removedIds: string[] = [];

    selectedIdList.forEach((id) => {
      if (temporaryIdSet.has(id)) {
        removeTemporaryConversation(id);
        removedIds.push(id);
      } else {
        persistedIds.push(id);
      }
    });

    let removeCode = -1;
    if (persistedIds.length > 0) {
      removeCode = await removeSessions(persistedIds);
      if (removeCode === 0) {
        removedIds.push(...persistedIds);
      }
    }

    if (currentConversationDeleted && conversationId) {
      const currentIsTemporary = temporaryIdSet.has(conversationId);
      const currentPersistedDeleted =
        persistedIds.includes(conversationId) && removeCode === 0;
      if (currentIsTemporary || currentPersistedDeleted) {
        setConversationBoth('', '');
      }
    }
    if (removedIds.length > 0) {
      onConversationsRemoved?.(removedIds);
    }
    exitSelectionMode();
  }, [
    selectedIds,
    conversationId,
    conversationList,
    setConversationBoth,
    removeTemporaryConversation,
    loadingConversationIds,
    stopOutputMessage,
    removeSessions,
    onConversationsRemoved,
    exitSelectionMode,
  ]);

  const handleOrganizeSessions = useCallback(async () => {
    const selectedIdList = Array.from(selectedIds);
    const persistedIds = selectedIdList.filter(
      (id) => !conversationList.find((item) => item.id === id)?.is_new,
    );

    if (persistedIds.length === 0) {
      message.info(t('chat.organizeSessionsNoPersisted'));
      return;
    }

    const payload = await organizeSessions(persistedIds);
    if (payload?.code === 0) {
      const data = payload.data || {};
      const nextSessionId = data.target_session_id || persistedIds[0];
      message.success(
        t('chat.organizeSessionsSuccess', {
          kept_turns: data.kept_turns ?? 0,
          dropped_duplicate_turns: data.dropped_duplicate_turns ?? 0,
          dropped_error_turns: data.dropped_error_turns ?? 0,
          removed_sessions: data.removed_sessions ?? 0,
        }),
      );
      exitSelectionMode();
      if (nextSessionId) {
        setConversationBoth(nextSessionId, '');
        void onConversationRefresh?.(nextSessionId);
      }
    } else {
      message.error(payload?.message || t('chat.organizeSessions'));
    }
  }, [
    conversationList,
    exitSelectionMode,
    organizeSessions,
    selectedIds,
    setConversationBoth,
    onConversationRefresh,
    t,
  ]);

  const selectedCount = useMemo(() => selectedIds.size, [selectedIds]);

  const { id } = useParams();
  const { showEmbedModal, hideEmbedModal, embedVisible, beta } =
    useShowEmbedModal();

  if (!visible) {
    return (
      <div className="p-5">
        <Button
          variant="transparent"
          size="icon-sm"
          className="relative border-0"
          onClick={switchVisible}
          data-testid="chat-detail-sessions-open"
        >
          <RAGFlowAvatar
            avatar={data.icon}
            name={data.name}
            className="size-8 cursor-pointer"
          />
          {loadingConversationIds.length > 0 && (
            <Loader2 className="absolute -right-1 -top-1 size-3.5 animate-spin text-text-secondary" />
          )}
        </Button>
      </div>
    );
  }

  return (
    <aside
      className="px-4 py-4 w-[276px] flex flex-col"
      role="complementary"
      data-testid="chat-detail-sessions"
    >
      <header className="flex items-center text-sm justify-between gap-3">
        <div className="flex gap-2.5 items-center min-w-0">
          <RAGFlowAvatar
            avatar={data.icon}
            name={data.name}
            className="size-7"
          />

          <span className="flex-1 truncate font-medium leading-5">
            {data.name}
          </span>
        </div>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              onClick={showEmbedModal}
              size="icon-xs"
              data-testid="chat-detail-embed-open"
            >
              <LucideSend />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{t('common.embedIntoSite')}</TooltipContent>
        </Tooltip>

        <EmbedDialog
          visible={embedVisible}
          hideModal={hideEmbedModal}
          token={id!}
          from={SharedFrom.Chat}
          beta={beta}
          isAgent={false}
        />

        <Button
          variant="transparent"
          size="icon-sm"
          className="border-0 ml-auto"
          onClick={switchVisible}
          data-testid="chat-detail-sessions-close"
        >
          <LucidePanelLeftClose />
        </Button>
      </header>

      <div className="flex justify-between items-center mb-3 pt-6">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold">
            {t('chat.conversations')}
          </span>
          <data
            className="text-text-secondary text-xs"
            value={conversationList.length}
          >
            {conversationList.length}
          </data>
        </div>

        <div className="flex items-center gap-2">
          {selectionMode || organizeMode ? (
            // Exit selection mode
            <Button
              variant="ghost"
              size="icon-xs"
              onClick={exitSelectionMode}
              data-testid="chat-detail-session-selection-exit"
            >
              <LucideUndo2 size={16} />
            </Button>
          ) : (
            // New conversation
            <Button
              variant="ghost"
              size="icon-xs"
              onClick={addTemporaryConversation}
              data-testid="chat-detail-session-new"
            >
              <LucidePlus className="h-4 w-4" />
            </Button>
          )}

          {selectionMode && selectedCount > 0 ? (
            // Delete selected items
            <ConfirmDeleteDialog
              onOk={handleBatchDelete}
              title={t('chat.batchDeleteSessions')}
              content={{
                title: t('chat.deleteSelectedConfirm', {
                  count: selectedCount,
                }),
              }}
              testId="chat-detail-session-batch-delete-dialog"
              confirmButtonTestId="chat-detail-session-batch-delete-confirm"
              cancelButtonTestId="chat-detail-session-batch-delete-cancel"
            >
              <Button
                variant="delete"
                size="icon-xs"
                data-testid="chat-detail-session-batch-delete"
              >
                <LucideTrash2 />
              </Button>
            </ConfirmDeleteDialog>
          ) : organizeMode && selectedCount > 0 ? (
            <ConfirmDeleteDialog
              onOk={handleOrganizeSessions}
              title={t('chat.organizeSessions')}
              content={{
                title: t('chat.organizeSessionsConfirm', {
                  count: selectedCount,
                }),
              }}
              testId="chat-detail-session-organize-dialog"
              confirmButtonTestId="chat-detail-session-organize-confirm"
              cancelButtonTestId="chat-detail-session-organize-cancel"
            >
              <Button
                variant="ghost"
                size="icon-xs"
                data-testid="chat-detail-session-organize"
              >
                <Divide />
              </Button>
            </ConfirmDeleteDialog>
          ) : (
            <Button
              variant="ghost"
              size="icon-xs"
              onClick={
                selectionMode || organizeMode
                  ? toggleSelectAll
                  : toggleSelectionMode
              }
              data-testid={
                selectionMode
                  ? 'chat-detail-session-select-all'
                  : organizeMode
                    ? 'chat-detail-session-organize-select-all'
                    : 'chat-detail-session-selection-enable'
              }
            >
              {selectionMode ? (
                <LucideListChecks />
              ) : organizeMode ? (
                <Divide />
              ) : (
                <LucideMinus />
              )}
            </Button>
          )}

          {!selectionMode && !organizeMode && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-xs"
                  onClick={toggleOrganizeMode}
                  data-testid="chat-detail-session-organize-enable"
                >
                  <Divide />
                </Button>
              </TooltipTrigger>
              <TooltipContent>{t('chat.organizeSessions')}</TooltipContent>
            </Tooltip>
          )}
        </div>
      </div>

      <div className="pb-3" role="search">
        <SearchInput
          onChange={handleInputChange}
          value={searchString}
          data-testid="chat-detail-session-search"
        ></SearchInput>
      </div>

      <div className="flex-1 overflow-auto">
        {selectionMode || organizeMode ? (
          <ul className="space-y-1" role="listbox" aria-multiselectable>
            {conversationList.map((x) => (
              <li
                key={x.id}
                className="py-1 text-xs leading-5"
                role="option"
                aria-selected={selectedIds.has(x.id)}
                data-session-id={x.id}
              >
                <label className="flex items-center gap-2">
                  <Checkbox
                    checked={selectedIds.has(x.id)}
                    onCheckedChange={() => toggleSelection(x.id)}
                    data-testid="chat-detail-session-checkbox"
                    data-session-id={x.id}
                  />

                  <span className="truncate">{x.name}</span>
                </label>
              </li>
            ))}
          </ul>
        ) : (
          <nav aria-label={t('chat.conversations')}>
            <ul className="space-y-1">
              {conversationList.map((x) => (
                <li
                  key={x.id}
                  className="
                      group pr-2 flex items-center gap-1 rounded-md text-xs leading-5
                      aria-selected:bg-bg-card has-[>button:focus-visible]:bg-bg-card
                    "
                  aria-selected={conversationId === x.id}
                >
                  <button
                    type="button"
                    className="focus-visible:outline-none px-2.5 py-1.5 text-left flex-1 min-w-0"
                    onClick={() => handleConversationCardClick(x.id, x.is_new)}
                    data-testid="chat-detail-session-item"
                    data-session-id={x.id}
                  >
                    <span className="flex min-w-0 items-center gap-1">
                      {loadingConversationIds.includes(x.id) && (
                        <Loader2 className="size-3.5 shrink-0 animate-spin text-text-secondary" />
                      )}
                      <span className="min-w-0 truncate">{x.name}</span>
                    </span>
                  </button>

                  <ConversationDropdown
                    conversation={x}
                    removeTemporaryConversation={removeTemporaryConversation}
                    loadingConversationIds={loadingConversationIds}
                    stopOutputMessage={stopOutputMessage}
                    onConversationsRemoved={onConversationsRemoved}
                  >
                    <MoreButton
                      data-testid="chat-detail-session-actions"
                      data-session-id={x.id}
                    ></MoreButton>
                  </ConversationDropdown>
                </li>
              ))}
            </ul>
          </nav>
        )}
      </div>
    </aside>
  );
}
