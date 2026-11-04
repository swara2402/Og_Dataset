import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  BarChart3,
  CheckCircle,
  Clock,
  FileText,
  Loader2,
  RefreshCw,
  Settings,
  ShieldCheck,
  Upload,
  XCircle,
} from 'lucide-react';
import { JobSummary, useAPI } from '../contexts/APIContext';

function statusStyles(status: string) {
  if (status === 'completed') return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400';
  if (status === 'processing' || status === 'queued') return 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400';
  if (status === 'failed') return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400';
  return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400';
}

export default function Dashboard() {
  const navigate = useNavigate();
  const { healthCheck, listJobs, isConnected } = useAPI();
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    await healthCheck();
    const loaded = await listJobs();
    setJobs(loaded);
    setLoading(false);
  }, [healthCheck, listJobs]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const interval = setInterval(async () => {
      const loaded = await listJobs();
      setJobs(loaded);
    }, 15000);
    return () => clearInterval(interval);
  }, [listJobs]);

  const completed = jobs.filter((job) => job.status === 'completed').length;
  const active = jobs.filter((job) => job.status === 'processing' || job.status === 'queued').length;
  const failed = jobs.filter((job) => job.status === 'failed' || job.status === 'cancelled').length;

  const quickActions = [
    { title: 'Upload Document', description: 'Refine a new document with local multi-pass rewriting.', icon: Upload, onClick: () => navigate('/document') },
    { title: 'View Analysis', description: 'Inspect real writing-quality, validation and originality reports.', icon: BarChart3, onClick: () => navigate('/analysis') },
    { title: 'Configure Settings', description: 'Choose the local model and processing parameters.', icon: Settings, onClick: () => navigate('/settings') },
  ];

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-10 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="mb-3 text-4xl font-bold">Turnitout V2</h1>
          <p className="max-w-3xl text-lg text-neutral-600 dark:text-neutral-400">
            Local document refinement that preserves citations, numbers and meaning, then reports what actually changed.
          </p>
        </div>
        <button onClick={load} disabled={loading} className="btn-secondary inline-flex items-center gap-2">
          {loading ? <Loader2 className="animate-spin" size={16} /> : <RefreshCw size={16} />} Refresh
        </button>
      </div>

      {!isConnected && (
        <div className="mb-8 rounded-lg border border-yellow-200 bg-yellow-50 p-4 text-yellow-800 dark:border-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-300">
          Backend is offline. Start the backend service, then refresh.
        </div>
      )}

      <div className="mb-10 grid grid-cols-2 gap-4 md:grid-cols-4">
        <div className="card"><div className="mb-2 flex items-center gap-2 text-sm text-neutral-500"><FileText size={16} /> Jobs</div><p className="text-2xl font-bold">{jobs.length}</p></div>
        <div className="card"><div className="mb-2 flex items-center gap-2 text-sm text-neutral-500"><CheckCircle size={16} /> Completed</div><p className="text-2xl font-bold text-green-600 dark:text-green-400">{completed}</p></div>
        <div className="card"><div className="mb-2 flex items-center gap-2 text-sm text-neutral-500"><Clock size={16} /> Active</div><p className="text-2xl font-bold text-blue-600 dark:text-blue-400">{active}</p></div>
        <div className="card"><div className="mb-2 flex items-center gap-2 text-sm text-neutral-500"><XCircle size={16} /> Failed</div><p className="text-2xl font-bold text-red-600 dark:text-red-400">{failed}</p></div>
      </div>

      <div className="mb-12">
        <h2 className="mb-5 text-2xl font-semibold">Quick actions</h2>
        <div className="grid gap-5 md:grid-cols-3">
          {quickActions.map((action) => (
            <button key={action.title} onClick={action.onClick} className="card text-left transition-shadow hover:shadow-md">
              <action.icon size={30} className="text-primary-600 dark:text-primary-400" />
              <h3 className="mb-2 mt-4 text-lg font-semibold">{action.title}</h3>
              <p className="text-sm text-neutral-600 dark:text-neutral-400">{action.description}</p>
            </button>
          ))}
        </div>
      </div>

      <div className="mb-12">
        <h2 className="mb-5 text-2xl font-semibold">Recent documents</h2>
        <div className="card">
          {loading ? (
            <div className="flex justify-center py-8"><Loader2 className="animate-spin text-neutral-400" size={24} /></div>
          ) : jobs.length === 0 ? (
            <div className="py-8 text-center text-neutral-500 dark:text-neutral-400">
              <FileText className="mx-auto mb-3 opacity-40" size={40} />
              <p>No documents processed yet.</p>
              <button onClick={() => navigate('/document')} className="btn-primary mt-4">Upload your first document</button>
            </div>
          ) : (
            <ul className="divide-y divide-neutral-200 dark:divide-neutral-700">
              {jobs.slice(0, 8).map((job) => (
                <li key={job.job_id} className="flex flex-wrap items-center justify-between gap-3 py-4">
                  <button onClick={() => navigate(`/document/${job.job_id}`)} className="flex min-w-0 flex-1 items-center gap-4 text-left">
                    <FileText size={20} className="shrink-0 text-neutral-400" />
                    <div className="min-w-0">
                      <p className="truncate font-medium">{job.filename}</p>
                      <p className="text-sm text-neutral-500">
                        {job.style} · {new Date(job.created_at).toLocaleString()}
                        {job.status === 'processing' && ` · ${job.progress.percent}%`}
                      </p>
                    </div>
                  </button>
                  <div className="flex items-center gap-3">
                    <span className={`rounded-full px-3 py-1 text-xs font-medium ${statusStyles(job.status)}`}>{job.status}</span>
                    <button onClick={() => navigate(job.status === 'completed' ? `/analysis/${job.job_id}` : `/document/${job.job_id}`)} className="text-sm font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400">
                      {job.status === 'completed' ? 'Analyze' : 'View'}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="grid gap-5 md:grid-cols-3">
        <div className="card">
          <ShieldCheck className="mb-3 text-green-600 dark:text-green-400" size={26} />
          <h3 className="mb-2 font-semibold">Local by default</h3>
          <p className="text-sm text-neutral-600 dark:text-neutral-400">Rewriting, validation, analysis and export run on this machine through our rule-based engine.</p>
        </div>
        <div className="card">
          <ShieldCheck className="mb-3 text-primary-600 dark:text-primary-400" size={26} />
          <h3 className="mb-2 font-semibold">Protected content checks</h3>
          <p className="text-sm text-neutral-600 dark:text-neutral-400">Citations, numbers and URLs are masked, preserved and validated after every pass.</p>
        </div>
        <div className="card">
          <ShieldCheck className="mb-3 text-yellow-600 dark:text-yellow-400" size={26} />
          <h3 className="mb-2 font-semibold">Honest reporting</h3>
          <p className="text-sm text-neutral-600 dark:text-neutral-400">AI indicators are clearly labeled heuristics. Originality results are candidates for manual review, not a guarantee.</p>
        </div>
      </div>
    </div>
  );
}