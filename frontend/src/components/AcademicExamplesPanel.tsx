import { useEffect, useRef, useState } from 'react';
import { BookOpen, Copy, Loader2, Search, ShieldCheck } from 'lucide-react';
import { useAPI, AcademicRevisionExample } from '../contexts/APIContext';

interface AcademicExamplesPanelProps {
  initialQuery: string;
}

export default function AcademicExamplesPanel({ initialQuery }: AcademicExamplesPanelProps) {
  const { getAcademicExamples } = useAPI();
  const [query, setQuery] = useState(initialQuery);
  const [examples, setExamples] = useState<AcademicRevisionExample[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const activeRequest = useRef(0);

  useEffect(() => {
    // Invalidate any in-flight search when the workspace switches paragraphs.
    activeRequest.current += 1;
    setQuery(initialQuery);
    setExamples([]);
    setSearched(false);
    setLoading(false);
    setError(null);
    setCopiedId(null);
  }, [initialQuery]);

  const searchExamples = async () => {
    const cleanQuery = query.trim();
    if (cleanQuery.length < 2) {
      setError('Enter at least two characters to search academic examples.');
      return;
    }
    const requestId = ++activeRequest.current;
    setLoading(true);
    setError(null);
    setExamples([]);
    setSearched(true);
    try {
      const response = await getAcademicExamples(cleanQuery, { limit: 5 });
      // Ignore stale responses if a newer search or paragraph change occurred.
      if (requestId !== activeRequest.current) return;
      if (!response) {
        setExamples([]);
        setError('Academic examples could not be loaded. Check the backend connection and try again.');
      } else {
        setExamples(response.examples);
      }
    } catch {
      if (requestId === activeRequest.current) {
        setExamples([]);
        setError('Academic examples could not be loaded. Check the backend connection and try again.');
      }
    } finally {
      if (requestId === activeRequest.current) setLoading(false);
    }
  };

  const copyExample = async (example: AcademicRevisionExample) => {
    try {
      await navigator.clipboard.writeText(example.edited_text);
      setCopiedId(example.pair_id);
    } catch {
      setError('Clipboard access was blocked. Select the revised text and copy it manually.');
    }
  };

  return (
    <section className="card space-y-4" aria-labelledby="academic-examples-title">
      <div className="flex items-start gap-3">
        <div className="rounded-lg bg-primary-50 p-2 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300">
          <BookOpen size={20} />
        </div>
        <div className="min-w-0 flex-1">
          <h2 id="academic-examples-title" className="font-semibold">Academic writing examples</h2>
          <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
            Find reviewed examples similar to your paragraph. Examples are references only and never change your document.
          </p>
        </div>
      </div>

      <form
        className="flex flex-col gap-2 sm:flex-row"
        onSubmit={(event) => {
          event.preventDefault();
          void searchExamples();
        }}
      >
        <label className="sr-only" htmlFor="academic-example-query">Search academic examples</label>
        <input
          id="academic-example-query"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search by paragraph, topic, or writing issue…"
          className="min-w-0 flex-1 rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-200 dark:border-neutral-600 dark:bg-neutral-900 dark:text-neutral-100"
        />
        <button type="submit" disabled={loading || query.trim().length < 2} className="btn-primary inline-flex items-center justify-center gap-2">
          {loading ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
          {loading ? 'Searching…' : 'Find examples'}
        </button>
      </form>

      {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      {searched && !loading && !error && examples.length === 0 && (
        <div className="rounded-lg border border-dashed border-neutral-300 p-5 text-center dark:border-neutral-700">
          <BookOpen className="mx-auto mb-2 text-neutral-400" size={22} />
          <p className="text-sm font-medium text-neutral-700 dark:text-neutral-200">No approved examples found yet</p>
          <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
            The local corpus may be empty, or no reviewed example matches this search. Pending ARIES reconstructions are intentionally hidden.
          </p>
        </div>
      )}

      {!searched && (
        <p className="text-xs text-neutral-500 dark:text-neutral-400">
          Search uses the local BM25 index. Only human-approved, meaning-preserved and licence-eligible examples can appear.
        </p>
      )}

      {examples.map((example) => (
        <article key={example.pair_id} className="space-y-3 rounded-lg border border-neutral-200 p-4 dark:border-neutral-700">
          <div className="flex flex-wrap items-center gap-2 text-xs text-neutral-500">
            <span className="rounded-full bg-neutral-100 px-2 py-1 capitalize dark:bg-neutral-700">{example.discipline}</span>
            <span className="capitalize">{example.section.replace(/_/g, ' ')}</span>
            {example.edit_types.map((type) => (
              <span key={type} className="rounded-full bg-primary-50 px-2 py-1 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300">{type}</span>
            ))}
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-lg bg-neutral-50 p-3 dark:bg-neutral-900/50">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-neutral-500">Original</p>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-neutral-700 dark:text-neutral-300">{example.original_text}</p>
            </div>
            <div className="rounded-lg bg-primary-50/60 p-3 dark:bg-primary-900/10">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-primary-700 dark:text-primary-300">Reviewed revision</p>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-neutral-800 dark:text-neutral-200">{example.edited_text}</p>
            </div>
          </div>
          <p className="text-sm text-neutral-600 dark:text-neutral-400"><span className="font-medium text-neutral-800 dark:text-neutral-200">Why it changed: </span>{example.rationale}</p>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-neutral-100 pt-3 dark:border-neutral-700">
            <div className="flex min-w-0 items-center gap-2 text-xs text-neutral-500">
              <ShieldCheck size={14} className="shrink-0 text-green-600" />
              <span className="truncate">{example.provenance.attribution || example.provenance.reference}</span>
              {example.provenance.license && <span>· {example.provenance.license}</span>}
              {example.provenance.url && (
                <a href={example.provenance.url} target="_blank" rel="noreferrer" className="text-primary-600 underline dark:text-primary-400">Source</a>
              )}
            </div>
            <button type="button" onClick={() => void copyExample(example)} className="btn-secondary inline-flex items-center gap-2 text-xs">
              <Copy size={14} /> {copiedId === example.pair_id ? 'Copied' : 'Copy revision'}
            </button>
          </div>
          <p className="text-xs text-neutral-500 dark:text-neutral-400">Reference only — review the wording and meaning before using it.</p>
        </article>
      ))}
    </section>
  );
}
