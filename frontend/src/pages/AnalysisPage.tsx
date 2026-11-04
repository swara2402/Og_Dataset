import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowUpRight,
  BarChart3,
  BookOpen,
  CheckCircle,
  Clock,
  Copy,
  Download,
  FileText,
  Loader2,
  Search,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  XCircle,
} from 'lucide-react';
import {
  AnalysisReport,
  JobSummary,
  OriginalityReport,
  QualityMetrics,
  useAPI,
} from '../contexts/APIContext';

const QUALITY_ROWS: { key: keyof QualityMetrics; label: string; suffix?: string }[] = [
  { key: 'overall_score', label: 'Overall quality' },
  { key: 'readability_score', label: 'Readability' },
  { key: 'flesch_reading_ease', label: 'Flesch reading ease' },
  { key: 'sentence_variety', label: 'Sentence variety' },
  { key: 'vocabulary_diversity', label: 'Vocabulary diversity' },
  { key: 'repetition_score', label: 'Repetition score' },
  { key: 'transition_usage', label: 'Transition usage' },
  { key: 'formality', label: 'Formality' },
  { key: 'clarity', label: 'Clarity' },
  { key: 'coherence', label: 'Coherence' },
  { key: 'verbosity', label: 'Concision' },
  { key: 'terminology_consistency', label: 'Terminology consistency' },
];

function scoreColor(score: number) {
  if (score >= 80) return 'text-green-600 dark:text-green-400';
  if (score >= 60) return 'text-yellow-600 dark:text-yellow-400';
  return 'text-red-600 dark:text-red-400';
}

function barColor(score: number) {
  if (score >= 80) return 'bg-green-500';
  if (score >= 60) return 'bg-yellow-500';
  return 'bg-red-500';
}

