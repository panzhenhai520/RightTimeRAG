jest.mock('eventsource-parser/stream', () => ({}));

import { IReference } from '@/interfaces/database/chat';
import { hasAnswerPayload, mergeAnswerReference } from '../logic-hooks';

const previousReference = {
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

describe('mergeAnswerReference', () => {
  it('keeps existing chunks when a follow-up event only patches evidence audit', () => {
    const merged = mergeAnswerReference(previousReference, {
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
    });

    expect(merged?.chunks).toEqual(previousReference.chunks);
    expect(merged?.doc_aggs).toEqual(previousReference.doc_aggs);
    expect(merged?.evidence_audit?.retrieval?.selected_chunks).toBe(1);
    expect(merged?.total).toBe(1);
  });

  it('ignores an empty incoming reference instead of clearing the current one', () => {
    const merged = mergeAnswerReference(previousReference, {
      chunks: [],
      doc_aggs: [],
      total: 0,
    });

    expect(merged).toBe(previousReference);
  });
});

describe('hasAnswerPayload', () => {
  it('accepts an empty answer event when it carries an evidence audit reference patch', () => {
    expect(
      hasAnswerPayload({
        answer: '',
        reference: {
          chunks: [],
          doc_aggs: [],
          total: 0,
          evidence_audit: { retrieval: { selected_chunks: 1 } },
        },
      }),
    ).toBe(true);
  });
});
