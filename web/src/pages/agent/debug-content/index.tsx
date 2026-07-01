import MarkdownContent from '@/components/next-markdown-content';
import { SelectWithSearch } from '@/components/originui/select-with-search';
import { Button, ButtonLoading } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { IMessage } from '@/interfaces/database/chat';
import { cn } from '@/lib/utils';
import api from '@/utils/api';
import request from '@/utils/request';
import { zodResolver } from '@hookform/resolvers/zod';
import { ArrowUp, FileText, Folder, FolderOpen, RefreshCw } from 'lucide-react';
import React, {
  ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { BeginQueryType } from '../constant';
import { BeginQuery } from '../interface';
import { FileUploadDirectUpload } from './uploader';

const StringFields = [
  BeginQueryType.Line,
  BeginQueryType.Paragraph,
  BeginQueryType.Options,
];

type WorkspaceRoot = {
  root_id: string;
  path: string;
  name: string;
};

type WorkspaceFileEntry = {
  name: string;
  path: string;
  relative_path: string;
  root_id: string;
  type: 'directory' | 'file';
  size?: number;
  modified_at?: number;
};

function isWorkspacePathParameter(q: BeginQuery) {
  const text = `${q.key || ''} ${q.name || ''}`.toLowerCase();
  if (/workspace_root|root|根目录/.test(text)) {
    return false;
  }
  return /path|file|folder|directory|文件|目录|路径/.test(text);
}

function parentPath(path: string) {
  const normalized = (path || '.').replace(/\\/g, '/');
  if (!normalized || normalized === '.') {
    return '.';
  }
  const parts = normalized.split('/').filter(Boolean);
  parts.pop();
  return parts.length > 0 ? parts.join('/') : '.';
}

function formatBytes(value?: number) {
  const size = Number(value || 0);
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function WorkspacePathInput({
  agentId,
  field,
  label,
  parameter,
}: {
  agentId?: string;
  field: any;
  label: string;
  parameter: BeginQuery;
}) {
  const [open, setOpen] = useState(false);
  const [roots, setRoots] = useState<WorkspaceRoot[]>([]);
  const [selectedRoot, setSelectedRoot] = useState('');
  const [currentPath, setCurrentPath] = useState('.');
  const [files, setFiles] = useState<WorkspaceFileEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const canSelectDirectory = /folder|directory|目录|文件夹/.test(
    `${parameter.key || ''} ${parameter.name || ''}`.toLowerCase(),
  );

  const loadRoots = useCallback(async () => {
    const response = await request.get(
      `${api.workspaceRoots}${agentId ? `?agent_id=${encodeURIComponent(agentId)}` : ''}`,
    );
    const payload = await response.clone().json();
    const nextRoots: WorkspaceRoot[] = payload?.data?.roots ?? [];
    setRoots(nextRoots);
    if (!selectedRoot && nextRoots.length > 0) {
      setSelectedRoot(nextRoots[0].root_id || nextRoots[0].path);
    }
    return nextRoots;
  }, [agentId, selectedRoot]);

  const loadFiles = useCallback(async (path: string, root: string) => {
    if (!root) {
      return;
    }
    setLoading(true);
    setError('');
    try {
      const response = await request.post(api.workspaceFilesList, {
        data: {
          root,
          agent_id: agentId,
          path,
          recursive: false,
          include_dirs: true,
          max_results: 200,
        },
      });
      const payload = await response.clone().json();
      const nextFiles: WorkspaceFileEntry[] = payload?.data?.files ?? [];
      setFiles(
        nextFiles.sort((a, b) => {
          if (a.type !== b.type) {
            return a.type === 'directory' ? -1 : 1;
          }
          return a.name.localeCompare(b.name);
        }),
      );
    } catch (e: any) {
      setError(e?.message || '无法读取工作区文件列表');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) {
      return;
    }
    loadRoots().catch((e) => setError(e?.message || '无法读取工作区根目录'));
  }, [loadRoots, open]);

  useEffect(() => {
    if (!open || !selectedRoot) {
      return;
    }
    loadFiles(currentPath, selectedRoot);
  }, [currentPath, loadFiles, open, selectedRoot]);

  const handleDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      const text = event.dataTransfer.getData('text/plain').trim();
      const fileName = event.dataTransfer.files?.[0]?.name;
      field.onChange(text || fileName || field.value || '');
    },
    [field],
  );

  const selectPath = useCallback(
    (path: string) => {
      field.onChange(path);
      setOpen(false);
    },
    [field],
  );

  return (
    <div className="space-y-2">
      <div
        className="flex gap-2"
        onDragOver={(event) => event.preventDefault()}
        onDrop={handleDrop}
      >
        <Input
          {...field}
          value={field.value ?? ''}
          placeholder="选择工作区文件或粘贴路径"
        />
        <Button type="button" variant="outline" onClick={() => setOpen(true)}>
          <FolderOpen className="size-4" />
          浏览
        </Button>
      </div>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[82vh] max-w-3xl overflow-hidden">
          <DialogHeader>
            <DialogTitle>{label}</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <select
                className="h-9 min-w-52 rounded-md border border-border-default bg-white px-2 text-sm dark:bg-[#102636]"
                value={selectedRoot}
                onChange={(event) => {
                  setSelectedRoot(event.target.value);
                  setCurrentPath('.');
                }}
              >
                {roots.map((root) => (
                  <option
                    key={root.root_id || root.path}
                    value={root.root_id || root.path}
                  >
                    {root.name || root.path}
                  </option>
                ))}
              </select>
              <Button
                type="button"
                variant="outline"
                onClick={() => setCurrentPath(parentPath(currentPath))}
              >
                <ArrowUp className="size-4" />
                上一级
              </Button>
              {canSelectDirectory && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => selectPath(currentPath)}
                >
                  <Folder className="size-4" />
                  选择目录
                </Button>
              )}
              <Button
                type="button"
                variant="ghost"
                onClick={() => loadFiles(currentPath, selectedRoot)}
              >
                <RefreshCw className="size-4" />
              </Button>
            </div>
            <div className="rounded-md border border-border-default bg-muted/30 px-3 py-2 text-sm text-text-secondary">
              {currentPath === '.'
                ? '当前目录：/'
                : `当前目录：/${currentPath}`}
            </div>
            <div className="max-h-[48vh] overflow-auto rounded-md border border-border-default">
              {loading ? (
                <div className="px-3 py-8 text-center text-sm text-text-secondary">
                  Loading...
                </div>
              ) : error ? (
                <div className="px-3 py-8 text-center text-sm text-red-500">
                  {error}
                </div>
              ) : files.length === 0 ? (
                <div className="px-3 py-8 text-center text-sm text-text-secondary">
                  No files
                </div>
              ) : (
                files.map((file) => {
                  const Icon = file.type === 'directory' ? Folder : FileText;
                  return (
                    <button
                      className="flex w-full items-center gap-3 border-b border-border-default px-3 py-2 text-left text-sm hover:bg-muted/60 last:border-b-0"
                      draggable
                      key={`${file.root_id}:${file.relative_path}`}
                      type="button"
                      onClick={() => {
                        if (file.type === 'directory') {
                          setCurrentPath(file.relative_path || file.name);
                        } else {
                          selectPath(file.relative_path || file.name);
                        }
                      }}
                      onDragStart={(event) => {
                        event.dataTransfer.setData(
                          'text/plain',
                          file.relative_path || file.name,
                        );
                      }}
                    >
                      <Icon className="size-4 shrink-0 text-text-secondary" />
                      <span className="min-w-0 flex-1 truncate">
                        {file.name}
                      </span>
                      <span className="shrink-0 text-xs text-text-secondary">
                        {file.type === 'directory'
                          ? '目录'
                          : formatBytes(file.size)}
                      </span>
                    </button>
                  );
                })
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

interface IProps {
  parameters: BeginQuery[];
  message?: IMessage;
  ok(parameters: any[]): void;
  isNext?: boolean;
  loading?: boolean;
  submitButtonDisabled?: boolean;
  btnText?: ReactNode;
  className?: string;
  maxHeight?: string;
  agentId?: string;
}

const DebugContent = ({
  parameters,
  message,
  ok,
  isNext = true,
  loading = false,
  submitButtonDisabled = false,
  btnText,
  className,
  maxHeight,
  agentId,
}: IProps) => {
  const { t } = useTranslation();

  const formSchemaValues = useMemo(() => {
    const obj = parameters.reduce<{
      schema: Record<string, z.ZodType>;
      values: Record<string, any>;
    }>(
      (pre, cur, idx) => {
        const type = cur.type;
        let fieldSchema;
        let value;
        if (StringFields.some((x) => x === type)) {
          fieldSchema = z.string().trim().min(1);
        } else if (type === BeginQueryType.Boolean) {
          fieldSchema = z.boolean();
          value = false;
        } else if (type === BeginQueryType.Integer || type === 'float') {
          fieldSchema = z.coerce.number();
        } else if (type === BeginQueryType.File) {
          fieldSchema = z.array(z.record(z.any())).min(1);
        } else {
          fieldSchema = z.record(z.any());
        }

        if (cur.optional) {
          fieldSchema = fieldSchema.optional();
        }

        const index = idx.toString();

        pre.schema[index] = fieldSchema;
        pre.values[index] = value;

        return pre;
      },
      { schema: {}, values: {} },
    );

    return { schema: z.object(obj.schema), values: obj.values };
  }, [parameters]);

  const form = useForm<z.infer<typeof formSchemaValues.schema>>({
    defaultValues: formSchemaValues.values,
    resolver: zodResolver(formSchemaValues.schema),
  });

  const submittable = true;

  const renderWidget = useCallback(
    (q: BeginQuery, idx: string) => {
      const props = {
        key: idx,
        label: q.name ?? q.key,
        name: idx,
      };

      const BeginQueryTypeMap = {
        [BeginQueryType.Line]: (
          <FormField
            control={form.control}
            name={props.name}
            render={({ field }) => (
              <FormItem className="flex-1">
                <FormLabel>{props.label}</FormLabel>
                <FormControl>
                  {isWorkspacePathParameter(q) ? (
                    <WorkspacePathInput
                      agentId={agentId}
                      field={field}
                      label={props.label}
                      parameter={q}
                    />
                  ) : (
                    <Input {...field}></Input>
                  )}
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        ),
        [BeginQueryType.Paragraph]: (
          <FormField
            control={form.control}
            name={props.name}
            render={({ field }) => (
              <FormItem className="flex-1">
                <FormLabel>{props.label}</FormLabel>
                <FormControl>
                  <Textarea rows={1} {...field}></Textarea>
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        ),
        [BeginQueryType.Options]: (
          <FormField
            control={form.control}
            name={props.name}
            render={({ field }) => (
              <FormItem className="flex-1">
                <FormLabel>{props.label}</FormLabel>
                <FormControl>
                  <SelectWithSearch
                    allowClear
                    options={
                      q.options?.map((x) => ({
                        label: x,
                        value: x as string,
                      })) ?? []
                    }
                    {...field}
                  ></SelectWithSearch>
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        ),
        [BeginQueryType.File]: (
          <React.Fragment key={idx}>
            <FormField
              control={form.control}
              name={props.name}
              render={({ field }) => (
                <div className="space-y-6">
                  <FormItem className="w-full">
                    <FormLabel>{props.label}</FormLabel>
                    <FormControl>
                      <FileUploadDirectUpload
                        value={field.value}
                        onChange={field.onChange}
                      ></FileUploadDirectUpload>
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                </div>
              )}
            />
          </React.Fragment>
        ),
        [BeginQueryType.Integer]: (
          <FormField
            control={form.control}
            name={props.name}
            render={({ field }) => (
              <FormItem className="flex-1">
                <FormLabel>{props.label}</FormLabel>
                <FormControl>
                  <Input type="number" {...field}></Input>
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        ),
        [BeginQueryType.Boolean]: (
          <FormField
            control={form.control}
            name={props.name}
            render={({ field }) => (
              <FormItem className="flex-1">
                <FormLabel>{props.label}</FormLabel>
                <FormControl>
                  <Switch
                    checked={field.value}
                    onCheckedChange={field.onChange}
                  ></Switch>
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        ),
      };

      return (
        BeginQueryTypeMap[q.type as BeginQueryType] ??
        BeginQueryTypeMap[BeginQueryType.Paragraph]
      );
    },
    [form],
  );

  const onSubmit = useCallback(
    (values: z.infer<typeof formSchemaValues.schema>) => {
      const nextValues = Object.entries(values).map(([key, value]) => {
        const item = parameters[Number(key)];
        return { ...item, value };
      });

      ok(nextValues);
    },
    [formSchemaValues, ok, parameters],
  );
  return (
    <>
      <section className={className}>
        {message?.data?.tips && (
          <div className="mb-2">
            <MarkdownContent
              content={message?.data?.tips}
              loading={false}
            ></MarkdownContent>
          </div>
        )}
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)}>
            <section
              className={cn('overflow-auto px-2 space-y-4 pb-4', maxHeight)}
            >
              {parameters.map((x, idx) => {
                return <div key={idx}>{renderWidget(x, idx.toString())}</div>;
              })}
            </section>
            <div className="px-2">
              <ButtonLoading
                type="submit"
                loading={loading}
                disabled={!submittable || submitButtonDisabled}
                className="w-full mt-1"
              >
                {btnText || t(isNext ? 'common.next' : 'flow.run')}
              </ButtonLoading>
            </div>
          </form>
        </Form>
      </section>
    </>
  );
};

export default DebugContent;
