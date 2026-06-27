import CopyToClipboard from '@/components/copy-to-clipboard';
import Image from '@/components/image';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { MarkdownRemarkPlugins } from '@/constants/markdown-remark-plugins';
import type { IReferenceChunk } from '@/interfaces/database/chat';
import { isPlainObject } from 'lodash';
import { Maximize2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Markdown from 'react-markdown';
import rehypeRaw from 'rehype-raw';
import { extractNumbersFromMessageContent } from './utils';

type IProps = {
  referenceChunks?: IReferenceChunk[] | Record<string, IReferenceChunk>;
  messageContent: string;
};

type EvidenceItem = {
  chunk: IReferenceChunk;
  index: number;
};

type ReferenceEvidenceSelection = EvidenceItem;

function EvidenceMarkdown({ content }: { content?: string }) {
  if (!content) return null;
  return (
    <Markdown remarkPlugins={MarkdownRemarkPlugins} rehypePlugins={[rehypeRaw]}>
      {content}
    </Markdown>
  );
}

function EvidenceThumbnail({ imageId, fig }: { imageId: string; fig: number }) {
  return (
    <div className="h-full min-h-0 overflow-hidden rounded border border-border-default bg-[#eef2f5] dark:!border-[#7aa4ba]/32 dark:!bg-[#1f3747]">
      <Image
        id={imageId}
        className="size-full max-h-none max-w-none object-cover object-center"
        alt={`Fig. ${fig.toString()}`}
      />
    </div>
  );
}

function EvidenceCard({
  chunk,
  index,
  onOpenEvidence,
}: EvidenceItem & {
  onOpenEvidence?: (selection: ReferenceEvidenceSelection) => void;
}) {
  const { t } = useTranslation();

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={() => onOpenEvidence?.({ chunk, index })}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onOpenEvidence?.({ chunk, index });
        }
      }}
      aria-label={t('chat.openEvidenceInRecall', { fig: index + 1 })}
      className="flex h-48 min-h-0 cursor-pointer flex-col overflow-hidden rounded-md border border-[#eef0f3] bg-[#fcfcfd] p-3 text-[13px] leading-5 text-text-primary shadow-sm transition-colors hover:border-primary/25 hover:bg-[#f6f8fa] hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25 dark:!border-[#7aa4ba]/42 dark:!bg-[#243d4e] dark:!text-[#dbeaf2] dark:shadow-[0_8px_20px_rgba(4,25,39,0.12)] dark:hover:!border-[#8fb7ca]/58 dark:hover:!bg-[#2a4658] dark:hover:shadow-[0_10px_28px_rgba(4,25,39,0.16)]"
    >
      <div className="mb-2 flex min-h-7 items-center gap-2 text-[13px] leading-5">
        <span className="shrink-0 font-semibold">Fig. {index + 1}</span>
        {chunk.is_raptor_summary && (
          <span className="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-[11px] leading-4 text-amber-800 dark:!bg-[#4a402b] dark:!text-[#ead6a2]">
            {t('chat.summaryCitation')}
          </span>
        )}
        <span className="min-w-0 flex-1 truncate font-medium text-text-secondary">
          {chunk.document_name}
        </span>
        {onOpenEvidence && (
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onOpenEvidence({ chunk, index });
            }}
            className="ml-auto shrink-0 rounded p-1 text-text-secondary hover:bg-[#e8eef2] hover:text-text-primary dark:hover:!bg-[#34566a] dark:hover:text-[#f2fbff]"
            title={t('chat.openEvidenceInRecall', { fig: index + 1 })}
            aria-label={t('chat.openEvidenceInRecall', { fig: index + 1 })}
          >
            <Maximize2 className="size-3.5" />
          </button>
        )}
      </div>
      <div
        className={`min-h-0 flex-1 overflow-hidden text-[13px] font-normal leading-5 text-text-primary ${
          chunk.image_id ? 'grid grid-cols-[112px_minmax(0,1fr)] gap-3' : ''
        }`}
      >
        {chunk.image_id ? (
          <EvidenceThumbnail imageId={chunk.image_id} fig={index + 1} />
        ) : null}
        <div className="min-w-0 overflow-hidden text-[13px] font-normal leading-5 text-text-primary [&_*]:!text-[13px] [&_*]:!font-normal [&_*]:!leading-5 [&_a]:!text-primary [&_blockquote]:!my-0 [&_h1]:!my-0 [&_h1]:!text-[13px] [&_h1]:!font-normal [&_h2]:!my-0 [&_h2]:!text-[13px] [&_h2]:!font-normal [&_h3]:!my-0 [&_h3]:!text-[13px] [&_h3]:!font-normal [&_h4]:!my-0 [&_h4]:!text-[13px] [&_h4]:!font-normal [&_li]:!my-0 [&_ol]:!my-0 [&_p]:!my-0 [&_strong]:!font-normal [&_ul]:!my-0 [&>*]:line-clamp-6">
          <EvidenceMarkdown content={chunk.content} />
        </div>
      </div>
    </article>
  );
}

