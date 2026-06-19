import { Card, CardContent } from '@/components/ui/card';
import { useSetModalState } from '@/hooks/common-hooks';
import { Docagg } from '@/interfaces/database/chat';
import PdfDrawer from '@/pages/next-search/document-preview-modal';
import { middleEllipsis } from '@/utils/common-util';
import { FileSearch } from 'lucide-react';
import { useState } from 'react';
import FileIcon from '../file-icon';

export function ReferenceDocumentList({ list }: { list: Docagg[] }) {
  const { visible, showModal, hideModal } = useSetModalState();
  const [selectedDocument, setSelectedDocument] = useState<Docagg>();
  return (
    <section className="mt-3 flex flex-wrap gap-3">
      {list.map((item) => (
        <Card
          key={item.doc_id}
          className="border-[#d9c7cf] bg-white/80 dark:border-[#38546a] dark:bg-[#142637]/80"
        >
          <CardContent
            className="flex cursor-pointer items-center gap-2 p-2"
            onClick={() => {
              setSelectedDocument(item);
              showModal();
            }}
          >
            <FileSearch className="size-4 shrink-0 text-[#5b2737] dark:text-[#d7e7f0]" />
            <div className="max-w-[260px] truncate font-semibold text-[#5b2737] dark:text-[#d7e7f0]">
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
