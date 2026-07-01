import { FormContainer } from '@/components/form-container';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { zodResolver } from '@hookform/resolvers/zod';
import { memo, useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import {
  Operator,
  initialClauseMatcherValues,
  initialComplianceChecklistGeneratorValues,
  initialComplianceReportComposerValues,
  initialComplianceVerifierValues,
  initialContractClauseExtractorValues,
  initialRiskScorerValues,
} from '../../constant';
import { useFormValues } from '../../hooks/use-form-values';
import { useWatchFormChange } from '../../hooks/use-watch-form-change';
import { INextOperatorForm } from '../../interface';
import { FormWrapper } from '../components/form-wrapper';
import { Output, transferOutputs } from '../components/output';
import { PromptEditor } from '../components/prompt-editor';
import { QueryVariable } from '../components/query-variable';

const FormSchema = z.object({}).catchall(z.any());

const defaultsByOperator = {
  [Operator.ContractClauseExtractor]: initialContractClauseExtractorValues,
  [Operator.ComplianceChecklistGenerator]:
    initialComplianceChecklistGeneratorValues,
  [Operator.ClauseMatcher]: initialClauseMatcherValues,
  [Operator.ComplianceVerifier]: initialComplianceVerifierValues,
  [Operator.RiskScorer]: initialRiskScorerValues,
  [Operator.ComplianceReportComposer]: initialComplianceReportComposerValues,
};

const fieldsByOperator = {
  [Operator.ContractClauseExtractor]: [
    { name: 'chunks', label: 'Chunks' },
    { name: 'content', label: 'Content' },
    { name: 'references', label: 'References' },
    { name: 'min_clause_chars', label: 'Min clause chars', type: 'number' },
  ],
  [Operator.ComplianceChecklistGenerator]: [
    { name: 'standards', label: 'Standards' },
    { name: 'focus', label: 'Focus', type: 'text' },
    { name: 'max_items', label: 'Max items', type: 'number' },
  ],
  [Operator.ClauseMatcher]: [
    { name: 'checklist', label: 'Checklist' },
    { name: 'clauses', label: 'Clauses' },
    { name: 'min_confidence', label: 'Min confidence', type: 'number' },
  ],
  [Operator.ComplianceVerifier]: [
    { name: 'checklist', label: 'Checklist' },
    { name: 'matches', label: 'Matches' },
    { name: 'clauses', label: 'Clauses' },
    { name: 'min_confidence', label: 'Min confidence', type: 'number' },
  ],
  [Operator.RiskScorer]: [
    { name: 'verification_results', label: 'Verification results' },
  ],
  [Operator.ComplianceReportComposer]: [
    { name: 'title', label: 'Title', type: 'plain' },
    { name: 'scope', label: 'Scope', type: 'text' },
    { name: 'verification_results', label: 'Verification results' },
    { name: 'risk_summary', label: 'Risk summary' },
    { name: 'references', label: 'References' },
  ],
};

function ComplianceForm({ node }: INextOperatorForm) {
  const operatorName = node?.data.label as Operator;
  const initialValues =
    defaultsByOperator[operatorName as keyof typeof defaultsByOperator] ||
    initialComplianceReportComposerValues;
  const values = useFormValues(initialValues, node);
  const form = useForm<z.infer<typeof FormSchema>>({
    defaultValues: values,
    resolver: zodResolver(FormSchema),
  });
  const fields =
    fieldsByOperator[operatorName as keyof typeof fieldsByOperator] || [];
  const outputList = useMemo(() => transferOutputs(values.outputs), [values]);

  useWatchFormChange(node?.id, form);

  return (
    <Form {...form}>
      <FormWrapper>
        <FormContainer>
          {fields.map((field) => {
            if (field.type === 'number') {
              return (
                <FormField
                  key={field.name}
                  control={form.control}
                  name={field.name}
                  render={({ field: controlField }) => (
                    <FormItem>
                      <FormLabel>{field.label}</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          step={field.name === 'min_confidence' ? 0.01 : 1}
                          {...controlField}
                          onChange={(event) =>
                            controlField.onChange(Number(event.target.value))
                          }
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              );
            }

            if (field.type === 'text') {
              return (
                <FormField
                  key={field.name}
                  control={form.control}
                  name={field.name}
                  render={({ field: controlField }) => (
                    <FormItem>
                      <FormLabel>{field.label}</FormLabel>
                      <FormControl>
                        <PromptEditor
                          {...controlField}
                          showToolbar={false}
                        ></PromptEditor>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              );
            }

            if (field.type === 'plain') {
              return (
                <FormField
                  key={field.name}
                  control={form.control}
                  name={field.name}
                  render={({ field: controlField }) => (
                    <FormItem>
                      <FormLabel>{field.label}</FormLabel>
                      <FormControl>
                        <Input {...controlField} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              );
            }

            return (
              <QueryVariable
                key={field.name}
                label={<FormLabel>{field.label}</FormLabel>}
                name={field.name}
              ></QueryVariable>
            );
          })}
        </FormContainer>
      </FormWrapper>
      <div className="p-5">
        <Output list={outputList}></Output>
      </div>
    </Form>
  );
}

export default memo(ComplianceForm);
