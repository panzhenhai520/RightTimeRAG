import {
  ChatVariableEnabledField,
  EmptyConversationId,
} from '@/constants/chat';
import { IMessage, Message } from '@/interfaces/database/chat';
import { omit } from 'lodash';
import { v4 as uuid } from 'uuid';
import {
  citationMarkerReg,
  normalizeCitationDigits,
  parseCitationIndex,
} from './citation-utils';

export const isConversationIdExist = (conversationId: string) => {
  return conversationId !== EmptyConversationId && conversationId !== '';
};

export const buildMessageUuid = (message: Partial<Message | IMessage>) => {
  if ('id' in message && message.id) {
    return message.id;
  }
  return uuid();
};

export const buildMessageListWithUuid = (messages?: Message[]) => {
  return (
    messages?.map((x: Message | IMessage) => ({
      ...omit(x, 'reference'),
      id: buildMessageUuid(x),
    })) ?? []
  );
};

export const generateConversationId = () => {
  return uuid().replace(/-/g, '');
};

// When rendering each message, add a prefix to the id to ensure uniqueness.
export const buildMessageUuidWithRole = (
  message: Partial<Message | IMessage>,
) => {
  return `${message.role}_${message.id}`;
};

// Preprocess LaTeX equations to be rendered by KaTeX
// ref: https://github.com/remarkjs/react-markdown/issues/785
//
// Delimiter matching: we only treat \] and \) as block/inline endings when they
// are not part of a LaTeX command (e.g. \right], \big), \left)). Use a negative
// lookbehind (?<![a-zA-Z]) so that \] or \) preceded by a letter (command name)
// is not considered the closing delimiter. Use greedy matching so we match up to
// the last valid delimiter and avoid cutting at the first \] or \) inside the
// equation (e.g. \frac{1}{|y|} or \right]).

const BLOCK_MATH_RE = /\\\[([\s\S]*?)(?<![a-zA-Z])\\\]/g;
const INLINE_MATH_RE = /\\\(([\s\S]*?)(?<![a-zA-Z])\\\)/g;

export const preprocessLaTeX = (content: string) => {
  const normalizedContent = content
    .replace(/\\\\\[/g, '\\[')
    .replace(/\\\\\(/g, '\\(')
    .replace(/\\\\\]/g, '\\]')
    .replace(/\\\\\)/g, '\\)')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&');

  const blockProcessedContent = normalizedContent.replace(
    BLOCK_MATH_RE,
    (_, equation) => `$$${equation}$$`,
  );

  const inlineProcessedContent = blockProcessedContent.replace(
    INLINE_MATH_RE,
    (_, equation) => `$${equation}$`,
  );

  return inlineProcessedContent;
};

export function replaceThinkToSection(
  text: string = '',
  summary = 'View reasoning process',
) {
  const pattern = /<think>([\s\S]*?)<\/think>/g;

  const result = text.replace(
    pattern,
    `<details class="think"><summary>${summary}</summary>$1</details>`,
  );

  return result;
}

export function parseThinkAndAnswer(text: string = '') {
  return parseTaggedContent(text, 'think');
}

export function parseRetrievingAndAnswer(text: string = '') {
  return parseTaggedContent(text, 'retrieving');
}

export function stripProcessBlocks(text: string = '') {
  return (text || '')
    .replace(/<retrieving>[\s\S]*?<\/retrieving>/gi, '')
    .replace(/<think>[\s\S]*?<\/think>/gi, '')
    .replace(/<\/?(?:retrieving|think)>/gi, '')
    .trim();
}

