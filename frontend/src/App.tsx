import { useCallback, useEffect, useRef, useState } from 'react';
import { Cpu, FileQuestion, X } from 'lucide-react';
import { deleteDocument, getHealth, listDocuments, loadSamples, uploadDocument, type DocumentInfo, type Health } from './api';
import DocumentList, { validateDocument } from './components/DocumentList';
import Chat from './components/Chat';

export default function App() {
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const seen = useRef<Set<string>>(new Set());

  const refresh = useCallback(async () => {
    try {
      const list = await listDocuments();
      setDocs(list);
      const ready = list.filter((d) => d.status === 'ready').map((d) => d.id);
      const fresh = ready.filter((id) => !seen.current.has(id));
      fresh.forEach((id) => seen.current.add(id));
      // Newly ready documents are included by default; removed ones drop out.
      setSelected((prev) => new Set([...[...prev].filter((id) => ready.includes(id)), ...fresh]));
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    refresh();
    getHealth().then(setHealth).catch(() => setHealth(null));
  }, [refresh]);

  const processing = docs.some((d) => d.status === 'processing');
  useEffect(() => {
    if (!processing) return;
    const t = setInterval(refresh, 1500);
    return () => clearInterval(t);
  }, [processing, refresh]);

  const run = async (task: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await task();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      refresh();
    }
  };

  const onUpload = (files: File[]) => {
    const problems = files.map(validateDocument).filter(Boolean) as string[];
    const ok = files.filter((f) => !validateDocument(f));
    if (problems.length) setError(problems.join(' '));
    if (ok.length) run(async () => { for (const f of ok) await uploadDocument(f); });
  };

  const onDelete = (d: DocumentInfo) => {
    if (!window.confirm(`Remove “${d.name}” and its index entries?`)) return;
    run(() => deleteDocument(d.id));
  };

  const readyIds = docs.filter((d) => d.status === 'ready').map((d) => d.id);
  const chosen = readyIds.filter((id) => selected.has(id));
  const scope = chosen.length === readyIds.length ? null : chosen;

  return (
    <div className="min-h-screen">
      <header className="border-b border-ink-700/80">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-4 sm:px-6">
          <FileQuestion className="shrink-0 text-accent-400" size={24} aria-hidden="true" />
          <div className="min-w-0">
            <h1 className="truncate text-base font-semibold text-fog-100 sm:text-lg">AI Document Assistant</h1>
            <p className="truncate text-xs text-fog-400">Retrieval over your own documents · local embeddings · cited sources</p>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-4 px-4 py-6 sm:px-6">
        {health && (
          <div className="flex items-start gap-3 rounded-xl border border-ink-700 bg-ink-900/60 p-3 text-xs text-fog-300">
            <Cpu size={16} className="mt-0.5 shrink-0 text-accent-400" aria-hidden="true" />
            <div className="space-y-1">
              <p>
                <strong className="font-medium text-fog-100">Search:</strong>{' '}
                {health.embeddings.enabled ? `semantic (${health.embeddings.model}, runs locally) + keyword` : 'keyword only (semantic search disabled)'}
                {health.embeddings.error && <span className="text-amber-300"> · {health.embeddings.error}</span>}
              </p>
              <p>
                <strong className="font-medium text-fog-100">Answers:</strong>{' '}
                {health.llm.enabled ? `local LLM (${health.llm.model}) via Ollama` : health.llm.message}
              </p>
            </div>
          </div>
        )}

        {error && (
          <div role="alert" className="flex items-start justify-between gap-3 rounded-xl border border-red-400/30 bg-red-400/10 p-3 text-sm text-red-200">
            <span>{error}</span>
            <button type="button" aria-label="Dismiss error" onClick={() => setError(null)}><X size={16} aria-hidden="true" /></button>
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[22rem_minmax(0,1fr)]">
          <DocumentList
            documents={docs}
            selected={selected}
            busy={busy}
            onToggle={(id) => setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; })}
            onUpload={onUpload}
            onDelete={onDelete}
            onSamples={() => run(loadSamples)}
          />
          <Chat documentIds={scope} disabled={chosen.length === 0} />
        </div>
      </main>
    </div>
  );
}
