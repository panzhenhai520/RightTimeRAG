import { EmptyConversationId, MessageType } from '@/constants/chat';
import {
  IConversation,
  IMessage,
  IReference,
} from '@/interfaces/database/chat';
import { isEmpty } from 'lodash';

export const isConversationIdExist = (conversationId: string) => {
  return conversationId !== EmptyConversationId && conversationId !== '';
};

export const getDocumentIdsFromConversionReference = (data: IConversation) => {
  const documentIds = data.reference.reduce(
    (pre: Array<string>, cur: IReference) => {
      cur.doc_aggs
        ?.map((x) => x.doc_id)
        .forEach((x) => {
          if (pre.every((y) => y !== x)) {
            pre.push(x);
          }
        });
      return pre;
    },
    [],
  );
  return documentIds.join(',');
};

const toArray = <T>(value: T[] | Record<string, T> | undefined | null) => {
  if (Array.isArray(value)) return value;
  if (value && typeof value === 'object') return Object.values(value);
  return [];
};

const normalizeReference = (reference?: Partial<IReference>) => {
  const chunks = toArray(reference?.chunks as any).map((chunk: any) => {
    const kbId = chunk?.kb_id;
    return {
      ...chunk,
      id: chunk?.id ?? chunk?.chunk_id ?? '',
      content:
        typeof chunk?.content === 'string'
          ? chunk.content
          : typeof chunk?.content_with_weight === 'string'
            ? chunk.content_with_weight
            : '',
      document_id: chunk?.document_id ?? chunk?.doc_id ?? '',
      document_name: chunk?.document_name ?? chunk?.docnm_kwd ?? '',
      dataset_id:
        chunk?.dataset_id ??
        (Array.isArray(kbId) ? (kbId[0] ?? '') : (kbId ?? '')),
      image_id: chunk?.image_id ?? chunk?.img_id ?? '',
      positions: Array.isArray(chunk?.positions)
        ? chunk.positions
        : Array.isArray(chunk?.position_int)
          ? chunk.position_int
          : [],
    };
  });
  const docAggs = toArray(reference?.doc_aggs as any);

  return {
    ...reference,
    chunks,
    doc_aggs: docAggs,
    total: reference?.total ?? chunks.length,
  } as IReference;
};

const hasReferenceItems = (value: unknown) => {
  if (Array.isArray(value)) return value.length > 0;
  if (value && typeof value === 'object') return Object.keys(value).length > 0;
  return false;
};

const mergeMessageReference = (
  serverReference?: Partial<IReference>,
  messageReference?: Partial<IReference>,
) => {
  const normalizedServerReference = normalizeReference(serverReference);
  const normalizedMessageReference = normalizeReference(messageReference);
  const hasServerPayload =
    hasReferenceItems(normalizedServerReference.chunks) ||
    hasReferenceItems(normalizedServerReference.doc_aggs) ||
    normalizedServerReference.evidence_audit;
  const hasMessagePayload =
    hasReferenceItems(normalizedMessageReference.chunks) ||
    hasReferenceItems(normalizedMessageReference.doc_aggs) ||
    normalizedMessageReference.evidence_audit;

  if (!hasServerPayload && !hasMessagePayload) {
    return normalizeReference({ doc_aggs: [], chunks: [], total: 0 });
  }
  if (!hasServerPayload) return normalizedMessageReference;
  if (!hasMessagePayload) return normalizedServerReference;

  const hasMessageChunks = hasReferenceItems(normalizedMessageReference.chunks);
  const hasMessageDocAggs = hasReferenceItems(
    normalizedMessageReference.doc_aggs,
  );

  return {
    ...normalizedServerReference,
    ...normalizedMessageReference,
    chunks: hasMessageChunks
      ? normalizedMessageReference.chunks
      : normalizedServerReference.chunks,
    doc_aggs: hasMessageDocAggs
      ? normalizedMessageReference.doc_aggs
      : normalizedServerReference.doc_aggs,
    evidence_audit:
      normalizedMessageReference.evidence_audit ??
      normalizedServerReference.evidence_audit,
    total:
      hasMessageChunks || hasMessageDocAggs
        ? normalizedMessageReference.total
        : normalizedServerReference.total,
  } as IReference;
};

export const buildMessageItemReference = (
  conversation: { messages: IMessage[]; reference: IReference[] },
  message: IMessage,
) => {
  const references = conversation?.reference ?? [];
  const messages = conversation?.messages ?? [];
  const allAssistantMessages = messages.filter(
    (x) =>
      x.role === MessageType.Assistant &&
      !String(x.content ?? '').startsWith('**ERROR**:'), // Exclude error messages
  );
  const firstAssistantIndex = messages.findIndex(
    (x) =>
      x.role === MessageType.Assistant &&
      !String(x.content ?? '').startsWith('**ERROR**:'),
  );
  const hasPrologue = firstAssistantIndex === 0;
  const assistantMessages = hasPrologue
    ? allAssistantMessages.slice(1)
    : allAssistantMessages;
  const referenceIndexByObject = assistantMessages.findIndex(
    (x) => x === message,
  );
  const referenceIndexById =
    message.id === undefined || message.id === null
      ? -1
      : assistantMessages.findIndex((x) => x.id === message.id);
  const referenceIndex =
    referenceIndexByObject >= 0 ? referenceIndexByObject : referenceIndexById;
  const latestAssistant = assistantMessages[assistantMessages.length - 1];
  const isLatestAssistant =
    latestAssistant === message ||
    (message.id !== undefined &&
      message.id !== null &&
      latestAssistant?.id === message.id);
  const serverReference =
    referenceIndex >= 0
      ? references[referenceIndex]
      : isLatestAssistant
        ? references[references.length - 1]
        : undefined;

  return mergeMessageReference(
    serverReference,
    !isEmpty(message?.reference) ? message.reference : undefined,
  );
};
