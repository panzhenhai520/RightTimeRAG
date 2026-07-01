import '@testing-library/jest-dom';
import 'whatwg-fetch';
import { TextDecoder, TextEncoder } from 'util';
import { TransformStream } from 'stream/web';

(globalThis as any).TextEncoder ??= TextEncoder;
(globalThis as any).TextDecoder ??= TextDecoder;
(globalThis as any).TransformStream ??= TransformStream;

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: jest.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: jest.fn(),
    removeListener: jest.fn(),
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  })),
});

class ResizeObserverMock {
  observe = jest.fn();
  unobserve = jest.fn();
  disconnect = jest.fn();
}

Object.defineProperty(window, 'ResizeObserver', {
  writable: true,
  value: ResizeObserverMock,
});

Object.defineProperty(globalThis, '__JEST_IMPORT_META_ENV__', {
  writable: true,
  value: {
    MODE: 'test',
    DEV: false,
    PROD: false,
    SSR: false,
    VITE_DEFAULT_LANGUAGE_CODE: 'en',
  },
});

Object.defineProperty(globalThis, '__JEST_IMPORT_META_GLOB__', {
  writable: true,
  value: jest.fn(() => ({})),
});
