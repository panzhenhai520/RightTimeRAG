import {
  useGetChunkHighlights,
  useGetDocumentUrl,
} from '@/hooks/use-document-request';
import { IModalProps } from '@/interfaces/common';
import { IReferenceChunk } from '@/interfaces/database/chat';
import { IChunk } from '@/interfaces/database/dataset';
import { cn } from '@/lib/utils';
import { Download, Printer, ZoomIn, ZoomOut } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import PdfPreview from '../document-preview/pdf-preview';
import { Button } from '../ui/button';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '../ui/sheet';

interface IProps extends IModalProps<any> {
  documentId: string;
  chunk: IChunk | IReferenceChunk;
  width?: string | number;
  height?: string | number;
}

export const PdfSheet = ({
  hideModal,
  documentId,
  chunk,
  width = '82vw',
  height,
}: IProps) => {
  const { t } = useTranslation();
  const [scale, setScale] = useState(1);
  const getDocumentUrl = useGetDocumentUrl(documentId);
  const url = getDocumentUrl(documentId);
  const { highlights, setWidthAndHeight } = useGetChunkHighlights(chunk);
  const chunkLike = chunk as Partial<IReferenceChunk & IChunk> & {
    docnm_kwd?: string;
    document_name?: string;
  };
  const fileName =
    chunkLike.document_name ||
    chunkLike.docnm_kwd ||
    t('search.untitledDocument');

  const handlePrint = () => {
    if (!url) return;
    const previewWindow = window.open(url, '_blank');
    previewWindow?.addEventListener?.('load', () => previewWindow.print(), {
      once: true,
    });
  };

  return (
    <Sheet open onOpenChange={hideModal}>
      <SheetContent
        className={cn(`max-w-full p-4`)}
        style={{
          width: width,
          height: height ? height : '100dvh',
        }}
      >
        <SheetHeader>
          <SheetTitle className="truncate pr-10">{fileName}</SheetTitle>
        </SheetHeader>
        <div className="mb-3 mt-2 flex items-center justify-between rounded-md border border-border bg-bg-card px-3 py-2">
          <div className="min-w-0 truncate text-xs text-text-secondary">
            {fileName}
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              title={t('common.zoomOut')}
              aria-label={t('common.zoomOut')}
              onClick={() => setScale((value) => Math.max(0.5, value - 0.15))}
            >
              <ZoomOut className="size-4" />
            </Button>
            <span className="w-12 text-center text-xs text-text-secondary">
              {Math.round(scale * 100)}%
            </span>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              title={t('common.zoomIn')}
              aria-label={t('common.zoomIn')}
              onClick={() => setScale((value) => Math.min(2.5, value + 0.15))}
            >
              <ZoomIn className="size-4" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              title={t('common.print')}
              aria-label={t('common.print')}
              disabled={!url}
              onClick={handlePrint}
            >
              <Printer className="size-4" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              asChild
              title={t('common.download')}
              aria-label={t('common.download')}
            >
              <a href={url} download={fileName}>
                <Download className="size-4" />
              </a>
            </Button>
          </div>
        </div>
        {url && documentId && (
          <PdfPreview
            className={'p-0 !h-[calc(100dvh-130px)] w-full'}
            highlights={highlights}
            setWidthAndHeight={setWidthAndHeight}
            pdfScaleValue={String(scale)}
            url={url}
          ></PdfPreview>
        )}
      </SheetContent>
    </Sheet>
  );
};

export default PdfSheet;
