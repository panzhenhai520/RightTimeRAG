const esbuild = require('esbuild');

module.exports = {
  process(sourceText, sourcePath) {
    const normalizedSource = sourceText
      .replace(/import\.meta\.env/g, 'globalThis.__JEST_IMPORT_META_ENV__')
      .replace(/import\.meta\.glob\s*\(/g, 'globalThis.__JEST_IMPORT_META_GLOB__(');
    const ext = sourcePath.split('.').pop();
    const loader =
      ext === 'tsx' ? 'tsx' : ext === 'ts' ? 'ts' : ext === 'jsx' ? 'jsx' : 'js';
    const result = esbuild.transformSync(normalizedSource, {
      loader,
      format: 'cjs',
      target: 'es2020',
      jsx: 'automatic',
      sourcemap: 'inline',
      sourcefile: sourcePath,
    });
    return { code: result.code, map: result.map };
  },
};
