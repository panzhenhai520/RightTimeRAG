import { FormContainer } from '@/components/form-container';
import NumberInput from '@/components/originui/number-input';
import { Button } from '@/components/ui/button';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { RAGFlowSelect } from '@/components/ui/select';
import { zodResolver } from '@hookform/resolvers/zod';
import { Plus, Trash2 } from 'lucide-react';
import { memo, useMemo } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { z } from 'zod';
import { initialFileParserValues } from '../../constant';
import { useFormValues } from '../../hooks/use-form-values';
import { useWatchFormChange } from '../../hooks/use-watch-form-change';
import { INextOperatorForm } from '../../interface';
import { FormWrapper } from '../components/form-wrapper';
import { Output, transferOutputs } from '../components/output';

const parserOptions = [
  { label: 'Auto', value: 'auto' },
  { label: 'Naive', value: 'naive' },
  { label: 'Laws', value: 'laws' },
  { label: 'Paper', value: 'paper' },
  { label: 'Book', value: 'book' },
  { label: 'Manual', value: 'manual' },
  { label: 'One', value: 'one' },
];

const FormSchema = z.object({
  input_files: z.array(z.string()).default([]),
  query: z.string().optional(),
  parser_id: z.string().optional(),
  layout_recognize: z.string().optional(),
  chunk_token_num: z.coerce.number().min(100),
  from_page: z.coerce.number().min(0),
  to_page: z.coerce.number().min(1),
  top_n: z.coerce.number().min(1),
  context_window: z.coerce.number().min(0).max(5),
  max_content_chars: z.coerce.number().min(1000),
  outputs: z.any().optional(),
});

function FileParserForm({ node }: INextOperatorForm) {
  const values = useFormValues(initialFileParserValues, node);
  const form = useForm<z.infer<typeof FormSchema>>({
    defaultValues: values,
    resolver: zodResolver(FormSchema),
  });

  const inputFiles = useWatch({ control: form.control, name: 'input_files' });
  const formOutputs = useWatch({ control: form.control, name: 'outputs' });
  const outputList = useMemo(
    () => transferOutputs(formOutputs ?? values.outputs),
    [formOutputs, values.outputs],
  );

  useWatchFormChange(node?.id, form);

  return (
    <Form {...form}>
      <FormWrapper>
        <FormContainer>
          <FormItem>
            <FormLabel>Input file variable references</FormLabel>
            <div className="space-y-2">
              {(inputFiles || []).map((value, index) => (
                <div
                  key={`${index}-${value}`}
                  className="flex items-center gap-2"
                >
                  <FormField
                    control={form.control}
                    name={`input_files.${index}`}
                    render={({ field }) => (
                      <FormControl>
                        <Input
                          {...field}
                          placeholder="sys.file_assets or begin@file_files"
                        />
                      </FormControl>
                    )}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() =>
                      form.setValue(
                        'input_files',
                        (inputFiles || []).filter((_, i) => i !== index),
                      )
                    }
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() =>
                  form.setValue('input_files', [
                    ...(inputFiles || []),
                    'sys.file_assets',
                  ])
                }
              >
                <Plus className="mr-2 h-4 w-4" />
                Add file reference
              </Button>
            </div>
          </FormItem>

          <FormField
            control={form.control}
            name="query"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Query</FormLabel>
                <FormControl>
                  <Input {...field} placeholder="{sys.query}" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="parser_id"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Parser</FormLabel>
                <FormControl>
                  <RAGFlowSelect {...field} options={parserOptions} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="layout_recognize"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Layout recognize</FormLabel>
                <FormControl>
                  <Input {...field} placeholder="Plain Text" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <div className="grid grid-cols-2 gap-3">
            <FormField
              control={form.control}
              name="chunk_token_num"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Chunk tokens</FormLabel>
                  <FormControl>
                    <NumberInput {...field} className="w-full" />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="top_n"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Top N</FormLabel>
                  <FormControl>
                    <NumberInput {...field} className="w-full" />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="context_window"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Context window</FormLabel>
                  <FormControl>
                    <NumberInput {...field} className="w-full" />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="from_page"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>From page</FormLabel>
                  <FormControl>
                    <NumberInput {...field} className="w-full" />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="to_page"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>To page</FormLabel>
                  <FormControl>
                    <NumberInput {...field} className="w-full" />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>

          <FormField
            control={form.control}
            name="max_content_chars"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Max content chars</FormLabel>
                <FormControl>
                  <NumberInput {...field} className="w-full" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <Output list={outputList}></Output>
        </FormContainer>
      </FormWrapper>
    </Form>
  );
}

export default memo(FileParserForm);
