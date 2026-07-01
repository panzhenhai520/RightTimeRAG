import type {
  IAgentOperatorManifest,
  IAgentSchemaField,
  RAGFlowNodeType,
} from '@/interfaces/database/agent';
import type { Connection, Edge } from '@xyflow/react';

const ANY = 'Any';
const STRING = 'String';
const NUMBER = 'Number';
const BOOLEAN = 'Boolean';
const FILE_ASSET = 'FileAsset';
const TEXT_DOCUMENT = 'TextDocument';
const TEXT_CHUNK = 'TextChunk';
const AUDIO_ASSET = 'AudioAsset';
const ARRAY_PREFIX = 'Array<';

const aliases: Record<string, string> = {
  any: ANY,
  str: STRING,
  string: STRING,
  text: STRING,
  line: STRING,
  paragraph: STRING,
  number: NUMBER,
  int: NUMBER,
  integer: NUMBER,
  float: NUMBER,
  boolean: BOOLEAN,
  bool: BOOLEAN,
  file: FILE_ASSET,
  fileasset: FILE_ASSET,
  audio: AUDIO_ASSET,
  audioasset: AUDIO_ASSET,
  object: 'JSON',
  json: 'JSON',
  tabledata: 'TableData',
  sqlresult: 'SQLResult',
  artifact: 'Artifact',
  chartspec: 'ChartSpec',
  voicereply: 'VoiceReply',
  agentrunref: 'AgentRunRef',
  meetingcontext: 'MeetingContext',
  scoreresult: 'ScoreResult',
  scorerubric: 'ScoreRubric',
  textdocument: TEXT_DOCUMENT,
  textchunk: TEXT_CHUNK,
};

function normalizeType(type?: string) {
  const raw = String(type || ANY).trim();
  const compact = raw.replace(/\s+/g, '');
  const lower = compact.toLowerCase();
  if (lower.startsWith('array<') && compact.endsWith('>')) {
    return `Array<${normalizeType(compact.slice(6, -1))}>`;
  }
  if (lower.endsWith('[]')) {
    return `Array<${normalizeType(compact.slice(0, -2))}>`;
  }
  return aliases[lower] ?? (compact ? compact[0].toUpperCase() + compact.slice(1) : ANY);
}

function arrayInner(type?: string) {
  const normalized = normalizeType(type);
  return normalized.startsWith(ARRAY_PREFIX) && normalized.endsWith('>')
    ? normalized.slice(ARRAY_PREFIX.length, -1)
    : '';
}

function baseType(type?: string) {
  return arrayInner(type) || normalizeType(type);
}

function isBlockedPromptType(type?: string) {
  return ['Artifact', FILE_ASSET, AUDIO_ASSET, 'VoiceReply', 'AgentRunRef', 'MeetingContext'].includes(
    baseType(type),
  );
}

export function areSchemaTypesCompatible(
  sourceType?: string,
  targetType?: string,
  targetOperator?: string,
  targetInput?: string,
) {
  const source = normalizeType(sourceType);
  const target = normalizeType(targetType);
  const sourceBase = baseType(source);
  const targetBase = baseType(target);

  if (source === ANY || target === ANY || source === target) return true;

  const isPromptTarget =
    ['Agent', 'AgentWithTools', 'LLM', 'Categorize', 'RewriteQuestion'].includes(
      targetOperator || '',
    ) &&
    ['sys_prompt', 'prompts', 'prompt', 'user_prompt', 'context', 'reasoning'].includes(
      targetInput || '',
    );
  if (isPromptTarget && isBlockedPromptType(source)) return false;

  if (target === STRING) return !isBlockedPromptType(source);
  if (targetBase === FILE_ASSET) return sourceBase === FILE_ASSET;
  if (targetBase === TEXT_DOCUMENT || targetBase === TEXT_CHUNK) return sourceBase === targetBase;
  if (targetBase === AUDIO_ASSET) return sourceBase === AUDIO_ASSET;
  if (targetBase === NUMBER) return sourceBase === NUMBER;
  if (targetBase === BOOLEAN) return sourceBase === BOOLEAN;

  return sourceBase === targetBase;
}

export function summarizeSchema(schema?: Record<string, IAgentSchemaField>) {
  const entries = Object.values(schema || {});
  if (entries.length === 0) return 'Any';
  const head = entries.slice(0, 5).map((field) => `${field.name}: ${normalizeType(field.type)}`);
  const rest = entries.length > head.length ? `\n+${entries.length - head.length} more` : '';
  return `${head.join('\n')}${rest}`;
}

function getManifest(
  node?: RAGFlowNodeType,
  manifests?: IAgentOperatorManifest[],
) {
  const label = node?.data?.label;
  return manifests?.find((item) => item.operator === label || item.component_name === label);
}

function parsePortHandle(handle?: string | null, direction?: 'source' | 'target') {
  if (!handle) return '';
  const prefixes = direction === 'source' ? ['output:', 'out:'] : ['input:', 'in:'];
  const prefix = prefixes.find((item) => handle.startsWith(item));
  return prefix ? handle.slice(prefix.length) : '';
}

export function validateConnectionBySchema({
  connection,
  nodes,
  manifests,
}: {
  connection: Connection | Edge;
  nodes: RAGFlowNodeType[];
  manifests: IAgentOperatorManifest[];
}) {
  const sourceNode = nodes.find((node) => node.id === connection.source);
  const targetNode = nodes.find((node) => node.id === connection.target);
  const sourceManifest = getManifest(sourceNode, manifests);
  const targetManifest = getManifest(targetNode, manifests);
  const sourcePort = parsePortHandle(connection.sourceHandle, 'source');
  const targetPort = parsePortHandle(connection.targetHandle, 'target');

  if (!sourceManifest || !targetManifest || !sourcePort || !targetPort) {
    return { valid: true };
  }

  const sourceField = sourceManifest.output_schema[sourcePort];
  const targetField = targetManifest.input_schema[targetPort];
  if (!sourceField || !targetField) {
    return { valid: true };
  }

  const valid = areSchemaTypesCompatible(
    sourceField.type,
    targetField.type,
    targetManifest.operator,
    targetField.name,
  );

  return {
    valid,
    reason: valid
      ? ''
      : `${sourceNode?.data?.name || sourceNode?.id}.${sourceField.name} (${normalizeType(
          sourceField.type,
        )}) -> ${targetNode?.data?.name || targetNode?.id}.${targetField.name} (${normalizeType(
          targetField.type,
        )})`,
  };
}
