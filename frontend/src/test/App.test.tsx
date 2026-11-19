import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, vi } from 'vitest';
import App from '../App';
import { validateDocument } from '../components/DocumentList';
import type { AskResult, DocumentInfo } from '../api';

const doc = (over: Partial<DocumentInfo> = {}): DocumentInfo => ({
  id: 'd1', name: 'handbook.pdf', ext: '.pdf', size: 2048, status: 'ready', error: null, warning: null, pages: 3, chunks: 4, embedded: 1, created_at: 1, ...over,
});

const searchOnly: AskResult = {
  question: 'sick leave?',
  retrieval: 'hybrid',
  found: true,
  answer: null,
  answer_mode: 'search_only',
  message: 'No language model is configured, so conversational answers are unavailable. Document search still works.',
  sources: [{ n: 1, document_id: 'd1', document: 'handbook.pdf', page: 2, chunk: 1, excerpt: 'Employees receive 12 days of paid sick leave', text: 'Employees receive 12 days of paid sick leave per year.', semantic_score: 0.81, keyword_score: 1, matched_terms: ['sick', 'leave'] }],
};

let docs: DocumentInfo[];
let askResult: AskResult;
const calls: { url: string; method?: string; body?: string }[] = [];

beforeEach(() => {
  docs = [doc()];
  askResult = searchOnly;
  calls.length = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, method: init?.method, body: typeof init?.body === 'string' ? init.body : undefined });
      if (url.endsWith('/api/health')) return Response.json({ documents: 1, embeddings: { enabled: true, model: 'BAAI/bge-small-en-v1.5', loaded: true, error: null }, llm: { enabled: false, message: 'No language model is configured.' } });
      if (url.endsWith('/api/documents') && init?.method === 'POST') return Response.json(doc({ id: 'd2', name: 'new.txt', status: 'processing' }), { status: 202 });
      if (url.endsWith('/api/documents')) return Response.json(docs);
      if (url.includes('/api/documents/') && init?.method === 'DELETE') { docs = []; return new Response(null, { status: 204 }); }
      if (url.endsWith('/api/ask')) return Response.json(askResult);
      return new Response('{}', { status: 404 });
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

it('validates documents', () => {
  expect(validateDocument(new File(['x'], 'a.png'))).toMatch(/not supported/);
  expect(validateDocument(new File([], 'a.txt'))).toMatch(/empty/);
  expect(validateDocument(new File(['x'], 'notes.MD'))).toBeNull();
});

it('shows retrieved passages with page citations and is honest about missing LLM', async () => {
  const user = userEvent.setup();
  render(<App />);
  expect(await screen.findByText('handbook.pdf')).toBeInTheDocument();
  expect(await screen.findByText(/semantic \(BAAI\/bge-small-en-v1.5, runs locally\)/)).toBeInTheDocument();

  await user.type(screen.getByLabelText('Question'), 'How many sick days?');
  await user.click(screen.getByRole('button', { name: 'Ask' }));

  const sources = await screen.findByRole('list', { name: 'Sources' });
  expect(within(sources).getByText('· page 2')).toBeInTheDocument();
  expect(within(sources).getByText(/12 days of paid sick leave$/)).toBeInTheDocument();
  expect(screen.getByText(/conversational answers are unavailable/)).toBeInTheDocument();
  expect(JSON.parse(calls.find((c) => c.url.endsWith('/api/ask'))!.body!)).toEqual({ question: 'How many sick days?', document_ids: null });
});

it('shows the not-found message', async () => {
  askResult = { ...searchOnly, found: false, sources: [], message: "I couldn't find this in your documents." };
  const user = userEvent.setup();
  render(<App />);
  await screen.findByText('handbook.pdf');
  await user.type(screen.getByLabelText('Question'), 'Mars weather?');
  await user.click(screen.getByRole('button', { name: 'Ask' }));
  expect(await screen.findByText(/couldn't find this in your documents/)).toBeInTheDocument();
});

it('scopes questions to selected documents and removes documents', async () => {
  docs = [doc(), doc({ id: 'd2', name: 'faq.txt', ext: '.txt', pages: null })];
  const user = userEvent.setup();
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  render(<App />);
  await screen.findByText('faq.txt');
  await waitFor(() => expect(screen.getByLabelText('Include faq.txt in questions')).toBeChecked());
  await user.click(screen.getByLabelText('Include faq.txt in questions'));
  await user.type(screen.getByLabelText('Question'), 'leave policy');
  await user.click(screen.getByRole('button', { name: 'Ask' }));
  await screen.findByRole('list', { name: 'Sources' });
  expect(JSON.parse(calls.find((c) => c.url.endsWith('/api/ask'))!.body!).document_ids).toEqual(['d1']);

  await user.click(screen.getByRole('button', { name: 'Remove handbook.pdf' }));
  const list = screen.getByRole('region', { name: 'Documents' });
  await waitFor(() => expect(within(list).queryByText('handbook.pdf')).not.toBeInTheDocument());
});

it('rejects unsupported uploads before sending', async () => {
  const user = userEvent.setup({ applyAccept: false });
  render(<App />);
  await screen.findByText('handbook.pdf');
  await user.upload(screen.getByLabelText('Upload documents'), new File(['x'], 'photo.png', { type: 'image/png' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(/not supported/);
  expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/api/documents'))).toBe(false);
});
