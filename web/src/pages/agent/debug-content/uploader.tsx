'use client';

import {
  FileUpload,
  FileUploadDropzone,
  FileUploadItem,
  FileUploadItemDelete,
  FileUploadItemMetadata,
  FileUploadItemPreview,
  FileUploadItemProgress,
  FileUploadList,
  FileUploadTrigger,
  type FileUploadProps,
} from '@/components/file-upload';
import { Button } from '@/components/ui/button';
import { useUploadAgentFileWithProgress } from '@/hooks/use-agent-request';
import { Upload, X } from 'lucide-react';
import * as React from 'react';
import { toast } from 'sonner';

type FileUploadDirectUploadProps = {
  value: Record<string, any> | Record<string, any>[];
  onChange(value: Record<string, any>[]): void;
  maxFiles?: number;
};

export function FileUploadDirectUpload({
  value,
  onChange,
  maxFiles,
}: FileUploadDirectUploadProps) {
  const [files, setFiles] = React.useState<File[]>([]);
  const uploadedFilesRef = React.useRef<Record<string, any>[]>(
    Array.isArray(value) ? value : value ? [value] : [],
  );

  const { uploadAgentFile, loading } = useUploadAgentFileWithProgress();

  const onUpload: NonNullable<FileUploadProps['onUpload']> = React.useCallback(
    async (files, options) => {
      try {
        const ret = await uploadAgentFile({ files, options });
        if (ret?.code === 0) {
          const uploaded = Array.isArray(ret.data) ? ret.data : [ret.data];
          uploadedFilesRef.current = [
            ...uploadedFilesRef.current,
            ...uploaded.filter(Boolean),
          ];
          onChange(uploadedFilesRef.current);
        } else {
          const error = new Error(ret?.message || 'Upload failed');
          files.forEach((file) => options.onError(file, error));
        }
      } catch (error) {
        const nextError =
          error instanceof Error ? error : new Error('Upload failed');
        files.forEach((file) => options.onError(file, nextError));
      }
    },
    [onChange, uploadAgentFile],
  );

  const onFileReject = React.useCallback((file: File, message: string) => {
    toast(message, {
      description: `"${file.name.length > 20 ? `${file.name.slice(0, 20)}...` : file.name}" has been rejected`,
    });
  }, []);

  const handleFilesChange = React.useCallback(
    (newFiles: File[]) => {
      // Find removed files and update uploadedFilesRef
      const removedFiles = files.filter((f) => !newFiles.includes(f));
      if (removedFiles.length > 0) {
        const removedIndices = removedFiles.map((f) => files.indexOf(f));
        uploadedFilesRef.current = uploadedFilesRef.current.filter(
          (_, idx) => !removedIndices.includes(idx),
        );
        onChange(uploadedFilesRef.current);
      }
      setFiles(newFiles);
    },
    [files, onChange],
  );

  return (
    <FileUpload
      value={files}
      onValueChange={handleFilesChange}
      onUpload={onUpload}
      onFileReject={onFileReject}
      // TODO： DEFALUT to 5 / 1 for params
      maxFiles={(maxFiles ?? 5) as number}
      className="w-full"
      multiple={!maxFiles || !!(maxFiles && maxFiles > 1)}
      disabled={loading}
    >
      <FileUploadDropzone>
        <div className="flex flex-col items-center gap-1 text-center">
          <div className="flex items-center justify-center rounded-full border p-2.5">
            <Upload className="size-6 text-muted-foreground" />
          </div>
          <p className="font-medium text-sm">Drag & drop files here</p>
          <p className="text-muted-foreground text-xs">
            Or click to browse (max {(maxFiles ?? 5) as number} files)
          </p>
        </div>
        <FileUploadTrigger asChild>
          <Button variant="outline" size="sm" className="mt-2 w-fit">
            Browse files
          </Button>
        </FileUploadTrigger>
      </FileUploadDropzone>
      <FileUploadList>
        {files.map((file, index) => (
          <FileUploadItem key={index} value={file} className="flex-col">
            <div className="flex w-full items-center gap-2">
              <FileUploadItemPreview />
              <FileUploadItemMetadata />
              <FileUploadItemDelete asChild>
                <Button variant="ghost" size="icon" className="size-7">
                  <X />
                </Button>
              </FileUploadItemDelete>
            </div>
            <FileUploadItemProgress />
          </FileUploadItem>
        ))}
      </FileUploadList>
    </FileUpload>
  );
}
