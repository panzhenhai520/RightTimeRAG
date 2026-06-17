import Image from '@/components/image';
import {
  Carousel,
  CarouselContent,
  CarouselItem,
  CarouselNext,
  CarouselPrevious,
} from '@/components/ui/carousel';
import { MarkdownRemarkPlugins } from '@/constants/markdown-remark-plugins';
import { IReferenceChunk } from '@/interfaces/database/chat';
import { restAPIv1 } from '@/utils/api';
import { isPlainObject } from 'lodash';
import { RotateCw, ZoomIn, ZoomOut } from 'lucide-react';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import Markdown from 'react-markdown';
import { PhotoProvider, PhotoView } from 'react-photo-view';
import rehypeRaw from 'rehype-raw';
import { extractNumbersFromMessageContent } from './utils';

type IProps = {
  referenceChunks?: IReferenceChunk[] | Record<string, IReferenceChunk>;
  messageContent: string;
};

type ImageItem = {
  id: string;
  index: number;
};

type EvidenceItem = {
  chunk: IReferenceChunk;
  index: number;
};

const getButtonVisibilityClass = (imageCount: number) => {
  const map: Record<number, string> = {
    1: 'hidden',
    2: '@sm:hidden',
    3: '@md:hidden',
    4: '@lg:hidden',
    5: '@lg:hidden',
  };
  return map[imageCount] || (imageCount >= 6 ? '@2xl:hidden' : '');
};

function ImageCarousel({ images }: { images: ImageItem[] }) {
  const buttonVisibilityClass = getButtonVisibilityClass(images.length);

  return (
    <PhotoProvider
      // className="[&_.PhotoView-Slider__toolbarIcon]:hidden"
      toolbarRender={({ rotate, onRotate, scale, onScale }) => {
        return (
          <>
            <RotateCw
              className="mr-4 cursor-pointer text-text-disabled hover:text-text-primary"
              onClick={() => onRotate(rotate + 90)}
            />
            <ZoomIn
              className="mr-4 cursor-pointer text-text-disabled hover:text-text-primary"
              onClick={() => onScale(scale + 1)}
            />
            <ZoomOut
              className="cursor-pointer text-text-disabled hover:text-text-primary"
              onClick={() => onScale(scale - 1)}
            />
            {/* <X className="cursor-pointer text-text-disabled hover:text-text-primary" /> */}
          </>
        );
      }}
    >
      <Carousel
        className="w-full"
        opts={{
          align: 'start',
        }}
      >
        <CarouselContent>
          {images.map(({ id, index }) => (
            <CarouselItem
              key={index}
              className="
              basis-full
              @sm:basis-1/2
              @md:basis-1/3
              @lg:basis-1/4
              @2xl:basis-1/6
              "
            >
              <PhotoView src={`${restAPIv1}/documents/images/${id}`}>
                <Image
                  id={id}
                  className="h-40 w-full"
                  label={`Fig. ${(index + 1).toString()}`}
                />
              </PhotoView>
            </CarouselItem>
          ))}
        </CarouselContent>
        <CarouselPrevious className={buttonVisibilityClass} />
        <CarouselNext className={buttonVisibilityClass} />
      </Carousel>
    </PhotoProvider>
  );
}

function EvidenceMarkdown({ content }: { content?: string }) {
  if (!content) return null;
  return (
    <Markdown remarkPlugins={MarkdownRemarkPlugins} rehypePlugins={[rehypeRaw]}>
      {content}
    </Markdown>
  );
}

function EvidenceCard({ chunk, index }: EvidenceItem) {
  const { t } = useTranslation();
  const sourceChunks = chunk.source_chunks ?? [];

  return (
    <article className="min-h-40 rounded-md border border-border-default bg-bg-card p-3 text-sm text-text-primary">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="font-medium">Fig. {index + 1}</span>
        {chunk.is_raptor_summary && (
          <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800">
            {t('chat.summaryCitation')}
          </span>
        )}
        <span className="text-xs font-semibold text-[#5b2737] dark:text-[#d7e7f0]">
          {chunk.document_name}
        </span>
      </div>
      {chunk.image_id ? (
        <PhotoView src={`${restAPIv1}/documents/images/${chunk.image_id}`}>
          <Image
            id={chunk.image_id}
            className="mb-2 h-32 w-full"
            label={`Fig. ${(index + 1).toString()}`}
          />
        </PhotoView>
      ) : null}
      <div className="max-h-56 overflow-y-auto leading-6">
        <EvidenceMarkdown content={chunk.content} />
      </div>
      {chunk.is_raptor_summary && sourceChunks.length > 0 && (
        <section className="mt-3 space-y-2 border-t border-border-default pt-2">
          <div className="text-xs font-medium text-text-secondary">
            {t('chat.relatedOriginalChunks')}
          </div>
          {sourceChunks.map((source, sourceIndex) => (
            <div
              key={`${source.document_id}-${sourceIndex}`}
              className="rounded bg-bg-base p-2 text-xs leading-5"
            >
              <div className="mb-1 font-semibold text-[#5b2737] dark:text-[#d7e7f0]">
                {source.document_name || chunk.document_name}
                {source.page_num ? ` · p.${source.page_num}` : ''}
              </div>
              <EvidenceMarkdown content={source.content} />
            </div>
          ))}
        </section>
      )}
    </article>
  );
}

export function ReferenceImageList({
  referenceChunks,
  messageContent,
}: IProps) {
  const allChunkIndexes = extractNumbersFromMessageContent(messageContent);
  const evidenceItems = useMemo(() => {
    if (Array.isArray(referenceChunks)) {
      return referenceChunks
        .map((chunk, idx) => ({ chunk, index: idx }))
        .filter((item) => allChunkIndexes.includes(item.index));
    }

    if (isPlainObject(referenceChunks)) {
      return Object.entries(referenceChunks || {}).reduce<EvidenceItem[]>(
        (pre, [idx, chunk]) => {
          const index = Number(idx);
          if (allChunkIndexes.includes(index)) {
            return pre.concat({ chunk, index });
          }
          return pre;
        },
        [],
      );
    }

    return [];
  }, [allChunkIndexes, referenceChunks]);
  const images = useMemo(() => {
    if (Array.isArray(referenceChunks)) {
      return referenceChunks
        .map((chunk, idx) => ({ id: chunk.image_id, index: idx }))
        .filter((item, idx) => allChunkIndexes.includes(idx) && item.id);
    }

    if (isPlainObject(referenceChunks)) {
      return Object.entries(referenceChunks || {}).reduce<ImageItem[]>(
        (pre, [idx, chunk]) => {
          if (allChunkIndexes.includes(Number(idx)) && chunk.image_id) {
            return pre.concat({ id: chunk.image_id, index: Number(idx) });
          }
          return pre;
        },
        [],
      );
    }

    return [];
  }, [allChunkIndexes, referenceChunks]);

  const imageCount = images?.length || 0;

  if (evidenceItems.length === 0) {
    return <></>;
  }

  return (
    <section className="@container w-full space-y-3">
      {imageCount > 0 && <ImageCarousel images={images} />}
      <div className="grid gap-3 @md:grid-cols-2 @2xl:grid-cols-3">
        {evidenceItems.map((item) => (
          <EvidenceCard
            key={`${item.chunk.id}-${item.index}`}
            chunk={item.chunk}
            index={item.index}
          />
        ))}
      </div>
    </section>
  );
}
