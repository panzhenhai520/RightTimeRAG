export default {
  testEnvironment: 'jsdom',
  setupFilesAfterEnv: ['<rootDir>/jest-setup.ts'],
  transform: {
    '^.+\\.(ts|tsx|js|jsx)$': '<rootDir>/jest-esbuild-transform.cjs',
  },
  moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx', 'json'],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
    '^@parent/(.*)$': '<rootDir>/../src/$1',
    '\\.(css|less|scss|sass)$': '<rootDir>/jest-style-mock.cjs',
    '\\.(svg|png|jpg|jpeg|gif|webp|avif|ico|woff|woff2|ttf|eot)$':
      '<rootDir>/jest-file-mock.cjs',
  },
  testPathIgnorePatterns: ['/node_modules/', '/dist/'],
};