function EvidenceDetailDialog({
  selection,
  onOpenChange,
}: {
  selection?: ReferenceEvidenceSelection;
  onOpenChange: (open: boolean) => void;
}) {
  if (!selection) return null;

  const { chunk, index } = selection;

  return (
    <Dialog open={Boolean(selection)} onOpenChange={onOpenChange}>
      <DialogContent className="grid h-[82vh] min-h-[520px] w-[92vw] max-w-[1180px] grid-rows-[auto_minmax(0,1fr)] gap-0 overflow-hidden p-0 dark:!border-[#7aa4ba]/38 dark:!bg-[#203747] dark:[&>button]:!text-[#dbeaf2] dark:[&>button]:!opacity-100 dark:[&>button]:hover:!bg-[#2a4658] dark:[&>button]:hover:!text-[#f2fbff] dark:[&>button]:focus-visible:!bg-[#2a4658] dark:[&>button]:focus-visible:!text-[#f2fbff] dark:[&>button_svg]:!stroke-[2.4]">
        <DialogHeader className="mx-0 mt-0 shrink-0 border-b border-border-default bg-white/90 px-5 py-3.5 dark:!border-[#7aa4ba]/32 dark:!bg-[#213b4c]">
          <DialogTitle className="flex min-w-0 items-center gap-3 pr-10 text-sm">
            <span className="shrink-0 rounded bg-[#f2f4f6] px-2 py-1 text-xs font-semibold text-[#364350] dark:!border dark:!border-[#8fb7ca]/34 dark:!bg-[#2a4658] dark:!text-[#f2fbff]">
              Fig. {index + 1}
            </span>
            <span className="min-w-0 flex-1 truncate text-xs font-medium text-text-secondary dark:!text-[#dbeaf2]">
              {chunk.document_name}
            </span>
            <CopyToClipboard
              text={chunk.content || ''}
              className="shrink-0 border-0 text-[#425867] hover:bg-[#e8eef2] hover:text-[#132330] dark:!text-[#dbeaf2] dark:hover:!bg-[#2a4658] dark:hover:!text-[#f2fbff] [&_svg]:!stroke-[2.2]"
              size="icon-sm"
            />
          </DialogTitle>
        </DialogHeader>

        <section
          className={
            chunk.image_id
              ? 'grid min-h-0 grid-cols-[minmax(320px,44%)_minmax(0,1fr)] bg-white dark:bg-[#203747]'
              : 'min-h-0 overflow-auto bg-white dark:bg-[#203747]'
          }
        >
          {chunk.image_id && (
            <div className="min-h-0 overflow-auto border-r border-border-default bg-[#f6f7f9] dark:border-[#9fd0ea]/16 dark:bg-[#dceef8]/7">
              <Image
                id={chunk.image_id}
                className="h-auto w-full max-h-none max-w-none object-contain object-left-top"
                alt={`Fig. ${(index + 1).toString()}`}
              />
            </div>
          )}
          <div className="min-h-0 overflow-auto bg-white dark:bg-[#dceef8]/5">
            <article
              className={`mx-auto min-h-full max-w-[720px] px-7 py-6 text-[14px] font-normal leading-7 text-text-primary dark:text-[#dcebf3] [&_*]:!font-normal [&_a]:!text-primary [&_blockquote]:my-3 [&_h1]:!my-2 [&_h1]:!text-[16px] [&_h1]:!leading-7 [&_h2]:!my-2 [&_h2]:!text-[16px] [&_h2]:!leading-7 [&_h3]:!my-2 [&_h3]:!text-[15px] [&_h3]:!leading-7 [&_li]:my-1 [&_ol]:my-2 [&_p]:my-2 [&_strong]:!font-normal [&_ul]:my-2 ${
                chunk.image_id ? '' : 'max-w-[820px]'
              }`}
            >
              <EvidenceMarkdown content={chunk.content} />
            </article>
          </div>
        </section>
      </DialogContent>
    </Dialog>
  );
}

export function ReferenceImageList({
  referenceChunks,
  messageContent,
}: IProps) {
  const [selectedEvidence, setSelectedEvidence] =
    useState<ReferenceEvidenceSelection>();
  const allChunkIndexes = extractNumbersFromMessageContent(messageContent);
  const citedChunkIndexes = useMemo(
    () => (allChunkIndexes.length > 0 ? new Set(allChunkIndexes) : undefined),
    [allChunkIndexes],
  );
  const evidenceItems = useMemo(() => {
    if (Array.isArray(referenceChunks)) {
      return referenceChunks
        .map((chunk, idx) => ({ chunk, index: idx }))
        .filter(
          (item) => !citedChunkIndexes || citedChunkIndexes.has(item.index),
        );
    }

    if (isPlainObject(referenceChunks)) {
      return Object.entries(referenceChunks || {}).reduce<EvidenceItem[]>(
        (pre, [idx, chunk]) => {
          const index = Number(idx);
          if (!citedChunkIndexes || citedChunkIndexes.has(index)) {
            return pre.concat({ chunk, index });
          }
          return pre;
        },
        [],
      );
    }

    return [];
  }, [citedChunkIndexes, referenceChunks]);
  if (evidenceItems.length === 0) {
    return <></>;
  }

  return (
    <section className="@container w-full space-y-3">
      <div className="grid gap-3 @md:grid-cols-2 @2xl:grid-cols-3">
        {evidenceItems.map((item) => (
          <EvidenceCard
            key={`${item.chunk.id}-${item.index}`}
            chunk={item.chunk}
            index={item.index}
            onOpenEvidence={setSelectedEvidence}
          />
        ))}
      </div>
      <EvidenceDetailDialog
        selection={selectedEvidence}
        onOpenChange={(open) => {
          if (!open) setSelectedEvidence(undefined);
        }}
      />
    </section>
  );
}
