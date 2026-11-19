import { useRef } from 'react';
import { AlertTriangle, CheckCircle2, FileText, Loader2, Sparkles, Trash2, Upload } from 'lucide-react';
import type { DocumentInfo } from '../api';

const ACCEPT = ['.pdf', '.docx', '.txt', '.md'];
export const MAX_MB = 15;

export function validateDocument(f: File): string | null {
  const ext = f.name.slice(f.name.lastIndexOf('.')).toLowerCase();
  if (!ACCEPT.includes(ext)) return `“${f.name}” is not supported. Use PDF, DOCX, TXT or Markdown.`;
  if (f.size === 0) return `“${f.name}” is empty.`;
  if (f.size > MAX_MB * 1024 * 1024) return `“${f.name}” is larger than ${MAX_MB} MB.`;
  return null;
}

interface Props {
  documents: DocumentInfo[];
  selected: Set<string>;
  onToggle: (id: string) => void;
  onUpload: (files: File[]) => void;
  onDelete: (doc: DocumentInfo) => void;
  onSamples: () => void;
  busy: boolean;
}

const kb = (n: number) => (n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

export default function DocumentList({ documents, selected, onToggle, onUpload, onDelete, onSamples, busy }: Props) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <section className="panel space-y-4" aria-labelledby="docs-title">
      <div className="flex items-center justify-between gap-2">
        <h2 id="docs-title" className="panel-title">Documents</h2>
        <span className="text-xs text-fog-400">{documents.length} total</span>
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-1">
        <button type="button" className="btn btn-primary" disabled={busy} onClick={() => input.current?.click()}>
          <Upload size={16} aria-hidden="true" /> Upload documents
        </button>
        <button type="button" className="btn btn-secondary" disabled={busy} onClick={onSamples}>
          <Sparkles size={16} aria-hidden="true" /> Load sample documents
        </button>
      </div>
      <input
        ref={input}
        type="file"
        multiple
        accept=".pdf,.docx,.txt,.md"
        className="sr-only"
        aria-label="Upload documents"
        onChange={(e) => {
          onUpload(Array.from(e.target.files ?? []));
          e.target.value = '';
        }}
      />
      <p className="text-xs text-fog-400">PDF, DOCX, TXT, Markdown · up to {MAX_MB} MB each. Text is extracted and indexed automatically.</p>

      {documents.length === 0 ? (
        <p className="rounded-xl border border-dashed border-ink-600 p-6 text-center text-sm text-fog-400">No documents yet.</p>
      ) : (
        <ul className="space-y-2">
          {documents.map((d) => (
            <li key={d.id} className="rounded-xl border border-ink-700 bg-ink-850/60 p-3">
              <div className="flex items-start gap-3">
                <input
                  type="checkbox"
                  className="mt-1 h-4 w-4 shrink-0 accent-[#2dd4bf]"
                  checked={selected.has(d.id)}
                  disabled={d.status !== 'ready'}
                  onChange={() => onToggle(d.id)}
                  aria-label={`Include ${d.name} in questions`}
                />
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-1.5 truncate text-sm text-fog-100">
                    <FileText size={14} className="shrink-0 text-fog-400" aria-hidden="true" />
                    <span className="truncate" title={d.name}>{d.name}</span>
                  </p>
                  <p className="mt-0.5 text-xs text-fog-400">
                    {kb(d.size)}
                    {d.pages ? ` · ${d.pages} pages` : ''}
                    {d.status === 'ready' ? ` · ${d.chunks} passages` : ''}
                  </p>
                  <p className="mt-1 flex items-center gap-1.5 text-xs" role="status">
                    {d.status === 'processing' && (<><Loader2 size={12} className="animate-spin text-amber-300" aria-hidden="true" /><span className="text-amber-300">Processing…</span></>)}
                    {d.status === 'ready' && (<><CheckCircle2 size={12} className="text-accent-400" aria-hidden="true" /><span className="text-accent-300">Ready{d.embedded ? ' · semantic + keyword' : ' · keyword only'}</span></>)}
                    {d.status === 'failed' && (<><AlertTriangle size={12} className="text-red-300" aria-hidden="true" /><span className="text-red-300">Failed</span></>)}
                  </p>
                  {(d.error || d.warning) && <p className="mt-1 text-xs text-fog-400">{d.error ?? d.warning}</p>}
                </div>
                <button type="button" className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-fog-400 hover:bg-red-400/10 hover:text-red-300" aria-label={`Remove ${d.name}`} onClick={() => onDelete(d)}>
                  <Trash2 size={15} aria-hidden="true" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
