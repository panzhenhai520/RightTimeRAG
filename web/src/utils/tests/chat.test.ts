import {
  mergeFinalAnswerWithProcess,
  mergeStreamingAnswerChunk,
  preprocessLaTeX,
} from '../chat';

test('handles double-escaped inline LaTeX', () => {
  const result = preprocessLaTeX('\\\\(\\\\Delta = b^2\\\\)');
  expect(result).toBe('$\\Delta = b^2$');
});

test('handles double-escaped block LaTeX', () => {
  const result = preprocessLaTeX('\\\\[E = mc^2\\\\]');
  expect(result).toBe('$$E = mc^2$$');
});

test('decodes HTML entities', () => {
  const result = preprocessLaTeX('a &lt; b &amp; c &gt; d');
  expect(result).toBe('a < b & c > d');
});

test('handles mixed double-escaped delimiters with HTML entities', () => {
  const result = preprocessLaTeX('\\\\(x &lt; y\\\\)');
  expect(result).toBe('$x < y$');
});

test('passes through already correct single-escaped delimiters unchanged', () => {
  const result = preprocessLaTeX('\\(x = 1\\)');
  expect(result).toBe('$x = 1$');
});

test('preserves retrieval and thinking blocks when merging final answer', () => {
  const previous =
    '<retrieving>Searching datasets\n</retrieving><think>Reviewing evidence\n</think>**Answer** body';
  const final = '**Answer** body [ID:0]';

  const result = mergeFinalAnswerWithProcess(previous, final);

  expect(result).toContain('<retrieving>Searching datasets\n</retrieving>');
  expect(result).toContain('<think>Reviewing evidence\n</think>');
  expect(result).toContain('**Answer** body [ID:0]');
});

test('deduplicates repeated process open tags before final merge', () => {
  const previous =
    '<retrieving><retrieving>Searching datasets\n</retrieving><think>Reviewing evidence\n</think>Streamed answer';
  const final = 'Final answer [ID:0]';

  const result = mergeFinalAnswerWithProcess(previous, final);

  expect(result).toBe(
    '<retrieving>Searching datasets</retrieving><think>Reviewing evidence</think>Final answer [ID:0]',
  );
  expect(result.match(/<retrieving>/g)).toHaveLength(1);
});

test('ignores duplicate process open tags while streaming', () => {
  const result = mergeStreamingAnswerChunk('<retrieving>', '<retrieving>');

  expect(result).toBe('<retrieving>');
});

test('continues streaming content after a process block is open', () => {
  const result = mergeStreamingAnswerChunk(
    '<retrieving>',
    'Searching datasets\n',
  );

  expect(result).toBe('<retrieving>Searching datasets\n');
});

test('keeps final answer when it adds citation markers', () => {
  const previous =
    '<retrieving>Searching datasets\n</retrieving><think>Reviewing evidence\n</think>Table answer';
  const final = 'Table answer [ID:2]';

  const result = mergeFinalAnswerWithProcess(previous, final);

  expect(result).toContain('Table answer [ID:2]');
});

test('keeps streamed answer when final answer is unexpectedly shorter without new citations', () => {
  const previous =
    '<retrieving>Searching datasets\n</retrieving><think>Reviewing evidence\n</think>## Title\n\nA complete streamed answer with formatting.';
  const final = 'A short answer.';

  const result = mergeFinalAnswerWithProcess(previous, final);

  expect(result).toContain(
    '## Title\n\nA complete streamed answer with formatting.',
  );
  expect(result).not.toContain('A short answer.');
});