export function getTtsReadableContent(text: string = '') {
  return stripProcessBlocks(
    (text || '')
      .replace(
        /<details[^>]*class=["'][^"']*(?:think|retrieving)[^"']*["'][^>]*>[\s\S]*?<\/details>/gi,
        '',
      )
      .replace(
        /<section[^>]*class=["'][^"']*(?:think|retrieving)[^"']*["'][^>]*>[\s\S]*?<\/section>/gi,
        '',
      ),
  );
}

export const extractTaggedBlocks = (text: string = '', tagName: string) => {
  const pattern = new RegExp(`<${tagName}>[\\s\\S]*?</${tagName}>`, 'gi');
  return text.match(pattern)?.join('') ?? '';
};

export const extractProcessBlocksForFinal = (
  text: string = '',
  tagName: string,
) => {
  const parsed = parseTaggedContent(text, tagName as 'think' | 'retrieving');
  const thinking = parsed.thinking.trim();

  if (!parsed.hasThinking || !thinking) {
    return extractTaggedBlocks(text, tagName);
  }

  return `<${tagName}>${thinking}</${tagName}>`;
};

export const stripProcessBlocksForFinal = (text: string = '') => {
  return (text || '')
    .replace(/<retrieving>[\s\S]*?<\/retrieving>/gi, '')
    .replace(/<think>[\s\S]*?<\/think>/gi, '')
    .replace(/<\/?(?:retrieving|think)>/gi, '')
    .trimStart();
};

const countCitationMarkers = (text: string = '') => {
  return (text.match(new RegExp(citationMarkerReg.source, 'g')) ?? []).length;
};

const shouldKeepStreamedVisibleAnswer = (
  streamedVisibleAnswer: string,
  finalVisibleAnswer: string,
) => {
  if (!streamedVisibleAnswer || !finalVisibleAnswer) {
    return false;
  }

  const streamedCitationCount = countCitationMarkers(streamedVisibleAnswer);
  const finalCitationCount = countCitationMarkers(finalVisibleAnswer);

  if (finalCitationCount > streamedCitationCount) {
    return false;
  }

  const streamedLength = streamedVisibleAnswer.trim().length;
  const finalLength = finalVisibleAnswer.trim().length;
  if (streamedLength === 0) {
    return false;
  }

  return finalLength < streamedLength * 0.9;
};

export const mergeFinalAnswerWithProcess = (
  previousAnswer: string = '',
  finalAnswer: string = '',
) => {
  if (!previousAnswer) return finalAnswer;
  if (!finalAnswer) return previousAnswer;

  const processPrefix =
    extractProcessBlocksForFinal(previousAnswer, 'retrieving') +
    extractProcessBlocksForFinal(previousAnswer, 'think');

  if (!processPrefix) {
    return finalAnswer;
  }

  const finalVisibleAnswer = stripProcessBlocksForFinal(finalAnswer);
  if (!finalVisibleAnswer) {
    return previousAnswer;
  }

  const streamedVisibleAnswer = stripProcessBlocksForFinal(previousAnswer);
  if (
    shouldKeepStreamedVisibleAnswer(streamedVisibleAnswer, finalVisibleAnswer)
  ) {
    return processPrefix + streamedVisibleAnswer;
  }

  return processPrefix + finalVisibleAnswer;
};

const hasUnclosedProcessTag = (
  text: string = '',
  tagName: 'think' | 'retrieving',
) => {
  const openTag = `<${tagName}>`;
  const closeTag = `</${tagName}>`;
  const lowerText = text.toLowerCase();
  const lastOpenIndex = lowerText.lastIndexOf(openTag);
  const lastCloseIndex = lowerText.lastIndexOf(closeTag);

  return lastOpenIndex !== -1 && lastOpenIndex > lastCloseIndex;
};

export const mergeStreamingAnswerChunk = (
  previousAnswer: string = '',
  incomingAnswer: string = '',
) => {
  if (!previousAnswer) return incomingAnswer;
  if (!incomingAnswer) return previousAnswer;

  const processOpenTag = incomingAnswer
    .trim()
    .toLowerCase()
    .match(/^<(retrieving|think)>$/);
  if (
    processOpenTag &&
    hasUnclosedProcessTag(
      previousAnswer,
      processOpenTag[1] as 'think' | 'retrieving',
    )
  ) {
    return previousAnswer;
  }

  if (incomingAnswer.startsWith(previousAnswer)) {
    return incomingAnswer;
  }

  return previousAnswer + incomingAnswer;
};

function parseTaggedContent(
  text: string = '',
  tagName: 'think' | 'retrieving',
) {
  const normalizedText = text || '';
  const tagPattern = new RegExp(`<\\/?${tagName}>`, 'g');
  const matches = Array.from(normalizedText.matchAll(tagPattern));

  if (matches.length === 0) {
    return {
      thinking: '',
      answer: normalizedText,
      hasThinking: false,
      thinkingComplete: false,
    };
  }

  const thinkingParts: string[] = [];
  const answerParts: string[] = [];
  let cursor = 0;
  let inThinking = false;
  let hasThinking = false;

  for (const match of matches) {
    const tag = match[0];
    const index = match.index ?? 0;
    const chunk = normalizedText.slice(cursor, index);

    if (inThinking) {
      thinkingParts.push(chunk);
    } else {
      answerParts.push(chunk);
    }

    if (tag === `<${tagName}>`) {
      inThinking = true;
      hasThinking = true;
    } else {
      inThinking = false;
    }

    cursor = index + tag.length;
  }

  const tail = normalizedText.slice(cursor);
  if (inThinking) {
    thinkingParts.push(tail);
  } else {
    answerParts.push(tail);
  }

  return {
    thinking: thinkingParts
      .join('')
      .replace(tagPattern, '')
      .replace(/<br\s*\/?>/gi, '\n'),
    answer: answerParts.join('').replace(tagPattern, ''),
    hasThinking,
    thinkingComplete: !inThinking,
  };
}

export function getThinkingPreview(text: string = '', maxLines = 1) {
  return text
    .replace(/<br\s*\/?>/gi, '\n')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(-maxLines)
    .join('\n');
}

export function replaceRetrievingToSection(
  text: string = '',
  summary = 'View retrieval process',
) {
  const pattern = /<retrieving>([\s\S]*?)<\/retrieving>/g;

  const result = text.replace(
    pattern,
    `<details class="retrieving"><summary>${summary}</summary>$1</details>`,
  );

  return result;
}

export function setInitialChatVariableEnabledFieldValue(
  field: ChatVariableEnabledField,
) {
  return field !== ChatVariableEnabledField.MaxTokensEnabled;
}

const ShowImageFields = ['image', 'table'];

export function showImage(filed?: string) {
  return ShowImageFields.some((x) => x === filed);
}

export function setChatVariableEnabledFieldValuePage() {
  const variableCheckBoxFieldMap = Object.values(
    ChatVariableEnabledField,
  ).reduce<Record<string, boolean>>((pre, cur) => {
    pre[cur] = cur !== ChatVariableEnabledField.MaxTokensEnabled;
    return pre;
  }, {});

  return variableCheckBoxFieldMap;
}

const oldReg = /(#{2}[0-9\u0660-\u0669\u06F0-\u06F9]+\${2})/g;
export const currentReg = citationMarkerReg;
export { normalizeCitationDigits, parseCitationIndex };

// To be compatible with the old index matching mode
export const replaceTextByOldReg = (text: string) => {
  return text?.replace(oldReg, (substring: string) => {
    return `[ID:${substring.slice(2, -2)}]`;
  });
};
