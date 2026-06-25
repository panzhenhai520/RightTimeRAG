import {
  ConfirmDeleteDialog,
  ConfirmDeleteDialogNode,
} from '@/components/confirm-delete-dialog';
import { EmptyType } from '@/components/empty/constant';
import Empty from '@/components/empty/empty';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/ui/modal/modal';
import { RAGFlowPagination } from '@/components/ui/ragflow-pagination';
import { Switch } from '@/components/ui/switch';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { RunningStatus } from '@/constants/knowledge';
import { Pagination } from '@/interfaces/common';
import { cn } from '@/lib/utils';
import ProcessLogModal, {
  ILogInfo,
  replaceText,
} from '@/pages/dataset/process-log-modal';
import { MemoryOptions } from '@/pages/memories/constants';
import {
  ColumnDef,
  ColumnFiltersState,
  ExpandedState,
  Row,
  SortingState,
  VisibilityState,
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getExpandedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import dayjs from 'dayjs';
import { t } from 'i18next';
import { pick } from 'lodash';
import {
  ChevronDown,
  ChevronUp,
  Eraser,
  ListChevronsDownUp,
  ListChevronsUpDown,
  TextSelect,
} from 'lucide-react';
import * as React from 'react';
import { useMemo, useState } from 'react';
import { useMessageAction } from './hook';
import { IMessageInfo } from './interface';

function stripProcessBlocks(text: string): string {
  return (text || '')
    .replace(/<think>[\s\S]*?<\/think>/gi, '')
    .replace(/<retrieving>[\s\S]*?<\/retrieving>/gi, '')
    .trim();
}

function isLongContent(text: string): boolean {
  const lines = text.split('\n').length;
  return lines > 3 || text.length > 240;
}

function typeRowClass(messageType: string, isSubRow: boolean): string {
  if (isSubRow) return '';
  if (messageType === 'raw') return 'bg-accent-primary/[.04]';
  if (messageType === 'semantic') return 'bg-state-success/[.04]';
  if (messageType === 'procedural') return 'bg-bg-list/30';
  return '';
}

export type MemoryTableProps = {
  messages: Array<IMessageInfo>;
  total: number;
  pagination: Pagination;
  setPagination: (params: { page: number; pageSize: number }) => void;
};

const columnHelper = createColumnHelper<IMessageInfo>();

function getTaskStatus(progress: number) {
  if (progress >= 1) {
    return RunningStatus.DONE;
  } else if (progress > 0 && progress < 1) {
    return RunningStatus.RUNNING;
  } else {
    return RunningStatus.FAIL;
  }
}

function hasForgetAt(value: unknown) {
  return Boolean(value && String(value) !== 'None');
}

export function MemoryTable({
  messages,
  total,
  pagination,
  setPagination,
}: MemoryTableProps) {
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>(
    [],
  );
  const [columnVisibility, setColumnVisibility] =
    React.useState<VisibilityState>({});
  const [expandedContent, setExpandedContent] = useState<Set<number>>(
    new Set(),
  );
  const toggleContentExpand = (id: number) => {
    setExpandedContent((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const {
    showDeleteDialog,
    setShowDeleteDialog,
    handleClickDeleteMessage,
    selectedMessage,
    handleDeleteMessage,

    handleClickUpdateMessageState,
    selectedMessageContent,
    showMessageContentDialog,
    setShowMessageContentDialog,
    handleClickMessageContentDialog,
  } = useMessageAction();

  const disabledRowFunc = (row: Row<IMessageInfo>) => {
    return hasForgetAt(row.original.forget_at);
  };

  const [isModalVisible, setIsModalVisible] = useState(false);
  const [logInfo, setLogInfo] = useState<ILogInfo>();
  const showLog = (row: Row<IMessageInfo>) => {
    const task = row.original.task;
    const logDetail = {
      startTime: dayjs(task.create_time)
        .locale(document.documentElement.lang)
        .format('MM/DD/YYYY HH:mm:ss'),
      status: getTaskStatus(task.progress),
      details: task.progress_msg,
    } as unknown as ILogInfo;
    setLogInfo(logDetail);
    setIsModalVisible(true);
  };
  // Define columns for the memory table
  const columns: ColumnDef<IMessageInfo>[] = useMemo(
    () => [
      {
        accessorKey: 'session_id',
        header: ({ table }) => (
          <div className="flex items-center gap-1">
            <button
              {...{
                onClick: table.getToggleAllRowsExpandedHandler(),
              }}
            >
              {table.getIsAllRowsExpanded() ? (
                <ListChevronsDownUp size={16} />
              ) : (
                <ListChevronsUpDown size={16} />
              )}
            </button>{' '}
            <span>{t('memory.messages.sessionId')}</span>
          </div>
        ),
        cell: ({ row }) => (
          <div className="flex items-center gap-1">
            {row.getCanExpand() ? (
              <button
                {...{
                  onClick: row.getToggleExpandedHandler(),
                  style: { cursor: 'pointer' },
                }}
              >
                {row.getIsExpanded() ? (
                  <ListChevronsDownUp size={16} />
                ) : (
                  <ListChevronsUpDown size={16} />
                )}
              </button>
            ) : (
              ''
            )}
            <div
              className={cn('text-sm font-medium', {
                'pl-5': !row.getCanExpand(),
              })}
            >
              {row.getValue('session_id')}
            </div>
          </div>
        ),
      },
      {
        accessorKey: 'agent_name',
        header: () => <span>{t('memory.messages.agent')}</span>,
        cell: ({ row }) => (
          <div className="text-sm font-medium ">
            {row.getValue('agent_name')}
          </div>
        ),
      },
      {
        accessorKey: 'message_type',
        header: () => <span>{t('memory.messages.type')}</span>,
        cell: ({ row }) => (
          <div className="text-sm font-medium  capitalize">
            {row.getValue('message_type')
              ? MemoryOptions(t).find(
                  (item) =>
                    item.value === (row.getValue('message_type') as string),
                )?.label
              : row.getValue('message_type')}
          </div>
        ),
      },
      {
        accessorKey: 'valid_at',
        header: () => <span>{t('memory.messages.validDate')}</span>,
        cell: ({ row }) => (
          <div className="text-sm ">{row.getValue('valid_at')}</div>
        ),
      },
      {
        accessorKey: 'forget_at',
        header: () => <span>{t('memory.messages.forgetAt')}</span>,
        cell: ({ row }) => (
          <div className="text-sm ">
            {hasForgetAt(row.getValue('forget_at'))
              ? row.getValue('forget_at')
              : t('memory.messages.notForgotten')}
          </div>
        ),
      },
      {
        accessorKey: 'content',
        header: () => <span>{t('memory.messages.content')}</span>,
        cell: ({ row }) => {
          const raw = row.original.content || '';
          const cleaned = stripProcessBlocks(raw);
          if (!cleaned) return null;
          const isExpanded = expandedContent.has(row.original.message_id);
          const long = isLongContent(cleaned);
          return (
            <div className="max-w-[400px] text-xs leading-5 text-text-primary">
              <div
                className={cn('whitespace-pre-line break-words', {
                  'line-clamp-3': long && !isExpanded,
                })}
              >
                {cleaned}
              </div>
              {long && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleContentExpand(row.original.message_id);
                  }}
                  className="mt-0.5 inline-flex items-center gap-0.5 text-[11px] text-accent-primary hover:underline"
                >
                  {isExpanded ? (
                    <>
                      收起 <ChevronUp className="size-3" />
                    </>
                  ) : (
                    <>
                      展开 <ChevronDown className="size-3" />
                    </>
                  )}
                </button>
              )}
            </div>
          );
        },
      },
      {
        accessorKey: 'status',
        header: () => <span>{t('memory.messages.enable')}</span>,
        cell: ({ row }) => {
          const isEnabled = row.getValue('status') as boolean;
          return (
            <div className="flex items-center">
              <Switch
                disabled={disabledRowFunc(row)}
                defaultChecked={isEnabled}
                onCheckedChange={(val) => {
                  handleClickUpdateMessageState(row.original, val);
                }}
              />
            </div>
          );
        },
      },
      columnHelper.display({
        id: 'task_progress',
        cell: ({ row }) => {
          const { task } = row.original;

          if (!task) {
            return null;
          }

          const taskStatus = getTaskStatus(task.progress);

          return (
            <Button
              variant="transparent"
              size="icon"
              className="border-0 size-8"
              onClick={() => {
                showLog(row);
              }}
            >
              <div
                className={cn('size-1 rounded-full', {
                  'bg-state-success': taskStatus === RunningStatus.DONE,
                  'bg-state-error': taskStatus === RunningStatus.FAIL,
                  'bg-state-warning': taskStatus === RunningStatus.RUNNING,
                })}
              />
            </Button>
          );
        },
      }),
      {
        accessorKey: 'action',
        header: () => <span>{t('memory.messages.action')}</span>,
        meta: {
          cellClassName: 'w-12',
        },
        cell: ({ row }) => (
          <div className=" flex opacity-0 group-hover:opacity-100">
            <Button
              variant={'ghost'}
              className="bg-transparent"
              onClick={() => {
                handleClickMessageContentDialog(row.original);
              }}
            >
              <TextSelect />
            </Button>
            <Button
              variant={'delete'}
              disabled={disabledRowFunc(row)}
              className="bg-transparent"
              aria-label="Edit"
              onClick={() => {
                handleClickDeleteMessage(row.original);
              }}
            >
              <Eraser />
            </Button>
          </div>
        ),
      },
    ],
    [handleClickDeleteMessage, expandedContent, toggleContentExpand],
  );

  const currentPagination = useMemo(() => {
    return {
      pageIndex: (pagination.current || 1) - 1,
      pageSize: pagination.pageSize || 10,
    };
  }, [pagination]);
  const [expanded, setExpanded] = React.useState<ExpandedState>({});
  const table = useReactTable({
    data: messages,
    columns,
    onExpandedChange: setExpanded,
    getSubRows: (row) => (row.extract as IMessageInfo[]) || undefined,
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    onColumnVisibilityChange: setColumnVisibility,
    manualPagination: true,
    state: {
      sorting,
      columnFilters,
      columnVisibility,
      pagination: currentPagination,
      expanded,
    },
    rowCount: total,
  });

  return (
    <div className="w-full">
      <Table rootClassName="max-h-[calc(100vh-292px)]">
        <TableHeader>
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <TableHead key={header.id}>
                  {header.isPlaceholder
                    ? null
                    : flexRender(
                        header.column.columnDef.header,
                        header.getContext(),
                      )}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody className="relative">
          {table.getRowModel().rows?.length ? (
            table.getRowModel().rows.map((row) => (
              <TableRow
                key={row.id}
                data-state={row.getIsSelected() && 'selected'}
                className={cn(
                  'group',
                  typeRowClass(row.original.message_type, !row.getCanExpand()),
                )}
              >
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))
          ) : (
            <TableRow>
              <TableCell colSpan={columns.length} className="h-24 text-center">
                <Empty type={EmptyType.Data} />
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      {showDeleteDialog && (
        <ConfirmDeleteDialog
          onOk={handleDeleteMessage}
          title={t('memory.messages.forgetMessage')}
          open={showDeleteDialog}
          onOpenChange={setShowDeleteDialog}
          okButtonText={t('memory.messages.forget')}
          content={{
            title: t('memory.messages.forgetMessageTip'),
            node: (
              <ConfirmDeleteDialogNode
                // avatar={{ avatar: selectedMessage.avatar, name: selectedMessage.name }}
                name={
                  t('memory.messages.sessionId') +
                  ': ' +
                  selectedMessage.session_id
                }
                warnText={t('memory.messages.delMessageWarn')}
              />
            ),
          }}
        />
      )}

      {showMessageContentDialog && (
        <Modal
          title={t('memory.messages.content')}
          open={showMessageContentDialog}
          onOpenChange={setShowMessageContentDialog}
          className="!w-[640px]"
          footer={
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowMessageContentDialog(false)}
                className={
                  'px-2 py-1 border border-border-button rounded-md hover:bg-bg-card hover:text-text-primary '
                }
              >
                {t('common.close')}
              </button>
            </div>
          }
        >
          <div className="flex flex-col gap-2.5">
            <div className="text-text-secondary text-sm">
              {t('memory.messages.sessionId')}:&nbsp;&nbsp;
              {selectedMessage.session_id}
            </div>
            {selectedMessageContent?.content && (
              <div className="w-full bg-accent-primary-5  whitespace-pre-line text-wrap rounded-lg h-fit max-h-[350px] overflow-y-auto scrollbar-auto px-2.5 py-1">
                {replaceText(selectedMessageContent?.content || '')}
              </div>
            )}
            {selectedMessageContent?.content_embed && (
              <div className="rounded-md border border-border-button bg-bg-card px-3 py-2 text-xs text-text-secondary">
                {t('memory.messages.contentEmbedHint')}
              </div>
            )}
          </div>
        </Modal>
      )}

      {isModalVisible && (
        <ProcessLogModal
          title={t('memory.taskLogDialog.title')}
          visible={isModalVisible}
          onCancel={() => setIsModalVisible(false)}
          translateKey="memory.taskLogDialog"
          logInfo={logInfo as unknown as ILogInfo}
        />
      )}

      <div className="flex items-center justify-end  absolute bottom-3 right-3">
        <RAGFlowPagination
          {...pick(pagination, 'current', 'pageSize')}
          total={total}
          onChange={(page, pageSize) => {
            setPagination({ page, pageSize });
          }}
        />
      </div>
    </div>
  );
}
