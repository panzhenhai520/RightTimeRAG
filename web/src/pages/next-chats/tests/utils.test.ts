import { MessageType } from '@/constants/chat';
import { IReference } from '@/interfaces/database/chat';
import { buildMessageItemReference } from '../utils';

const serverReference = {
  chunks: [],
  doc_aggs: [],
  total: 0,
  evidence_audit: {
    retrieval: {
      candidate_docs: 1,
      candidate_chunks: 1,
      selected_chunks: 1,
    },
  },
} satisfies IReference;

const messageReference = {
  chunks: [
    {
      id: 'chunk-1',
      content: 'source text',
      document_id: 'doc-1',
      document_name: 'Doc.pdf',
      dataset_id: 'kb-1',
      image_id: '',
      similarity: 0.9,
      vector_similarity: 0.9,
      term_similarity: 0.8,
      positions: [],
    },
  ],
  doc_aggs: [{ doc_id: 'doc-1', doc_name: 'Doc.pdf', count: 1 }],
  total: 1,
} satisfies IReference;

describe('buildMessageItemReference', () => {
  it('merges server evidence audit into a non-empty local message reference', () => {
    const reference = buildMessageItemReference(
      {
        messages: [
          {
            id: 'prologue',
            role: MessageType.Assistant,
            content: 'hello',
          },
          {
            id: 'question-1',
            role: MessageType.User,
            content: 'question',
          },
          {
            id: 'question-1',
            role: MessageType.Assistant,
            content: 'answer',
            reference: messageReference,
          },
        ],
        reference: [serverReference],
      },
      {
        id: 'question-1',
        role: MessageType.Assistant,
        content: 'answer',
        reference: messageReference,
      },
    );

    expect(reference.chunks).toHaveLength(1);
    expect(reference.doc_aggs).toHaveLength(1);
    expect(reference.evidence_audit?.retrieval?.selected_chunks).toBe(1);
  });

  it('uses the first server reference when there is no prologue assistant', () => {
    const reference = buildMessageItemReference(
      {
        messages: [
          {
            id: 'question-1',
            role: MessageType.User,
            content: 'question',
          },
          {
            id: 'question-1',
            role: MessageType.Assistant,
            content: 'answer',
          },
        ],
        reference: [serverReference],
      },
      {
        id: 'question-1',
        role: MessageType.Assistant,
        content: 'answer',
      },
    );

    expect(reference.evidence_audit?.retrieval?.selected_chunks).toBe(1);
  });

  it('matches the assistant by object position when ids are absent', () => {
    const answer = {
      role: MessageType.Assistant,
      content: 'answer',
    } as any;
    const reference = buildMessageItemReference(
      {
        messages: [
          {
            role: MessageType.Assistant,
            content: 'hello',
          } as any,
          {
            id: 'question-1',
            role: MessageType.User,
            content: 'question',
          },
          answer,
        ],
        reference: [serverReference],
      },
      answer,
    );

    expect(reference.evidence_audit?.retrieval?.selected_chunks).toBe(1);
  });
});
