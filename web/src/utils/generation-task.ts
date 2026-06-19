import i18n from '@/locales/config';

export type GenerationTaskType =
  | 'normal_qa'
  | 'long_report'
  | 'novel'
  | 'research'
  | 'document';

export interface GenerationTaskClassification {
  shouldGenerateDocument: boolean;
  taskType: GenerationTaskType;
  expectedOutput: 'short' | 'medium' | 'long' | 'very_long';
  summary: string;
  outline: string[];
  reason: string;
}

const numberTextToValue = (value: string, unit?: string) => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 0;
  if (unit === '万字') return numeric * 10000;
  return numeric;
};

const getExplicitLength = (text: string) => {
  const chineseLength = text.match(/(\d+(?:\.\d+)?)\s*(万字|字)/);
  if (chineseLength) {
    return numberTextToValue(chineseLength[1], chineseLength[2]);
  }

  const englishLength = text.match(/(\d+(?:\.\d+)?)\s*(words?|tokens?)/i);
  if (englishLength) {
    return Number(englishLength[1]);
  }

  return 0;
};

const hasAny = (text: string, patterns: RegExp[]) =>
  patterns.some((pattern) => pattern.test(text));

const buildOutline = (taskType: GenerationTaskType) => {
  if (taskType === 'novel') {
    return [
      i18n.t('chat.longTaskNovelOutline1', {
        defaultValue: 'Premise, setting, and central conflict',
      }),
      i18n.t('chat.longTaskNovelOutline2', {
        defaultValue: 'Main characters and relationship arcs',
      }),
      i18n.t('chat.longTaskNovelOutline3', {
        defaultValue: 'Chapter-by-chapter plot progression',
      }),
      i18n.t('chat.longTaskNovelOutline4', {
        defaultValue: 'Turning points, climax, and ending',
      }),
    ];
  }

  if (taskType === 'research') {
    return [
      i18n.t('chat.longTaskResearchOutline1', {
        defaultValue: 'Research objective and scope',
      }),
      i18n.t('chat.longTaskResearchOutline2', {
        defaultValue: 'Key facts, evidence, and assumptions',
      }),
      i18n.t('chat.longTaskResearchOutline3', {
        defaultValue: 'Analysis framework and findings',
      }),
      i18n.t('chat.longTaskResearchOutline4', {
        defaultValue: 'Conclusions, risks, and next steps',
      }),
    ];
  }

  return [
    i18n.t('chat.longTaskReportOutline1', {
      defaultValue: 'Executive summary and background',
    }),
    i18n.t('chat.longTaskReportOutline2', {
      defaultValue: 'Main arguments and supporting evidence',
    }),
    i18n.t('chat.longTaskReportOutline3', {
      defaultValue: 'Detailed section analysis',
    }),
    i18n.t('chat.longTaskReportOutline4', {
      defaultValue: 'Conclusion and action recommendations',
    }),
  ];
};

export function classify_generation_task(
  text: string,
): GenerationTaskClassification {
  const input = (text || '').trim();
  const explicitLength = getExplicitLength(input);
  const normalized = input.toLowerCase();

  const isNovel = hasAny(normalized, [
    /小说/,
    /故事/,
    /章节/,
    /人物设定/,
    /中篇/,
    /长篇/,
    /\bnovel\b/,
    /\bstory\b/,
    /\bchapter\b/,
  ]);
  const isResearch = hasAny(normalized, [
    /深度研究/,
    /深入研究/,
    /系统研究/,
    /全面研究/,
    /研究.+报告/,
    /\bdeep research\b/,
    /\bresearch\b/,
  ]);
  const isReport = hasAny(normalized, [
    /报告/,
    /白皮书/,
    /尽调/,
    /调研/,
    /全面分析/,
    /系统梳理/,
    /\breport\b/,
    /\bwhite paper\b/,
    /\banalysis report\b/,
    /\bcomprehensive analysis\b/,
  ]);
  const isLongDocument = hasAny(normalized, [
    /生成.*文档/,
    /markdown文档/,
    /写一篇/,
    /不少于/,
    /不能低于/,
    /\bmarkdown document\b/,
    /\blong-form\b/,
  ]);

  let taskType: GenerationTaskType = 'normal_qa';
  if (isNovel) taskType = 'novel';
  else if (isResearch) taskType = 'research';
  else if (isReport) taskType = 'long_report';
  else if (isLongDocument) taskType = 'document';

  const shouldGenerateDocument =
    taskType !== 'normal_qa' &&
    (explicitLength >= 3000 ||
      input.length >= 250 ||
      isNovel ||
      isResearch ||
      isLongDocument);

  const expectedOutput = shouldGenerateDocument
    ? explicitLength >= 8000 || isNovel || isResearch
      ? 'very_long'
      : 'long'
    : input.length > 180
      ? 'medium'
      : 'short';

  return {
    shouldGenerateDocument,
    taskType,
    expectedOutput,
    summary: i18n.t('chat.longTaskSummary', {
      defaultValue:
        'This request is better handled as a staged document generation task to avoid chat-window truncation.',
    }),
    outline: buildOutline(taskType === 'normal_qa' ? 'document' : taskType),
    reason:
      explicitLength > 0
        ? i18n.t('chat.longTaskReasonLength', {
            defaultValue:
              'The request contains an explicit long length target.',
          })
        : i18n.t('chat.longTaskReasonType', {
            defaultValue: 'The request matches a long-form generation task.',
          }),
  };
}

export function buildLongTaskPreview(
  classification: GenerationTaskClassification,
) {
  const outline = classification.outline
    .map((item, index) => `${index + 1}. ${item}`)
    .join('\n');

  return [
    `### ${i18n.t('chat.longTaskDetectedTitle', {
      defaultValue: 'Long-form task detected',
    })}`,
    '',
    classification.summary,
    '',
    `**${i18n.t('chat.longTaskReason', {
      defaultValue: 'Reason',
    })}:** ${classification.reason}`,
    '',
    `**${i18n.t('chat.longTaskOutline', {
      defaultValue: 'Outline',
    })}:**`,
    '',
    outline,
    '',
    i18n.t('chat.longTaskButtonHint', {
      defaultValue:
        'Use the button below to generate a Markdown document by sections.',
    }),
  ].join('\n');
}

export function isAnswerTruncated(content?: string) {
  if (!content) return false;
  return [
    /The answer is truncated by your chosen LLM/i,
    /answer is truncated/i,
    /由于.*上下文.*限制/,
    /回答.*被.*截断/,
    /For the content length reason/i,
    /it stopped/i,
  ].some((pattern) => pattern.test(content));
}
