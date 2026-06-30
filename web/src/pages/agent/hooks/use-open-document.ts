import { useCallback } from 'react';

const AgentComponentsDocumentUrl: string = '';

export function useOpenDocument() {
  const openDocument = useCallback(() => {
    if (AgentComponentsDocumentUrl) {
      window.open(AgentComponentsDocumentUrl, '_blank');
    }
  }, []);

  return openDocument;
}
