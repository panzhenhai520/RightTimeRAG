import { EmptyType } from '@/components/empty/constant';
import Empty from '@/components/empty/empty';
import HighLightMarkdown from '@/components/highlight-markdown';
import { FileIcon } from '@/components/icon-font';
import { ImageWithPopover } from '@/components/image';
import { Input } from '@/components/originui/input';
import { SkeletonCard } from '@/components/skeleton-card';
import { Button } from '@/components/ui/button';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { RAGFlowPagination } from '@/components/ui/ragflow-pagination';
import { IReference } from '@/interfaces/database/chat';
import { ITestingChunk } from '@/interfaces/database/dataset';
import { cn } from '@/lib/utils';
import { isEmpty } from 'lodash';
import { Loader2, ListTree, Search, X } from 'lucide-react';
import {
  Dispatch,
  SetStateAction,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { ISearchAppDetailProps } from '../next-searches/hooks';
import PdfDrawer from './document-preview-modal';
import ExpandableContent from './expandable-content';
import { ISearchReturnProps } from './hooks';
import './index.less';
import MarkdownContent from './markdown-content';
import MindMapSheet from './mindmap-sheet';
import RetrievalDocuments from './retrieval-documents';

const formatMetadataValue = (value: unknown) => {
  if (Array.isArray(value)) return value.join(', ');
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

const stripMarkup = (value = '') =>
  value
    .replace(/<[^>]*>/g, ' ')
    .replace(/[#>*_`~\[\]()]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

const escapeRegExp = (value: string) =>
  value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const getSearchTerms = (query: string) => {
  const terms = query.match(/[\p{L}\p{N}_-]+/gu) ?? [];
  return Array.from(new Set(terms.map((term) => term.trim()).filter((term) => term.length >= 2))).slice(0, 8);
};

const countTermHits = (content: string, terms: string[]) =>
  terms.reduce((count, term) => {
    const matched = content.match(new RegExp(escapeRegExp(term), 'giu'));
    return count + (matched?.length ?? 0);
  }, 0);

const highlightSearchTerms = (content: string, terms: string[]) => {
  if (!content || terms.length === 0) return content;
  return terms.reduce(
    (current, term) =>
      current.replace(
        new RegExp(escapeRegExp(term), 'giu'),
        (matched) => `<mark class="search-keyword-mark">${matched}</mark>`,
      ),
    content,
  );
};

const buildDocumentCards = (chunks: ITestingChunk[] = [], query: string) => {
  const terms = getSearchTerms(query);
  const groups = new Map<
    string,
    {
      docId: string;
      docName: string;
      chunks: ITestingChunk[];
      metadata?: Record<string, unknown>;
    }
  >();

  chunks.forEach((chunk, index) => {
    const docId = chunk.doc_id || `${chunk.docnm_kwd || 'document'}-${index}`;
    const current = groups.get(docId);
    const metadata = (chunk as any).document_metadata;
    if (current) {
      current.chunks.push(chunk);
      if (!current.metadata && metadata) current.metadata = metadata;
      return;
    }
    groups.set(docId, {
      docId,
      docName: chunk.docnm_kwd || chunk.doc_name || '',
      chunks: [chunk],
      metadata,
    });
  });

  return Array.from(groups.values()).map((group) => {
    const ranked = group.chunks
      .map((chunk, index) => {
        const content = chunk.highlight || chunk.content_with_weight || '';
        const plain = stripMarkup(content);
        return {
          chunk,
          content,
          plainLength: plain.length,
          score:
            countTermHits(plain, terms) * 100 +
            (chunk.similarity ?? 0) * 10 -
            index,
        };
      })
      .sort((a, b) => b.score - a.score);
    const substantial = ranked.filter((item) => item.plainLength >= 40);
    const snippets = (substantial.length > 0 ? substantial : ranked).slice(0, 3);
    const representative = snippets[0]?.chunk ?? group.chunks[0];
    const imageChunk =
      group.chunks.find((chunk) => chunk.image_id || chunk.img_id) ??
      representative;

    return {
      ...group,
      representative,
      imageChunk,
      snippets,
      terms,
    };
  });
};

export default function SearchingView({
  searchData,
  handleClickRelatedQuestion,
  handleTestChunk,
  setSelectedDocumentIds,
  answer,
  sendingLoading,
  loading,
  relatedQuestions,
  isFirstRender,
  selectedDocumentIds,
  isSearchStrEmpty,
  searchStr,
  stopOutputMessage,
  visible,
  hideModal,
  documentId,
  selectedChunk,
  clickDocumentButton,
  mindMapVisible,
  hideMindMapModal,
  showMindMapModal,
  mindMapLoading,
  mindMap,
  chunks,
  total,
  handleSearch,
  pagination,
  onChange,
}: ISearchReturnProps & {
  setIsSearching?: Dispatch<SetStateAction<boolean>>;
  searchData: ISearchAppDetailProps;
  showEmbedLogo?: boolean;
}) {
  const { t } = useTranslation();

  const [searchText, setSearchText] = useState<string>('');
  const [retrievalLoading, setRetrievalLoading] = useState(false);

  useEffect(() => {
    setSearchText(searchStr);
  }, [searchStr, setSearchText]);

  const documentCards = useMemo(
    () => buildDocumentCards(chunks, searchStr),
    [chunks, searchStr],
  );
  const showResultSkeleton =
    !isSearchStrEmpty &&
    documentCards.length === 0 &&
    (loading || retrievalLoading || sendingLoading);

  return (
    <section
      className={cn(
        'relative flex h-full w-full items-center justify-center transition-all',
      )}
    >
      {/* search header */}
      <div
        className={cn(
          'relative z-10 flex h-full w-full justify-center px-6 pt-8 text-text-primary',
        )}
      >
        <div
          className={cn(
            'sticky flex h-full w-full transform flex-col justify-center rounded-lg text-xl text-primary',
          )}
        >
          <div className={cn('flex flex-col justify-start items-start w-full')}>
            <div className="relative w-full text-primary">
              <Input
                placeholder={t('search.searchGreeting')}
                className={cn(
                  'w-full rounded-full border-border-default/70 bg-bg-base py-6 pl-5 !pr-[8rem] text-lg text-primary shadow-sm',
                )}
                value={searchText}
                onChange={(e) => {
                  setSearchText(e.target.value);
                }}
                disabled={sendingLoading}
                onKeyUp={(e) => {
                  if (e.key === 'Enter') {
                    handleSearch(searchText);
                  }
                }}
              />
              <div className="absolute right-2 top-1/2 -translate-y-1/2 transform flex items-center gap-1">
                <X
                  className="text-text-secondary cursor-pointer opacity-80"
                  size={14}
                  onClick={() => {
                    setSearchText('');
                    handleClickRelatedQuestion('');
                  }}
                />
                <span className="text-text-secondary opacity-20 ml-4">|</span>
                <button
                  type="button"
                  className="ml-4 h-8 w-12 rounded-full bg-accent-primary p-1 text-white shadow hover:opacity-90"
                  onClick={() => {
                    if (sendingLoading) {
                      stopOutputMessage();
                    } else {
                      handleSearch(searchText);
                    }
                  }}
                >
                  {sendingLoading ? (
                    <Loader2 size={20} className="m-auto animate-spin" />
                  ) : (
                    <Search size={22} className="m-auto" />
                  )}
                </button>
              </div>
            </div>
          </div>
          {/* search body */}
          <div
            className="mt-5 w-full overflow-auto scrollbar-thin"
            style={{ height: 'calc(100vh - 250px)' }}
          >
            {searchData.search_config.summary && !isSearchStrEmpty && (
              <>
                <div className="flex justify-start items-start text-text-primary text-2xl">
                  {t('search.AISummary')}
                </div>
                {isEmpty(answer) && sendingLoading ? (
                  <SkeletonCard className=" mt-2" />
                ) : (
                  answer.answer && (
                    <div className="mt-3 rounded-xl bg-bg-base/60 p-4 shadow-sm">
                      <ExpandableContent maxHeight={208}>
                        <MarkdownContent
                          loading={sendingLoading}
                          content={answer.answer}
                          reference={answer.reference ?? ({} as IReference)}
                          clickDocumentButton={clickDocumentButton}
                        />
                      </ExpandableContent>
                    </div>
                  )
                )}
                {answer.answer && !sendingLoading && (
                  <div className="my-6"></div>
                )}
              </>
            )}
            {/* retrieval documents */}
            {!isSearchStrEmpty && !sendingLoading && (
              <>
                <div className="mt-3 w-full">
                  <RetrievalDocuments
                    selectedDocumentIds={selectedDocumentIds}
                    setSelectedDocumentIds={setSelectedDocumentIds}
                    onTesting={handleTestChunk}
                    setLoading={(loading: boolean) => {
                      setRetrievalLoading(loading);
                    }}
                  ></RetrievalDocuments>
                </div>
                {/* <div className="w-full border-b border-border-default/80 my-6"></div> */}
              </>
            )}
            <div className="mt-4">
              {showResultSkeleton && (
                <div className="grid w-full grid-cols-[repeat(auto-fit,minmax(340px,1fr))] gap-4">
                  {Array.from({ length: 6 }).map((_, index) => (
                    <article
                      key={index}
                      className="flex h-[360px] flex-col overflow-hidden rounded-xl bg-bg-base/90 p-5 shadow-sm ring-1 ring-accent-primary/10 dark:bg-bg-component/70"
                    >
                      <div className="mb-4 h-5 w-2/3 animate-pulse rounded-md bg-[rgb(var(--accent-primary)/0.18)]" />
                      <div className="space-y-3">
                        <div className="h-20 animate-pulse rounded-lg bg-[rgb(var(--accent-primary)/0.12)]" />
                        <div className="h-20 animate-pulse rounded-lg bg-[rgb(var(--accent-primary)/0.10)]" />
                        <div className="h-20 animate-pulse rounded-lg bg-[rgb(var(--accent-primary)/0.08)]" />
                      </div>
                      <div className="mt-auto h-8 w-1/2 animate-pulse rounded-lg bg-[rgb(var(--accent-primary)/0.12)]" />
                    </article>
                  ))}
                </div>
              )}
              {documentCards.length > 0 && (
                <div className="grid w-full grid-cols-[repeat(auto-fit,minmax(340px,1fr))] gap-4">
                  {documentCards.map((card) => {
                    return (
                      <article
                        key={card.docId}
                        className="flex h-[360px] cursor-pointer flex-col overflow-hidden rounded-xl bg-bg-base/90 p-5 shadow-sm ring-1 ring-border-default/25 transition-shadow hover:shadow-md dark:bg-bg-component/70"
                        onClick={() =>
                          clickDocumentButton(
                            card.representative.doc_id,
                            card.representative as any,
                          )
                        }
                        tabIndex={0}
                      >
                        <div className="min-h-0 flex-1 overflow-hidden text-sm leading-6 text-text-primary">
                          {(card.imageChunk.image_id || card.imageChunk.img_id) && (
                            <div
                              className="float-left mb-3 mr-4 max-w-[42%] overflow-hidden rounded-lg bg-bg-card/50 p-1 [&_button]:block [&_img]:!max-h-32 [&_img]:!max-w-full [&_img]:rounded-md [&_img]:object-contain"
                              onClick={(event) => event.stopPropagation()}
                            >
                              <ImageWithPopover
                                id={
                                  card.imageChunk.image_id ||
                                  card.imageChunk.img_id
                                }
                              ></ImageWithPopover>
                            </div>
                          )}
                          <div className="space-y-3">
                            {card.snippets.map((snippet, snippetIndex) => (
                              <div
                                key={snippet.chunk.chunk_id || snippetIndex}
                                className={cn(
                                  'rounded-lg px-3 py-2',
                                  snippetIndex === 0
                                    ? 'bg-accent-primary/5'
                                    : 'bg-bg-card/35',
                                )}
                              >
                                <div className="mb-1 text-xs font-medium text-accent-primary">
                                  #{snippetIndex + 1}
                                </div>
                                <HighLightMarkdown>
                                  {highlightSearchTerms(
                                    snippet.content,
                                    card.terms,
                                  )}
                                </HighLightMarkdown>
                              </div>
                            ))}
                          </div>
                        </div>

                        <div className="clear-both mt-4 pt-3">
                          {card.metadata &&
                            Object.keys(card.metadata).length > 0 && (
                              <div className="mb-3 flex flex-wrap gap-2">
                                {Object.entries(card.metadata).map(
                                  ([key, value]) => (
                                    <div
                                      key={key}
                                      className="rounded-full bg-bg-card/60 px-2.5 py-1 text-xs"
                                    >
                                      <span className="text-text-secondary">
                                        {key}:
                                      </span>{' '}
                                      <span className="text-text-primary">
                                        {formatMetadataValue(value)}
                                      </span>
                                    </div>
                                  ),
                                )}
                              </div>
                            )}
                          <button
                            type="button"
                            className="flex max-w-full items-center gap-2 rounded-lg bg-bg-card/50 px-2.5 py-1.5 text-left text-xs text-text-secondary transition hover:bg-bg-card hover:text-text-primary"
                            onClick={(event) => {
                              event.stopPropagation();
                              clickDocumentButton(
                                card.representative.doc_id,
                                card.representative as any,
                              );
                            }}
                          >
                            <FileIcon name={card.docName}></FileIcon>
                            <span className="truncate">{card.docName}</span>
                            {card.chunks.length > 1 && (
                              <span className="ml-1 rounded-full bg-accent-primary/10 px-2 py-0.5 text-accent-primary">
                                {card.chunks.length}
                              </span>
                            )}
                          </button>
                        </div>
                      </article>
                    );
                  })}
                </div>
              )}
              {relatedQuestions?.length > 0 &&
                searchData.search_config.related_search && (
                  <>
                    <div className="mt-6 w-full overflow-hidden opacity-100 max-h-96">
                      <p className="text-text-primary mb-2 text-xl">
                        {t('search.relatedSearch')}
                      </p>
                      <div className="mt-2 flex flex-wrap justify-start gap-2">
                        {relatedQuestions?.map((x, idx) => (
                          <Button
                            key={idx}
                            variant="transparent"
                            className="bg-bg-card text-text-secondary"
                            onClick={handleClickRelatedQuestion(
                              x,
                              searchData.search_config.summary,
                            )}
                          >
                            {x}
                          </Button>
                        ))}
                      </div>
                    </div>
                  </>
                )}
            </div>
            {!isSearchStrEmpty &&
              !retrievalLoading &&
              !answer.answer &&
              !sendingLoading &&
              total <= 0 &&
              chunks?.length <= 0 &&
              relatedQuestions?.length <= 0 && (
                <div className="h-2/5 flex items-center justify-center">
                  <Empty type={EmptyType.SearchData} iconWidth={80} />
                </div>
              )}
          </div>

          {total > 0 && (
            <div className="mt-8 px-8 pb-8 text-base">
              <RAGFlowPagination
                current={pagination.current}
                pageSize={pagination.pageSize}
                total={total}
                onChange={onChange}
              ></RAGFlowPagination>
            </div>
          )}

          {!mindMapVisible &&
            !isFirstRender &&
            !isSearchStrEmpty &&
            !isEmpty(searchData.search_config.kb_ids) &&
            searchData.search_config.query_mindmap && (
              <Popover>
                <PopoverTrigger asChild>
                  <Button
                    onClick={showMindMapModal}
                    variant={'outline'}
                    className="absolute top-16 translate-y-2 right-10 z-30 rounded-full size-6"
                  >
                    <ListTree />
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-fit">
                  {t('chunk.mind')}
                </PopoverContent>
              </Popover>
            )}
        </div>
        {mindMapVisible && (
          <div className="flex-1 h-[88dvh] z-30 ml-32 mt-5">
            <MindMapSheet
              visible={mindMapVisible}
              hideModal={hideMindMapModal}
              data={mindMap}
              loading={mindMapLoading}
            ></MindMapSheet>
          </div>
        )}
      </div>

      {visible && (
        <PdfDrawer
          visible={visible}
          hideModal={hideModal}
          documentId={documentId}
          chunk={selectedChunk}
        ></PdfDrawer>
      )}
    </section>
  );
}
