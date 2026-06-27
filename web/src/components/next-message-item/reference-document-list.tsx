import { Card, CardContent } from '@/components/ui/card';
import { useSetModalState } from '@/hooks/common-hooks';
import { Docagg } from '@/interfaces/database/chat';
import { cn } from '@/lib/utils';
import PdfDrawer from '@/pages/next-search/document-preview-modal';
import { middleEllipsis } from '@/utils/common-util';
import { FileSearch } from 'lucide-react';
import { useState } from 'react';
import FileIcon from '../file-icon';

export function ReferenceDocumentList({
  list,
  dense = false,
}: {
  list: Docagg[];
  /** Stack cards full-width (one per row) so they never overflow a narrow
   * container such as the side recall panel. */
  dense?: boolean;
}) {
  const { visible, showModal, hideModal } = useSetModalState();
  const [selectedDocument, setSelectedDocument] = useState<Docagg>();
  return (
    <section
      className={
        dense ? 'mt-3 flex flex-col gap-2' : 'mt-3 flex flex-wrap gap-3'
      }
    >
      {list.map((item) => (
        <Card
          key={item.doc_id}
          className={cn(
            'border-[#d9c7cf] bg-white/80 transition-colors hover:border-[#cdaeb9] hover:bg-white dark:!border-[#7aa4ba]/36 dark:!bg-[#243d4e] dark:hover:!border-[#8fb7ca]/52 dark:hover:!bg-[#2a4658]',
            dense ? 'w-full' : '',
          )}
        >
          <CardContent
            className="flex cursor-pointer items-center gap-2 p-2"
            onClick={() => {
              setSelectedDocument(item);
              showModal();
            }}
          >
            <FileSearch className="size-4 shrink-0 text-[#5b2737] dark:!text-[#dbeaf2]" />
            <div
              className={cn(
                'truncate font-semibold text-[#5b2737] dark:!text-[#dbeaf2]',
                dense ? 'min-w-0 flex-1' : 'max-w-[260px]',
              )}
            >
              {middleEllipsis(item.doc_name)}
            </div>
            <FileIcon id={item.doc_id} name={item.doc_name}></FileIcon>
          </CardContent>
        </Card>
      ))}
      {visible && selectedDocument && (
        <PdfDrawer
          visible={visible}
          hideModal={hideModal}
          documentId={selectedDocument.doc_id}
          chunk={{
            document_name: selectedDocument.doc_name,
          }}
        ></PdfDrawer>
      )}
    </section>
  );
}
