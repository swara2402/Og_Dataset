import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  AlertTriangle,
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
  const { listJobs, getAnalysisReport } = useAPI();

  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [analysis, setAnalysis] = useState<AnalysisReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'recommendations'>('overview');
  const [copied, setCopied] = useState(false);

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
          <p className="text-neutral-600 dark:text-neutral-400">Writing quality and protected-content validation.</p>
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

  const { writing_quality, validation, statistics } = analysis;
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
          </div>

          <div className="overflow-hidden rounded-xl border border-neutral-200 bg-white dark:border-neutral-700 dark:bg-neutral-800">
            <div className="flex border-b border-neutral-200 dark:border-neutral-700">
              {(['overview', 'recommendations'] as const).map((tab) => (
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

                  <section>
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

              {activeTab === 'recommendations' && (
                <section className="space-y-4">
                  <h2 className="text-lg font-semibold">Recommendations</h2>
                  {revisedMetrics.recommendations.length === 0 && validation.warnings.length === 0 && validation.critical_issues.length === 0 && (
                    <p className="rounded-lg bg-green-50 p-4 text-sm text-green-700 dark:bg-green-900/20 dark:text-green-300">
                      No structural issues were detected. Review the revised text and citations before submission.
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