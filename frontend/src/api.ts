export interface DocumentInfo {
  id: string;
  name: string;
  ext: string;
  size: number;
  status: 'processing' | 'ready' | 'failed';
  error: string | null;
  warning: string | null;
  pages: number | null;
  chunks: number;
  embedded: number;
  created_at: number;
}

export interface Source {
  n: number;
  document_id: string;
  document: string;
  page: number | null;
  chunk: number;
  excerpt: string;
  text: string;
  semantic_score: number | null;
  keyword_score: number;
  matched_terms: string[];
}

export interface AskResult {
  question: string;
  retrieval: 'hybrid' | 'keyword';
  found: boolean;
  sources: Source[];
  answer: string | null;
  answer_mode?: 'llm' | 'search_only';
  message?: string;
  model?: string;
}

export interface Health {
  documents: number;
  embeddings: { enabled: boolean; model: string; loaded: boolean; error: string | null };
  llm: { enabled: boolean; model?: string; message?: string };
}

const BASE = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '');

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, init);
  } catch {
    throw new Error('Cannot reach the document server. Is the backend running on port 8104?');
  }
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === 'string') msg = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const getHealth = () => call<Health>('/api/health');
export const listDocuments = () => call<DocumentInfo[]>('/api/documents');
export const deleteDocument = (id: string) => call<void>(`/api/documents/${id}`, { method: 'DELETE' });
export const loadSamples = () => call<DocumentInfo[]>('/api/documents/samples', { method: 'POST' });

export function uploadDocument(file: File) {
  const f = new FormData();
  f.append('file', file);
  return call<DocumentInfo>('/api/documents', { method: 'POST', body: f });
}

export const ask = (question: string, documentIds: string[] | null) =>
  call<AskResult>('/api/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, document_ids: documentIds }),
  });