function formatDelta(value: number | undefined) {
  if (value === undefined || Number.isNaN(value)) return '—';
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}`;
}

export default function AnalysisPage() {
  const { jobId } = useParams<{ jobId?: string }>();
  const navigate = useNavigate();
  const { listJobs, getAnalysisReport, runOriginality, errorMessage } = useAPI();

  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [analysis, setAnalysis] = useState<AnalysisReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'originality' | 'recommendations'>('overview');
  const [copied, setCopied] = useState(false);
  const [searchConfirmed, setSearchConfirmed] = useState(false);
  const [maxSentences, setMaxSentences] = useState(6);
  const [searching, setSearching] = useState(false);

  const load = useCallback(
    async (targetId: string) => {
      const report = await getAnalysisReport(targetId);
      if (!report) {
        setError('Could not load this analysis report.');
        setAnalysis(null);
        return;
      }
      setError(null);
      setAnalysis(report);
    },
    [getAnalysisReport]
  );

  useEffect(() => {
    let active = true;
    const run = async () => {
      setLoading(true);
      setError(null);
      const all = await listJobs();
      const completed = all.filter((job) => job.status === 'completed');
      if (!active) return;
      setJobs(completed);
      const target = jobId || completed[0]?.job_id;
      if (target) {
        await load(target);
      } else {
        setAnalysis(null);
      }
      if (active) setLoading(false);
    };
    void run();
    return () => {
      active = false;
    };
  }, [jobId, listJobs, load]);

  const handleCopy = async () => {
    if (!analysis) return;
    await navigator.clipboard.writeText(JSON.stringify(analysis, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    if (!analysis) return;
    const blob = new Blob([JSON.stringify(analysis, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${analysis.filename.replace(/\.[^/.]+$/, '')}_analysis.json`;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  };

  const handleOriginality = async () => {
    if (!analysis || !searchConfirmed) return;
    setSearching(true);
    setError(null);
    try {
      const report: OriginalityReport | null = await runOriginality({
        jobId: analysis.job_id,
        maxSentences,
        fetchPages: true,
      });
      if (!report) {
        setError('Originality search failed. Check your network connection and try again.');
        return;
      }
      setAnalysis((current) => (current ? { ...current, originality: report } : current));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setSearching(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="animate-spin text-primary-500" size={32} />
      </div>
    );
  }

  if (!analysis) {
    return (
      <div className="mx-auto max-w-5xl">
        <div className="mb-8">
          <h1 className="mb-2 text-3xl font-bold">Analysis</h1>
          <p className="text-neutral-600 dark:text-neutral-400">Writing quality, protected-content validation and originality reports.</p>
        </div>
        {error && <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">{error}</div>}
        <div className="card flex flex-col items-center py-16 text-center">
          <Search className="mb-4 opacity-40" size={48} />
          <h2 className="mb-2 text-xl font-semibold">No completed analyses yet</h2>
          <p className="mb-6 max-w-md text-neutral-500 dark:text-neutral-400">
            Process a document in the workspace. The analysis is generated from the actual revised text, not a placeholder score.
          </p>
          <button onClick={() => navigate('/document')} className="btn-primary">Open Document Workspace</button>
        </div>
      </div>
    );
  }

  const { writing_quality, ai_indicators, validation, originality, statistics } = analysis;
  const revisedMetrics = writing_quality.revised;

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="mb-2 text-3xl font-bold">Analysis</h1>
          <p className="text-neutral-600 dark:text-neutral-400">
            {analysis.filename} · {analysis.style} style · report generated from revised text
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={handleCopy} className="btn-secondary inline-flex items-center gap-2">
            {copied ? <CheckCircle size={16} /> : <Copy size={16} />} {copied ? 'Copied' : 'Copy JSON'}
          </button>
          <button onClick={handleDownload} className="btn-secondary inline-flex items-center gap-2">
            <Download size={16} /> Report JSON
          </button>
          <button onClick={() => navigate(`/document/${analysis.job_id}`)} className="btn-primary inline-flex items-center gap-2">
            <FileText size={16} /> Open document
          </button>
        </div>
      </div>

      {error && <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">{error}</div>}

      <div className="grid gap-6 lg:grid-cols-4">
        <aside className="lg:col-span-1">
          <div className="card p-4">
            <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
              <Clock size={16} /> Completed jobs
            </h2>
            <div className="space-y-2">
              {jobs.map((job) => (
                <button
                  key={job.job_id}
                  onClick={() => navigate(`/analysis/${job.job_id}`)}
                  className={`w-full rounded-lg border p-3 text-left transition-colors ${
                    job.job_id === analysis.job_id
                      ? 'border-primary-400 bg-primary-50 dark:border-primary-600 dark:bg-primary-900/20'
                      : 'border-neutral-200 hover:bg-neutral-50 dark:border-neutral-700 dark:hover:bg-neutral-700/40'
                  }`}
                >
                  <p className="truncate text-sm font-medium">{job.filename}</p>
                  <p className="mt-1 text-xs text-neutral-500">{job.style} · {new Date(job.created_at).toLocaleDateString()}</p>
                </button>
              ))}
            </div>
          </div>
        </aside>

        <div className="space-y-6 lg:col-span-3">
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <div className="card">
              <div className="mb-2 flex items-center gap-2 text-sm text-neutral-500"><Sparkles size={16} /> Quality</div>
              <p className={`text-2xl font-bold ${scoreColor(revisedMetrics.overall_score)}`}>{revisedMetrics.overall_score.toFixed(1)}</p>
              <p className="text-xs text-neutral-500">{formatDelta(writing_quality.deltas.overall_score)} vs original</p>
            </div>
            <div className="card">
              <div className="mb-2 flex items-center gap-2 text-sm text-neutral-500"><TrendingUp size={16} /> Readability</div>
              <p className={`text-2xl font-bold ${scoreColor(revisedMetrics.readability_score)}`}>{revisedMetrics.readability_score.toFixed(1)}</p>
              <p className="text-xs text-neutral-500">{formatDelta(writing_quality.deltas.readability_score)} vs original</p>
            </div>
            <div className="card">
              <div className="mb-2 flex items-center gap-2 text-sm text-neutral-500"><ShieldCheck size={16} /> Protected</div>
              <p className="text-2xl font-bold">{validation.checked_paragraphs}</p>
              <p className="text-xs text-neutral-500">paragraphs checked</p>
            </div>
            <div className="card">
              <div className="mb-2 flex items-center gap-2 text-sm text-neutral-500"><BarChart3 size={16} /> AI detection</div>
              <p className="text-2xl font-bold">Not connected</p>
              <p className="text-xs text-neutral-500">No authorship verdict is generated</p>
            </div>
          </div>

          <div className="overflow-hidden rounded-xl border border-neutral-200 bg-white dark:border-neutral-700 dark:bg-neutral-800">
            <div className="flex border-b border-neutral-200 dark:border-neutral-700">
              {(['overview', 'originality', 'recommendations'] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`px-5 py-3 text-sm font-medium capitalize ${
                    activeTab === tab
                      ? 'border-b-2 border-primary-500 text-primary-600 dark:text-primary-400'
                      : 'text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200'
                  }`}
                >
                  {tab}
                </button>
              ))}
            </div>

            <div className="space-y-6 p-6">
              {activeTab === 'overview' && (
                <>
                  <section>
                    <h2 className="mb-1 text-lg font-semibold">Writing quality</h2>
                    <p className="mb-4 text-sm text-neutral-500 dark:text-neutral-400">
                      Original vs revised. Deltas are shown only where a real before/after measurement exists.
                    </p>
                    <div className="grid gap-x-8 gap-y-4 md:grid-cols-2">
                      {QUALITY_ROWS.map((row) => {
                        const revised = Number(revisedMetrics[row.key] ?? 0);
                        const original = Number(writing_quality.original[row.key] ?? 0);
                        const clamped = Math.max(0, Math.min(100, revised));
                        return (
                          <div key={row.key}>
                            <div className="mb-1 flex items-center justify-between text-sm">
                              <span className="text-neutral-600 dark:text-neutral-400">{row.label}</span>
                              <span className={scoreColor(clamped)}>{revised.toFixed(1)} <span className="text-xs text-neutral-400">(orig {original.toFixed(1)})</span></span>
                            </div>
                            <div className="h-2 overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-700">
                              <div className={`h-full rounded-full ${barColor(clamped)}`} style={{ width: `${clamped}%` }} />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </section>

                  <section className="grid gap-4 md:grid-cols-2">
                    <div className="rounded-lg border border-neutral-200 p-4 dark:border-neutral-700">
                      <h3 className="mb-3 font-semibold">Protected-content validation</h3>
                      <ul className="space-y-2 text-sm">
                        <li className="flex items-center justify-between"><span>Protected content</span>{validation.protected_content_preserved ? <CheckCircle className="text-green-500" size={16} /> : <XCircle className="text-red-500" size={16} />}</li>
                        <li className="flex items-center justify-between"><span>Numbers</span>{validation.numbers_preserved ? <CheckCircle className="text-green-500" size={16} /> : <XCircle className="text-red-500" size={16} />}</li>
                        <li className="flex items-center justify-between"><span>Citations</span>{validation.citations_preserved ? <CheckCircle className="text-green-500" size={16} /> : <XCircle className="text-red-500" size={16} />}</li>
                        <li className="flex items-center justify-between"><span>Critical issues</span><span className={validation.critical_issues.length ? 'text-red-500' : 'text-green-500'}>{validation.critical_issues.length}</span></li>
                        <li className="flex items-center justify-between"><span>Warnings</span><span className={validation.warnings.length ? 'text-yellow-500' : 'text-green-500'}>{validation.warnings.length}</span></li>
                      </ul>
                    </div>

                    <div className="rounded-lg border border-neutral-200 p-4 dark:border-neutral-700">
                      <h3 className="mb-2 font-semibold">Style observations (not AI detection)</h3>
                      <p className="mb-3 text-sm text-neutral-500 dark:text-neutral-400">{ai_indicators.detector_note}</p>
                      <p className="mb-3 text-sm text-neutral-600 dark:text-neutral-300">
                        These observations point to wording or structure that an author may want to review. They do not identify who wrote the text.
                      </p>
                      <div className="space-y-3">
                        {ai_indicators.indicators.filter((indicator) => indicator.evidence.length > 0).slice(0, 6).map((indicator) => (
                          <div key={indicator.id} className="border-b border-neutral-100 pb-2 last:border-0 last:pb-0 dark:border-neutral-700">
                            <p className="text-sm font-medium text-neutral-700 dark:text-neutral-200">{indicator.label}</p>
                            <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">{indicator.description}</p>
                            <p className="mt-1 text-xs text-neutral-500">Observed: {indicator.evidence.join(', ')}</p>
                          </div>
                        ))}
                        {ai_indicators.indicators.every((indicator) => indicator.evidence.length === 0) && (
                          <p className="text-sm text-neutral-500">No style observations to display.</p>
                        )}
                      </div>
                    </div>
                  </section>

                  <section className="rounded-lg bg-neutral-50 p-4 text-sm dark:bg-neutral-900/40">
                    <p className="font-medium">Processing record</p>
                    <p className="text-neutral-500 dark:text-neutral-400">
                      Rule-based engine: {String(statistics.applied_rule_count || '0')} rules applied · Passes: {String(statistics.passes || analysis.statistics.total_passes || '—')} ·
                      {' '}Cache hits: {String(statistics.cache_hits || 0)}
                    </p>
                    <p className="mt-2 text-xs text-neutral-500">{analysis.disclaimer}</p>
                  </section>
                </>
              )}

              {activeTab === 'originality' && (
                <>
                  {!originality && (
                    <section className="rounded-xl border border-blue-200 bg-blue-50 p-5 dark:border-blue-800 dark:bg-blue-900/20">
                      <h2 className="mb-2 flex items-center gap-2 text-lg font-semibold"><Search size={20} /> Originality check</h2>
                      <p className="mb-3 text-sm text-neutral-700 dark:text-neutral-300">
                        This check sends only short sentence queries to a public web search provider. It never uploads the document.
                        Results are candidate matches for manual review, not a definitive plagiarism percentage.
                      </p>
                      <ul className="mb-4 space-y-1 text-sm text-neutral-600 dark:text-neutral-400">
                        <li>• Search provider: DuckDuckGo HTML endpoint</li>
                        <li>• Queries per check: up to {Math.min(maxSentences, 6)} sentences (server limit)</li>
                        <li>• Coverage is limited to publicly indexed search results</li>
                      </ul>
                      <label className="mb-4 flex items-start gap-2 text-sm">
                        <input type="checkbox" checked={searchConfirmed} onChange={(event) => setSearchConfirmed(event.target.checked)} className="mt-1" />
                        <span>I understand and want to send selected sentences to the public search provider.</span>
                      </label>
                      <div className="flex flex-wrap items-center gap-4">
                        <div className="flex items-center gap-3">
                          <span className="text-sm text-neutral-500">Sentences</span>
                          <input type="range" min={3} max={6} value={maxSentences} onChange={(event) => setMaxSentences(Number(event.target.value))} className="accent-primary-600" />
                          <span className="w-6 text-sm">{maxSentences}</span>
                        </div>
                        <button onClick={handleOriginality} disabled={!searchConfirmed || searching} className="btn-primary inline-flex items-center gap-2">
                          {searching ? <Loader2 className="animate-spin" size={16} /> : <Search size={16} />}
                          {searching ? 'Searching...' : 'Run originality check'}
                        </button>
                      </div>
                    </section>
                  )}

                  {originality && (
                    <>
                      <div className="rounded-lg border border-neutral-200 p-4 text-sm dark:border-neutral-700">
                        <h3 className="mb-2 flex items-center gap-2 font-semibold"><ShieldCheck size={18} /> {originality.provider}</h3>
                        <p className="mb-2 text-neutral-600 dark:text-neutral-400">{originality.summary}</p>
                        <p className="text-neutral-500 dark:text-neutral-400">{originality.disclosure}</p>
                        <p className="mt-2 text-xs text-neutral-500">{originality.scope}</p>
                      </div>

                      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                        <div className="rounded-lg border border-neutral-200 p-4 dark:border-neutral-700"><p className="text-xs text-neutral-500">Sentences searched</p><p className="text-xl font-bold">{originality.sentences_searched}</p></div>
                        <div className="rounded-lg border border-neutral-200 p-4 dark:border-neutral-700"><p className="text-xs text-neutral-500">Matched sources</p><p className="text-xl font-bold">{originality.statistics.matched_sources}</p></div>
                        <div className="rounded-lg border border-neutral-200 p-4 dark:border-neutral-700"><p className="text-xs text-neutral-500">Needs review</p><p className="text-xl font-bold text-yellow-600 dark:text-yellow-400">{originality.statistics.needs_manual_review}</p></div>
                        <div className="rounded-lg border border-neutral-200 p-4 dark:border-neutral-700"><p className="text-xs text-neutral-500">Uncited quotations</p><p className="text-xl font-bold text-red-600 dark:text-red-400">{originality.statistics.uncited_quotations}</p></div>
                      </div>

                      <section>
                        <h3 className="mb-3 font-semibold">Candidate matches</h3>
                        {originality.matches.length === 0 && (
                          <p className="rounded-lg bg-green-50 p-4 text-sm text-green-700 dark:bg-green-900/20 dark:text-green-300">
                            No candidate matches above the comparison threshold. This only covers the sentences searched and the public results returned.
                          </p>
                        )}
                        <div className="space-y-3">
                          {originality.matches.map((match) => (
                            <div key={match.id} className="rounded-lg border border-neutral-200 p-4 dark:border-neutral-700">
                              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                                <div className="flex items-center gap-2">
                                  <BookOpen size={16} className="text-neutral-400" />
                                  <span className="font-medium">{match.source_title || 'Untitled result'}</span>
                                </div>
                                <span className="rounded-full bg-yellow-100 px-2 py-0.5 text-xs text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300">
                                  {(match.similarity * 100).toFixed(1)}% similarity
                                </span>
                              </div>
                              <p className="mb-2 rounded bg-neutral-50 p-2 text-sm italic text-neutral-700 dark:bg-neutral-900/40 dark:text-neutral-300">{match.matched_text}</p>
                              <p className="mb-2 text-xs text-neutral-500">Your sentence: {match.query_sentence}</p>
                              <div className="flex flex-wrap items-center gap-2 text-xs">
                                <span className={`rounded-full px-2 py-0.5 ${match.classification === 'possible_plagiarism' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300' : 'bg-neutral-100 text-neutral-600 dark:bg-neutral-700 dark:text-neutral-300'}`}>
                                  {match.classification.replace(/_/g, ' ')}
                                </span>
                                {match.direct_quotation && <span className="rounded-full bg-yellow-100 px-2 py-0.5 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300">quotation</span>}
                                {match.citation_found && <span className="rounded-full bg-green-100 px-2 py-0.5 text-green-700 dark:bg-green-900/30 dark:text-green-300">citation nearby</span>}
                                {match.source_url && (
                                  <a href={match.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-primary-600 hover:underline dark:text-primary-400">
                                    Open source <ArrowUpRight size={12} />
                                  </a>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </section>

                      <section>
                        <h3 className="mb-2 font-semibold">Searched queries</h3>
                        <div className="space-y-1 text-xs text-neutral-500">
                          {originality.searched_queries.map((queryItem, index) => (
                            <p key={index}>#{queryItem.sentence_index + 1}: “{queryItem.query}” {queryItem.error ? `— error: ${queryItem.error}` : ''}</p>
                          ))}
                        </div>
                      </section>

                      <section className="rounded-lg bg-neutral-50 p-4 text-sm dark:bg-neutral-900/40">
                        <h3 className="mb-2 font-semibold">Limitations</h3>
                        <ul className="list-disc space-y-1 pl-5 text-neutral-500 dark:text-neutral-400">
                          {originality.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
                        </ul>
                      </section>
                    </>
                  )}
                </>
              )}

              {activeTab === 'recommendations' && (
                <section className="space-y-4">
                  <h2 className="text-lg font-semibold">Recommendations</h2>
                  {revisedMetrics.recommendations.length === 0 && validation.warnings.length === 0 && validation.critical_issues.length === 0 && (
                    <p className="rounded-lg bg-green-50 p-4 text-sm text-green-700 dark:bg-green-900/20 dark:text-green-300">
                      No structural issues were detected. Review the revised text and any originality candidates manually before submission.
                    </p>
                  )}
                  {revisedMetrics.recommendations.map((recommendation, index) => (
                    <div key={`${recommendation.category}-${index}`} className="flex items-start gap-3 rounded-lg border border-neutral-200 p-4 dark:border-neutral-700">
                      {recommendation.type === 'critical' ? <XCircle className="mt-0.5 text-red-500" size={18} /> : recommendation.type === 'warning' ? <AlertTriangle className="mt-0.5 text-yellow-500" size={18} /> : <CheckCircle className="mt-0.5 text-blue-500" size={18} />}
                      <div>
                        <p className="text-sm font-medium capitalize">{recommendation.category.replace(/_/g, ' ')}</p>
                        <p className="text-sm text-neutral-600 dark:text-neutral-400">{recommendation.message}</p>
                        <p className="mt-1 text-sm text-neutral-500">{recommendation.suggestion}</p>
                      </div>
                    </div>
                  ))}
                  {validation.critical_issues.map((issue, index) => (
                    <div key={`critical-${index}`} className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20">
                      <XCircle className="mt-0.5 text-red-500" size={18} />
                      <div>
                        <p className="text-sm font-medium text-red-700 dark:text-red-300">Critical validation issue</p>
                        <p className="text-sm text-red-600 dark:text-red-400">{issue.paragraph_id}: {issue.issue}</p>
                      </div>
                    </div>
                  ))}
                  {validation.warnings.map((warning, index) => (
                    <div key={`warning-${index}`} className="flex items-start gap-3 rounded-lg border border-yellow-200 bg-yellow-50 p-4 dark:border-yellow-800 dark:bg-yellow-900/20">
                      <AlertTriangle className="mt-0.5 text-yellow-500" size={18} />
                      <div>
                        <p className="text-sm font-medium text-yellow-700 dark:text-yellow-300">Validation warning</p>
                        <p className="text-sm text-yellow-600 dark:text-yellow-400">{warning.paragraph_id}: {warning.warning}</p>
                      </div>
                    </div>
                  ))}
                </section>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}