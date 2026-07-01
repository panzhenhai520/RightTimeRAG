import {
  areSchemaTypesCompatible,
  validateConnectionBySchema,
} from './connection-schema';

const field = (name: string, type: string) => ({ name, type });

const manifests = [
  {
    operator: 'FileParser',
    component_name: 'FileParser',
    category: 'data',
    input_schema: {},
    output_schema: {
      file: field('file', 'FileAsset'),
      chunks: field('chunks', 'Array<TextChunk>'),
      document: field('document', 'TextDocument'),
      text: field('text', 'String'),
    },
    config_schema: {},
    runtime_capabilities: {
      streaming: false,
      long_running: false,
      produces_artifacts: false,
      accepts_files: false,
      uses_external_io: false,
      supports_cancel: false,
    },
    risk_level: 'low',
    requires_service: [],
  },
  {
    operator: 'LLM',
    component_name: 'LLM',
    category: 'model',
    input_schema: {
      prompt: field('prompt', 'String'),
      chunks: field('chunks', 'Array<TextChunk>'),
      document: field('document', 'TextDocument'),
    },
    output_schema: {},
    config_schema: {},
    runtime_capabilities: {
      streaming: true,
      long_running: false,
      produces_artifacts: false,
      accepts_files: false,
      uses_external_io: false,
      supports_cancel: false,
    },
    risk_level: 'medium',
    requires_service: [],
  },
];

const nodes = [
  { id: 'source', data: { label: 'FileParser', name: 'Parser' } },
  { id: 'target', data: { label: 'LLM', name: 'LLM' } },
] as any;

describe('agent connection schema validation', () => {
  it('allows normal text into prompt input', () => {
    expect(areSchemaTypesCompatible('String', 'String', 'LLM', 'prompt')).toBe(
      true,
    );
  });

  it('blocks binary/file-like outputs from prompt inputs', () => {
    expect(areSchemaTypesCompatible('FileAsset', 'String', 'LLM', 'prompt')).toBe(
      false,
    );
    expect(
      areSchemaTypesCompatible('Array<FileAsset>', 'String', 'LLM', 'prompt'),
    ).toBe(false);
    expect(
      areSchemaTypesCompatible('MeetingContext', 'String', 'LLM', 'prompt'),
    ).toBe(false);
    expect(
      areSchemaTypesCompatible('VoiceReply', 'String', 'LLM', 'prompt'),
    ).toBe(false);
  });

  it('keeps structured document and chunk types separate', () => {
    expect(areSchemaTypesCompatible('Array<TextChunk>', 'Array<TextChunk>')).toBe(
      true,
    );
    expect(areSchemaTypesCompatible('Array<TextChunk>', 'TextDocument')).toBe(
      false,
    );
    expect(areSchemaTypesCompatible('TextDocument', 'Array<TextChunk>')).toBe(
      false,
    );
  });

  it('validates edge ports with operator manifests', () => {
    const valid = validateConnectionBySchema({
      connection: {
        source: 'source',
        target: 'target',
        sourceHandle: 'output:chunks',
        targetHandle: 'input:chunks',
      } as any,
      nodes,
      manifests: manifests as any,
    });
    const invalid = validateConnectionBySchema({
      connection: {
        source: 'source',
        target: 'target',
        sourceHandle: 'output:file',
        targetHandle: 'input:prompt',
      } as any,
      nodes,
      manifests: manifests as any,
    });

    expect(valid.valid).toBe(true);
    expect(invalid.valid).toBe(false);
    expect(invalid.reason).toContain('FileAsset');
  });
});
