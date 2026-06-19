import DocumentPreview from '@/components/document-preview';
import { FileIcon } from '@/components/icon-font';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/ui/modal/modal';
import {
  useGetChunkHighlights,
  useGetDocumentUrl,
} from '@/hooks/use-document-request';
import { IModalProps } from '@/interfaces/common';
import { IReferenceChunk } from '@/interfaces/database/chat';
import { IChunk } from '@/interfaces/database/dataset';
import { cn } from '@/lib/utils';
import { Download, Printer, ZoomIn, ZoomOut } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

interface IProps extends IModalProps<any> {
  documentId: string;
  chunk: Partial<IChunk & IReferenceChunk> & {
    docnm_kwd?: string;
    document_name?: string;
  };
}
function getFileExtensionRegex(filename: string): string {
  const match = filename.match(/\.([^.]+)$/);
  return match ? match[1].toLowerCase() : '';
}
const PdfDrawer = ({
  visible = false,
  hideModal,
  documentId,
  chunk,
}: IProps) => {
  const { t } = useTranslation();
  const fileName =
    chunk.docnm_kwd || chunk.document_name || t('search.untitledDocument');
  const getDocumentUrl = useGetDocumentUrl(documentId);
  const { highlights, setWidthAndHeight } = useGetChunkHighlights(
    chunk as IChunk | IReferenceChunk,
  );
  // const ref = useRef<(highlight: IHighlight) => void>(() => {});
  // const [loaded, setLoaded] = useState(false);
  const url = getDocumentUrl();

  const [fileType, setFileType] = useState('');
  const [scale, setScale] = useState(1);

  useEffect(() => {
    if (fileName) {
      const type = getFileExtensionRegex(fileName);
      setFileType(type);
    }
  }, [fileName]);

  const isPdf = fileType === 'pdf';
  const pdfScaleValue = isPdf ? String(scale) : undefined;

  const handlePrint = () => {
    if (!url) return;
    const previewWindow = window.open(url, '_blank');
    previewWindow?.addEventListener?.('load', () => previewWindow.print(), {
      once: true,
    });
  };

  return (
    <Modal
      title={
        <div className="flex min-w-0 items-center gap-2 pr-10">
          <FileIcon name={fileName}></FileIcon>
          <span className="truncate">{fileName}</span>
        </div>
      }
      onCancel={hideModal}
      open={visible}
      showfooter={false}
      className="!w-[92vw] !max-w-[92vw] !max-h-[92dvh]"
      bodyClassName="!max-h-[calc(92dvh-82px)] !overflow-hidden !px-5 !pb-5"
      style={{ width: '92vw', maxWidth: '92vw' }}
    >
      <div className="flex h-[calc(92dvh-132px)] min-h-[560px] flex-col gap-3">
        <div className="flex items-center justify-between rounded-md border border-border bg-bg-card px-3 py-2">
          <div className="min-w-0 truncate text-xs text-text-secondary">
            {fileName}
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              disabled={!isPdf}
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
              disabled={!isPdf}
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
        <DocumentPreview
          className={cn(
            '!h-full overflow-auto border-none padding-0 max-h-full',
          )}
          fileType={fileType}
          highlights={highlights}
          setWidthAndHeight={setWidthAndHeight}
          pdfScaleValue={pdfScaleValue}
          url={url}
        ></DocumentPreview>
      </div>
    </Modal>
  );
};

export default PdfDrawer;
