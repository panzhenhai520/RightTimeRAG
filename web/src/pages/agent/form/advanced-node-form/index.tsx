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
import { Switch } from '@/components/ui/switch';
import { zodResolver } from '@hookform/resolvers/zod';
import { memo, useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import {
  Operator,
  initialASRTranscribeValues,
  initialAgentFanoutValues,
  initialArtifactPackagerValues,
  initialAudioInputValues,
  initialChartRendererValues,
  initialChartSpecBuilderValues,
  initialExternalScoreReceiverValues,
  initialHumanReviewValues,
  initialManualApproveValues,
  initialMeetingContextInputValues,
  initialMemoryInjectValues,
  initialNumberCalculateValues,
  initialPromptTemplateValues,
  initialPronunciationJudgeValues,
  initialReportComposerValues,
  initialResultAggregatorValues,
  initialSafeRecordInsertValues,
  initialSafeRecordQueryValues,
  initialSafeRecordUpdateValues,
  initialSafeTableEnsureValues,
  initialScopedDBConnectorValues,
  initialScoreRubricBuilderValues,
  initialSummaryNodeValues,
  initialTTSGenerateValues,
  initialVoiceReplyOutputValues,
  initialWebhookInputValues,
  initialWorkspaceFileWriteValues,
  initialWorkspacePatchApplyValues,
} from '../../constant';
import { useFormValues } from '../../hooks/use-form-values';
import { useWatchFormChange } from '../../hooks/use-watch-form-change';
import { INextOperatorForm } from '../../interface';
import { FormWrapper } from '../components/form-wrapper';
import { Output, transferOutputs } from '../components/output';
import { PromptEditor } from '../components/prompt-editor';

const FormSchema = z.object({}).catchall(z.any());

type FieldKind = 'line' | 'textarea' | 'number' | 'boolean';
type AdvancedField = { name: string; label: string; kind?: FieldKind };

const defaultsByOperator = {
  [Operator.PromptTemplate]: initialPromptTemplateValues,
  [Operator.ScoreRubricBuilder]: initialScoreRubricBuilderValues,
  [Operator.PronunciationJudge]: initialPronunciationJudgeValues,
  [Operator.SummaryNode]: initialSummaryNodeValues,
  [Operator.ReportComposer]: initialReportComposerValues,
  [Operator.AudioInput]: initialAudioInputValues,
  [Operator.TTSGenerate]: initialTTSGenerateValues,
  [Operator.ASRTranscribe]: initialASRTranscribeValues,
  [Operator.VoiceReplyOutput]: initialVoiceReplyOutputValues,
  [Operator.MeetingContextInput]: initialMeetingContextInputValues,
  [Operator.MemoryInject]: initialMemoryInjectValues,
  [Operator.AgentFanout]: initialAgentFanoutValues,
  [Operator.ResultAggregator]: initialResultAggregatorValues,
  [Operator.WebhookInput]: initialWebhookInputValues,
  [Operator.ExternalScoreReceiver]: initialExternalScoreReceiverValues,
  [Operator.HumanReview]: initialHumanReviewValues,
  [Operator.ManualApprove]: initialManualApproveValues,
  [Operator.NumberCalculate]: initialNumberCalculateValues,
  [Operator.ChartSpecBuilder]: initialChartSpecBuilderValues,
  [Operator.ChartRenderer]: initialChartRendererValues,
  [Operator.ArtifactPackager]: initialArtifactPackagerValues,
  [Operator.ScopedDBConnector]: initialScopedDBConnectorValues,
  [Operator.SafeTableEnsure]: initialSafeTableEnsureValues,
  [Operator.SafeRecordInsert]: initialSafeRecordInsertValues,
  [Operator.SafeRecordUpdate]: initialSafeRecordUpdateValues,
  [Operator.SafeRecordQuery]: initialSafeRecordQueryValues,
  [Operator.WorkspaceFileWrite]: initialWorkspaceFileWriteValues,
  [Operator.WorkspacePatchApply]: initialWorkspacePatchApplyValues,
};

const fieldsByOperator: Partial<Record<Operator, AdvancedField[]>> = {
  [Operator.PromptTemplate]: [
    { name: 'template', label: 'Template', kind: 'textarea' },
    { name: 'variables', label: 'Variables JSON', kind: 'textarea' },
  ],
  [Operator.ScoreRubricBuilder]: [
    { name: 'dimensions', label: 'Dimensions JSON', kind: 'textarea' },
  ],
  [Operator.PronunciationJudge]: [
    { name: 'structured_result', label: 'Structured result' },
    { name: 'rubric', label: 'Rubric' },
    {
      name: 'required_dimensions',
      label: 'Required dimensions JSON',
      kind: 'textarea',
    },
  ],
  [Operator.SummaryNode]: [
    { name: 'content', label: 'Content' },
    { name: 'max_chars', label: 'Max chars', kind: 'number' },
  ],
  [Operator.ReportComposer]: [
    { name: 'title', label: 'Title' },
    { name: 'sections', label: 'Sections JSON', kind: 'textarea' },
  ],
  [Operator.AudioInput]: [
    { name: 'audio', label: 'Audio file id or variable' },
  ],
  [Operator.TTSGenerate]: [
    { name: 'text', label: 'Text' },
    { name: 'voice_profile', label: 'Voice profile' },
    { name: 'speed', label: 'Speed', kind: 'number' },
    { name: 'endpoint', label: 'TTS endpoint' },
    { name: 'timeout', label: 'Timeout seconds', kind: 'number' },
  ],
  [Operator.ASRTranscribe]: [
    { name: 'audio', label: 'Audio' },
    { name: 'engine', label: 'Engine' },
    { name: 'language', label: 'Language' },
    { name: 'endpoint', label: 'ASR endpoint' },
    { name: 'timeout', label: 'Timeout seconds', kind: 'number' },
    { name: 'vad', label: 'VAD', kind: 'boolean' },
    { name: 'punctuation', label: 'Punctuation', kind: 'boolean' },
  ],
  [Operator.VoiceReplyOutput]: [
    { name: 'text', label: 'Text' },
    { name: 'audio', label: 'Audio' },
  ],
  [Operator.MeetingContextInput]: [
    { name: 'tenant_id', label: 'Tenant id' },
    { name: 'meeting_id', label: 'Meeting id' },
    { name: 'turn_id', label: 'Turn id' },
    { name: 'agent_id', label: 'Agent id' },
    { name: 'role', label: 'Role' },
    { name: 'query', label: 'Query' },
    { name: 'shared_memory', label: 'Shared memory JSON', kind: 'textarea' },
    { name: 'agent_memory', label: 'Agent memory JSON', kind: 'textarea' },
    {
      name: 'load_persisted_memory',
      label: 'Load persisted memory',
      kind: 'boolean',
    },
  ],
  [Operator.MemoryInject]: [
    { name: 'meeting_context', label: 'Meeting context' },
    { name: 'content', label: 'Content' },
    { name: 'scope', label: 'Scope' },
    { name: 'source', label: 'Source' },
    { name: 'run_id', label: 'Run id' },
    { name: 'role', label: 'Role' },
    { name: 'metadata', label: 'Metadata JSON', kind: 'textarea' },
  ],
  [Operator.AgentFanout]: [
    { name: 'meeting_context', label: 'Meeting context' },
    { name: 'content', label: 'Content' },
    { name: 'agents', label: 'Agents JSON', kind: 'textarea' },
    { name: 'files', label: 'Files JSON', kind: 'textarea' },
    { name: 'shared_context', label: 'Shared context', kind: 'textarea' },
    { name: 'base_inputs', label: 'Base inputs JSON', kind: 'textarea' },
    { name: 'user_id', label: 'User id' },
    { name: 'release', label: 'Release version', kind: 'boolean' },
    { name: 'return_trace', label: 'Return trace', kind: 'boolean' },
    { name: 'enqueue', label: 'Enqueue', kind: 'boolean' },
  ],
  [Operator.ResultAggregator]: [
    { name: 'runs', label: 'Runs JSON', kind: 'textarea' },
    { name: 'results', label: 'Results JSON', kind: 'textarea' },
    { name: 'scores', label: 'Scores JSON', kind: 'textarea' },
    { name: 'citations', label: 'Citations JSON', kind: 'textarea' },
    { name: 'memory_delta', label: 'Memory delta JSON', kind: 'textarea' },
  ],
  [Operator.WebhookInput]: [
    { name: 'payload', label: 'Payload JSON', kind: 'textarea' },
    { name: 'token', label: 'Token' },
    { name: 'expected_token', label: 'Expected token' },
  ],
  [Operator.ExternalScoreReceiver]: [
    { name: 'score_payload', label: 'Score payload JSON', kind: 'textarea' },
    { name: 'timeout_policy', label: 'Timeout policy' },
    { name: 'self_score', label: 'Self score', kind: 'number' },
  ],
  [Operator.HumanReview]: [
    { name: 'review_data', label: 'Review data JSON', kind: 'textarea' },
    { name: 'status', label: 'Status' },
    { name: 'reviewer', label: 'Reviewer' },
    { name: 'comment', label: 'Comment', kind: 'textarea' },
  ],
  [Operator.ManualApprove]: [
    { name: 'approved', label: 'Approved', kind: 'boolean' },
    { name: 'comment', label: 'Comment', kind: 'textarea' },
  ],
  [Operator.NumberCalculate]: [
    { name: 'operation', label: 'Operation' },
    { name: 'value', label: 'Value' },
    { name: 'coefficient', label: 'Coefficient', kind: 'number' },
    { name: 'self_score', label: 'Self score' },
    { name: 'self_weight', label: 'Self weight', kind: 'number' },
    { name: 'external_score', label: 'External score' },
    { name: 'external_weight', label: 'External weight', kind: 'number' },
    { name: 'result_name', label: 'Result name' },
    { name: 'round_digits', label: 'Round digits', kind: 'number' },
  ],
  [Operator.ChartSpecBuilder]: [
    { name: 'chart_type', label: 'Chart type' },
    { name: 'title', label: 'Title' },
    { name: 'data', label: 'Data' },
    { name: 'x_field', label: 'X field' },
    { name: 'y_field', label: 'Y field' },
    { name: 'series_field', label: 'Series field' },
    { name: 'dimensions', label: 'Dimensions JSON', kind: 'textarea' },
  ],
  [Operator.ChartRenderer]: [
    { name: 'chart_spec', label: 'Chart spec' },
    { name: 'charts', label: 'Charts JSON', kind: 'textarea' },
    { name: 'output_format', label: 'Output format' },
    { name: 'filename', label: 'Filename' },
  ],
  [Operator.ArtifactPackager]: [
    { name: 'artifacts', label: 'Artifacts JSON', kind: 'textarea' },
    { name: 'manifest', label: 'Manifest JSON', kind: 'textarea' },
    { name: 'filename', label: 'Filename' },
  ],
  [Operator.ScopedDBConnector]: [
    { name: 'agent_id', label: 'Agent id' },
    { name: 'db_path', label: 'DB path' },
  ],
  [Operator.SafeTableEnsure]: [
    { name: 'db_ref', label: 'DB ref' },
    { name: 'table_template', label: 'Table template' },
  ],
  [Operator.SafeRecordInsert]: [
    { name: 'table_ref', label: 'Table ref' },
    { name: 'record', label: 'Record JSON', kind: 'textarea' },
  ],
  [Operator.SafeRecordUpdate]: [
    { name: 'table_ref', label: 'Table ref' },
    { name: 'values', label: 'Values JSON', kind: 'textarea' },
    { name: 'filters', label: 'Filters JSON', kind: 'textarea' },
  ],
  [Operator.SafeRecordQuery]: [
    { name: 'table_ref', label: 'Table ref' },
    { name: 'filters', label: 'Filters JSON', kind: 'textarea' },
    { name: 'limit', label: 'Limit', kind: 'number' },
  ],
  [Operator.WorkspaceFileWrite]: [
    { name: 'root', label: 'Workspace root' },
    { name: 'path', label: 'Relative path' },
    { name: 'mode', label: 'Write mode' },
    { name: 'content', label: 'Content', kind: 'textarea' },
    { name: 'encoding', label: 'Encoding' },
    { name: 'expected_hash', label: 'Expected hash' },
    { name: 'dry_run', label: 'Dry run', kind: 'boolean' },
    { name: 'require_approval', label: 'Require approval', kind: 'boolean' },
    { name: 'approval_id', label: 'Approval id' },
    { name: 'approved', label: 'Manual approved', kind: 'boolean' },
    { name: 'task_id', label: 'Task id' },
    { name: 'max_bytes', label: 'Max bytes', kind: 'number' },
    { name: 'reason', label: 'Reason', kind: 'textarea' },
  ],
  [Operator.WorkspacePatchApply]: [
    { name: 'root', label: 'Workspace root' },
    { name: 'patch_format', label: 'Patch format' },
    { name: 'patch', label: 'Patch JSON or unified diff', kind: 'textarea' },
    {
      name: 'expected_hashes',
      label: 'Expected hashes JSON',
      kind: 'textarea',
    },
    { name: 'encoding', label: 'Encoding' },
    { name: 'dry_run', label: 'Dry run', kind: 'boolean' },
    { name: 'require_approval', label: 'Require approval', kind: 'boolean' },
    { name: 'approval_id', label: 'Approval id' },
    { name: 'approved', label: 'Manual approved', kind: 'boolean' },
    { name: 'task_id', label: 'Task id' },
    { name: 'max_files', label: 'Max files', kind: 'number' },
    { name: 'max_changed_lines', label: 'Max changed lines', kind: 'number' },
    { name: 'reason', label: 'Reason', kind: 'textarea' },
  ],
};

function toEditorValue(value: unknown) {
  if (typeof value === 'string') return value;
  if (value === undefined || value === null) return '';
  return JSON.stringify(value, null, 2);
}

function inferGenericFieldKind(value: unknown): FieldKind {
  if (typeof value === 'boolean') return 'boolean';
  if (typeof value === 'number') return 'number';
  if (Array.isArray(value) || (value && typeof value === 'object')) {
    return 'textarea';
  }
  if (
    typeof value === 'string' &&
    (value.length > 120 || value.includes('\n'))
  ) {
    return 'textarea';
  }
  return 'line';
}

function buildGenericFields(values: Record<string, unknown>): AdvancedField[] {
  return Object.entries(values || {})
    .filter(([name]) => name !== 'outputs')
    .map(([name, value]) => ({
      name,
      label: name
        .split('_')
        .filter(Boolean)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(' '),
      kind: inferGenericFieldKind(value),
    }));
}

function AdvancedNodeForm({ node }: INextOperatorForm) {
  const operatorName = node?.data.label as Operator;
  const initialValues =
    defaultsByOperator[operatorName as keyof typeof defaultsByOperator] ||
    initialPromptTemplateValues;
  const values = useFormValues(initialValues, node);
  const form = useForm<z.infer<typeof FormSchema>>({
    defaultValues: values,
    resolver: zodResolver(FormSchema),
  });
  const configuredFields = fieldsByOperator[operatorName] || [];
  const fields = useMemo(
    () =>
      configuredFields.length > 0
        ? configuredFields
        : buildGenericFields(values),
    [configuredFields, values],
  );
  const outputList = useMemo(() => transferOutputs(values.outputs), [values]);

  useWatchFormChange(node?.id, form);

  return (
    <Form {...form}>
      <FormWrapper>
        <FormContainer>
          {fields.map((item) => {
            if (item.kind === 'boolean') {
              return (
                <FormField
                  key={item.name}
                  control={form.control}
                  name={item.name}
                  render={({ field }) => (
                    <FormItem className="flex items-center justify-between gap-4">
                      <FormLabel>{item.label}</FormLabel>
                      <FormControl>
                        <Switch
                          checked={Boolean(field.value)}
                          onCheckedChange={field.onChange}
                        />
                      </FormControl>
                    </FormItem>
                  )}
                />
              );
            }

            if (item.kind === 'textarea') {
              return (
                <FormField
                  key={item.name}
                  control={form.control}
                  name={item.name}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{item.label}</FormLabel>
                      <FormControl>
                        <PromptEditor
                          value={toEditorValue(field.value)}
                          onChange={field.onChange}
                          showToolbar={false}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              );
            }

            return (
              <FormField
                key={item.name}
                control={form.control}
                name={item.name}
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{item.label}</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        type={item.kind === 'number' ? 'number' : 'text'}
                        onChange={(event) =>
                          item.kind === 'number'
                            ? field.onChange(Number(event.target.value))
                            : field.onChange(event.target.value)
                        }
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
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

export default memo(AdvancedNodeForm);
