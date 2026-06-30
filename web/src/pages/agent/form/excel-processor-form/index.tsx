import { FormContainer } from '@/components/form-container';
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
import { initialExcelProcessorValues } from '../../constant';
import { useFormValues } from '../../hooks/use-form-values';
import { useWatchFormChange } from '../../hooks/use-watch-form-change';
import { INextOperatorForm } from '../../interface';
import { FormWrapper } from '../components/form-wrapper';
import { Output, transferOutputs } from '../components/output';

const operationOptions = [
  { label: 'Read', value: 'read' },
  { label: 'Aggregate', value: 'aggregate' },
  { label: 'Calculate', value: 'calculate' },
  { label: 'Merge', value: 'merge' },
  { label: 'Transform', value: 'transform' },
  { label: 'Output', value: 'output' },
  { label: 'Export', value: 'export' },
];

const sheetOptions = [
  { label: 'All sheets', value: 'all' },
  { label: 'First sheet', value: 'first' },
];

const outputFormatOptions = [
  { label: 'XLSX', value: 'xlsx' },
  { label: 'CSV', value: 'csv' },
];

const FormSchema = z.object({
  input_files: z.array(z.string()).default([]),
  operation: z.string(),
  sheet_selection: z.string().optional(),
  merge_strategy: z.string().optional(),
  join_on: z.string().optional(),
  transform_data: z.string().optional(),
  output_format: z.string().optional(),
  output_filename: z.string().optional(),
  aggregate_column_keywords: z.array(z.string()).or(z.string()).optional(),
  aggregate_coefficient: z.any().optional(),
  aggregate_result_name: z.string().optional(),
  calculation_value: z.any().optional(),
  calculation_coefficient: z.any().optional(),
  calculation_result_name: z.string().optional(),
  outputs: z.any().optional(),
});

function ExcelProcessorForm({ node }: INextOperatorForm) {
  const values = useFormValues(initialExcelProcessorValues, node);
  const form = useForm<z.infer<typeof FormSchema>>({
    defaultValues: values,
    resolver: zodResolver(FormSchema),
  });

  const inputFiles = useWatch({ control: form.control, name: 'input_files' });
  const operation = useWatch({ control: form.control, name: 'operation' });
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
          <FormField
            control={form.control}
            name="operation"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Operation</FormLabel>
                <FormControl>
                  <RAGFlowSelect
                    {...field}
                    options={operationOptions}
                  ></RAGFlowSelect>
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

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
            name="sheet_selection"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Sheet selection</FormLabel>
                <FormControl>
                  <RAGFlowSelect {...field} options={sheetOptions} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          {operation === 'aggregate' && (
            <>
              <FormField
                control={form.control}
                name="aggregate_column_keywords"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Aggregate column keywords</FormLabel>
                    <FormControl>
                      <Input
                        value={
                          Array.isArray(field.value)
                            ? field.value.join(',')
                            : field.value || ''
                        }
                        onChange={(e) => field.onChange(e.target.value)}
                        placeholder="合计,总计,金额合计,total,sum,amount"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="aggregate_coefficient"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Coefficient</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder="1 or begin@coefficient" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="aggregate_result_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Result name</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder="B" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </>
          )}

          {operation === 'calculate' && (
            <>
              <FormField
                control={form.control}
                name="calculation_value"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Value</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        placeholder="100 or ExcelProcessor:Aggregate@result"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="calculation_coefficient"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Coefficient</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder="1 or begin@coefficient" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="calculation_result_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Result name</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder="B" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </>
          )}

          {(operation === 'output' || operation === 'export') && (
            <>
              <FormField
                control={form.control}
                name="transform_data"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Data variable reference</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder="excel_processor@data" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="output_format"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Output format</FormLabel>
                    <FormControl>
                      <RAGFlowSelect {...field} options={outputFormatOptions} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="output_filename"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Output filename</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder="output" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </>
          )}

          <Output list={outputList}></Output>
        </FormContainer>
      </FormWrapper>
    </Form>
  );
}

export default memo(ExcelProcessorForm);
