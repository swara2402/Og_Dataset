import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useDropzone } from 'react-dropzone';
import {
  Upload,
  X,
  Square,
  Download,
  File,
  CheckCircle,
  AlertCircle,
  Loader2,
  FileText,
  BarChart3,
  Sparkles,
  ThumbsUp,
  ChevronDown,
  History,
  ShieldCheck,
} from 'lucide-react';
import {
  useAPI,
  ParagraphResult,
  ProcessingProgress,
  ResultsResponse,
  WritingStyle,
  HybridAnalysisResponse,
} from '../contexts/APIContext';

const ACTIVE_EDITING_STYLE: WritingStyle = 'preserve_voice';

type FileStatus = 'uploading' | 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled';

interface WorkspaceFile {
  name: string;
  jobId?: string;
  status: FileStatus;
  error?: string;
}

export default function DocumentWorkspace() {
  const { jobId } = useParams<{ jobId?: string }>();
  const navigate = useNavigate();
  const {
    uploadDocument,
    cancelProcessing,
    getProcessingStatus,
    getProcessingResults,
    reviewParagraph,
    restoreVersion,
    reviewHybridProposal,
    analyzeParagraph,
    exportDocument,
    isConnected,
  } = useAPI();

  const [file, setFile] = useState<WorkspaceFile | null>(null);
  const [progress, setProgress] = useState<ProcessingProgress | null>(null);
  const [results, setResults] = useState<ResultsResponse | null>(null);
  const [activeTab, setActiveTab] = useState<'original' | 'revised' | 'compare' | 'versions'>('revised');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [hybridResult, setHybridResult] = useState<HybridAnalysisResponse | null>(null);
  const [hybridLoading, setHybridLoading] = useState(false);
  const [useSpacyContext, setUseSpacyContext] = useState(false);
  const [copiedProposalId, setCopiedProposalId] = useState<string | null>(null);
  const [hybridDecisions, setHybridDecisions] = useState<Record<string, 'accepted' | 'rejected'>>({});

  const loadJob = useCallback(
    async (id: string) => {
      const status = await getProcessingStatus(id);
      if (!status) {
        setError('Could not load this job.');
        return;
      }
      setProgress(status.progress);
      setFile({
        name: results?.filename || 'Document',
        jobId: id,
        status: status.status as FileStatus,
        error: status.error || undefined,
      });
      if (status.status === 'completed') {
        const loaded = await getProcessingResults(id);
        setResults(loaded);
        if (loaded?.results.length) {
          setSelectedId((current) => current || loaded.results[0].id);
        }
      }
    },
    [getProcessingStatus, getProcessingResults, results?.filename]
  );

  useEffect(() => {
    if (jobId && (!file || file.jobId !== jobId)) {
      void loadJob(jobId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  useEffect(() => {
    if (!file?.jobId) return;
    if (file.status !== 'processing' && file.status !== 'queued') return;
    let active = true;
    const tick = async () => {
      const status = await getProcessingStatus(file.jobId as string);
      if (!active || !status) return;
      setProgress(status.progress);
      if (status.status === 'completed') {
        const loaded = await getProcessingResults(file.jobId as string);
        if (!active) return;
        setResults(loaded);
        if (loaded?.results.length) {
          setSelectedId((current) => current || loaded.results[0].id);
        }
        setFile((current) =>
          current ? { ...current, status: 'completed', name: loaded?.filename || current.name } : current
        );
      } else if (status.status === 'failed' || status.status === 'cancelled') {
        setFile((current) =>
          current
            ? {
                ...current,
                status: status.status as FileStatus,
                error: status.error || (status.status === 'cancelled' ? 'Processing was cancelled.' : 'Processing failed.'),
              }
            : current
        );
      } else {
        setFile((current) => (current ? { ...current, status: 'processing' } : current));
      }
    };
    void tick();
    const interval = setInterval(tick, 1500);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [file?.jobId, file?.status, getProcessingStatus, getProcessingResults]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: {
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'application/pdf': ['.pdf'],
      'text/plain': ['.txt'],
      'text/markdown': ['.md'],
      'text/x-tex': ['.tex'],
    },
    maxFiles: 1,
    onDrop: async (acceptedFiles) => {
      if (!acceptedFiles.length) return;
      const selected = acceptedFiles[0];
      setError(null);
      setResults(null);
      setProgress(null);
      setFile({ name: selected.name, status: 'uploading' });
      const response = await uploadDocument(selected, { style: ACTIVE_EDITING_STYLE, autoStart: true });
      if (!response) {
        setFile({ name: selected.name, status: 'failed', error: 'Upload failed. Check the backend and try again.' });
        return;
      }
      setFile({ name: response.filename, jobId: response.job_id, status: response.status as FileStatus });
      setProgress({
        phase: response.status,
        pass: 0,
        total_passes: 1,
        total: Number(response.statistics.total_paragraphs || 0),
        completed: 0,
        failed: 0,
        skipped: Number(response.statistics.skipped_paragraphs || 0),
        pending: Number(response.statistics.total_paragraphs || 0),
        work_completed: 0,
        work_total: 0,
        percent: 0,
        elapsed_seconds: 0,
        estimated_remaining: null,
      });
      navigate(`/document/${response.job_id}`, { replace: true });
    },
  });

  const handleCancel = async () => {
    if (!file?.jobId) return;
    await cancelProcessing(file.jobId);
    setFile((current) => (current ? { ...current, status: 'cancelled', error: 'Processing was cancelled.' } : current));
  };

  const handleReset = () => {
    setFile(null);
    setProgress(null);
    setResults(null);
    setError(null);
    setSelectedId(null);
    navigate('/document', { replace: true });
  };

  const handleExport = async (format: 'docx' | 'txt' | 'md' | 'pdf' | 'tex') => {
    if (!file?.jobId) return;
    setExportOpen(false);
    const blob = await exportDocument(file.jobId, format);
    if (!blob) {
      setError('Export failed. Please try again.');
      return;
    }
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    const stem = file.name.replace(/\.[^/.]+$/, '');
    anchor.href = url;
    anchor.download = `${stem}_revised.${format}`;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  };

  const handleHybridAnalysis = async (paragraph: ParagraphResult) => {
    setHybridLoading(true);
    setHybridResult(null);
    setError(null);
    const response = await analyzeParagraph({
      paragraph_id: paragraph.id,
      text: paragraph.revised,
      paragraph_type: paragraph.type,
      category: paragraph.category,
      document_context: results?.results.map((item) => item.revised).join("\\n\\n").slice(0, 100000) || paragraph.original,
      include_nlp: useSpacyContext,
    });
    if (!response) {
      setError('Local analysis failed. Check whether optional spaCy context analysis is enabled.');
    } else {
      setHybridResult(response);
    }
    setHybridLoading(false);
  };

  const handleHybridReview = async (
    proposal: HybridAnalysisResponse['proposals'][number],
    action: 'accept' | 'reject'
  ) => {
    if (!file?.jobId) return;
    const response = await reviewHybridProposal(file.jobId, proposal, action);
    if (!response) {
      setError(`Could not ${action} this hybrid suggestion. It may be stale or have failed protected-content validation.`);
      return;
    }
    setHybridDecisions((current) => ({
      ...current,
      [proposal.proposal_id]: action === 'accept' ? 'accepted' : 'rejected',
    }));
    const refreshed = await getProcessingResults(file.jobId);
    if (refreshed) setResults(refreshed);
  };

  const handleRestoreVersion = async (paragraphId: string, version: number) => {
    if (!file?.jobId) return;
    const response = await restoreVersion(file.jobId, paragraphId, version);
    if (!response) {
      setError('Could not restore this version. Please retry.');
      return;
    }
    const refreshed = await getProcessingResults(file.jobId);
    if (refreshed) setResults(refreshed);
  };

  const handleCopyProposal = async (proposal: HybridAnalysisResponse['proposals'][number]) => {
    try {
      await navigator.clipboard.writeText(proposal.suggested_text);
      setCopiedProposalId(proposal.proposal_id);
    } catch {
      setError('Clipboard access was blocked by the browser. Select and copy the suggestion manually.');
    }
  };

  const handleReview = async (
    paragraph: ParagraphResult,
    action: 'accept' | 'reject'
  ) => {
    if (!file?.jobId) return;
    const response = await reviewParagraph(file.jobId, paragraph.id, action);
    if (!response) {
      setError(`Could not ${action} this change. Please retry.`);
      return;
    }
    const refreshed = await getProcessingResults(file.jobId);
    if (refreshed) setResults(refreshed);
  };

  const percent = progress?.percent || 0;
  const selected = results?.results.find((item) => item.id === selectedId) || null;
  const changedCount = results?.results.filter((item) => item.original !== item.revised).length || 0;
  const eligibleCount = results?.results.filter((item) => item.eligible).length || 0;
  const unchangedCount = results?.results.filter((item) => item.eligible && item.original === item.revised).length || 0;
  // Only unresolved proposals and validation failures require a review decision.
  // "No meaningful change" is an informational abstention, not a review warning.
  const reviewItems = results?.results.filter((item) =>
    (item.proposal !== null && item.review_status === 'pending') ||
    item.status === 'needs_review' ||
    item.status === 'failed' ||
    item.validation.critical === true ||
    (item.validation.issues?.length || 0) > 0
  ) || [];
  const authorNoteCount = results?.results.filter((item) =>
    item.proposal === null && item.requires_human_review
  ).length || 0;
  const warningCount = results?.results.reduce(
    (total, item) => total + item.warnings.filter((warning) => warning !== 'No meaningful change was produced.').length,
    0
  ) || 0;
  const protectedCount = results?.results.reduce((sum, item) => sum + item.protected_items.length, 0) || 0;

  const renderDropzone = () => (
    <div className="space-y-6">
      <div className="card">
        <p className="mb-1 text-sm font-medium text-neutral-700 dark:text-neutral-300">Editing mode</p>
        <p className="text-sm font-semibold">Conservative, voice-preserving corrections</p>
        <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
          The current rule engine fixes supported mechanical issues and flags uncertain wording for your review. Academic, concise and other style transformations are not implemented yet.
        </p>
      </div>
      <p className="mt-3 text-xs text-green-700 dark:text-green-400">
        Exports include accepted edits only. Pending or rejected suggestions keep their original text.
      </p>
      <div
        {...getRootProps()}
        className={`cursor-pointer rounded-xl border-2 border-dashed p-12 text-center transition-colors ${
          isDragActive
            ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
            : 'border-neutral-300 hover:border-primary-400 dark:border-neutral-600 dark:hover:border-primary-600'
        }`}
      >
        <input {...getInputProps()} />
        <Upload className="mx-auto mb-4 h-12 w-12 text-neutral-400" />
        <h3 className="mb-2 text-lg font-medium">{isDragActive ? 'Drop your document' : 'Upload a document'}</h3>
        <p className="mb-4 text-sm text-neutral-500 dark:text-neutral-400">
          DOCX, PDF, TXT, Markdown or LaTeX (.tex). Processing happens locally with our rule-based engine.
        </p>
        <span className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-white">
          <FileText size={16} /> Select file
        </span>
      </div>
    </div>
  );

  const renderProgress = () => {
    if (!progress) return null;
    return (
      <div className="card mb-6">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Loader2 className="animate-spin text-primary-500" size={24} />
            <div>
              <h3 className="text-lg font-semibold">
                {progress.phase === 'warming' ? 'Preparing document analysis...' : 'Analyzing the complete document...'}
              </h3>
              <p className="text-sm text-neutral-500 dark:text-neutral-400">
                {progress.percent || 0}% complete · one deterministic pass
              </p>
            </div>
          </div>
          <button onClick={handleCancel} className="flex items-center gap-2 rounded-lg bg-red-100 px-4 py-2 text-red-700 dark:bg-red-900/30 dark:text-red-400">
            <Square size={16} fill="currentColor" /> Cancel
          </button>
        </div>
        <div className="mb-4 h-3 w-full rounded-full bg-neutral-200 dark:bg-neutral-700">
          <div className="h-3 rounded-full bg-primary-600 transition-all duration-500" style={{ width: `${percent}%` }} />
        </div>
        <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
          <div><p className="text-neutral-500">Processed</p><p className="font-medium">{progress.completed} / {progress.total}</p></div>
          <div><p className="text-neutral-500">Skipped</p><p className="font-medium">{progress.skipped}</p></div>
          <div><p className="text-neutral-500">Elapsed</p><p className="font-medium">{Math.round(progress.elapsed_seconds)}s</p></div>
          <div><p className="text-neutral-500">Remaining</p><p className="font-medium">{progress.estimated_remaining ? `${Math.round(progress.estimated_remaining)}s` : 'estimating...'}</p></div>
        </div>
      </div>
    );
  };

  const renderResults = () => {
    if (!results) return null;
    return (
      <div className="space-y-6">
        <div className="rounded-xl border border-green-200 bg-green-50 p-6 dark:border-green-800 dark:bg-green-900/20">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <CheckCircle className="text-green-600 dark:text-green-400" size={24} />
              <div>
                <h3 className="text-lg font-semibold text-green-800 dark:text-green-200">Document analysis complete</h3>
                <p className="text-sm text-green-700 dark:text-green-400">
                  {results.filename} · {Math.round(results.processing_time)}s · {results.results.length} paragraphs inspected
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button onClick={handleReset} className="btn-secondary">New document</button>
              <button onClick={() => navigate(`/analysis/${results.job_id}`)} className="btn-secondary inline-flex items-center gap-2">
                <BarChart3 size={16} /> Analysis
              </button>
              <div className="relative">
                <button onClick={() => setExportOpen((open) => !open)} className="btn-primary inline-flex items-center gap-2">
                  <Download size={16} /> Export <ChevronDown size={14} />
                </button>
                {exportOpen && (
                  <div className="absolute right-0 z-10 mt-2 w-40 overflow-hidden rounded-lg border border-neutral-200 bg-white shadow-lg dark:border-neutral-700 dark:bg-neutral-800">
                    {(['docx', 'txt', 'md', 'pdf', 'tex'] as const).map((format) => (
                      <button key={format} onClick={() => handleExport(format)} className="block w-full px-4 py-2 text-left text-sm hover:bg-neutral-100 dark:hover:bg-neutral-700">
                        {format.toUpperCase()}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
          <div className="card"><p className="text-sm text-neutral-500">Analyzed</p><p className="text-2xl font-bold">{results.results.length}</p><p className="mt-1 text-xs text-neutral-500">{eligibleCount} eligible · {results.results.length - eligibleCount} preserved</p></div>
          <div className="card"><p className="text-sm text-neutral-500">Suggested edits</p><p className="text-2xl font-bold text-green-600 dark:text-green-400">{changedCount}</p><p className="mt-1 text-xs text-neutral-500">Actual text changes</p></div>
          <div className="card"><p className="text-sm text-neutral-500">Unchanged</p><p className="text-2xl font-bold">{unchangedCount}</p><p className="mt-1 text-xs text-neutral-500">Eligible, no edit applied</p></div>
          <div className="card"><p className="text-sm text-neutral-500">Needs review</p><p className="text-2xl font-bold text-yellow-600 dark:text-yellow-400">{reviewItems.length}</p><p className="mt-1 text-xs text-neutral-500">{warningCount} warning messages</p></div>
          <div className="card"><p className="text-sm text-neutral-500">Protected items</p><p className="text-2xl font-bold">{protectedCount}</p><p className="mt-1 text-xs text-neutral-500">Citations, numbers, URLs, etc.</p></div>
        </div>

        <div className="rounded-xl border border-neutral-200 bg-neutral-50 p-4 text-sm dark:border-neutral-700 dark:bg-neutral-900/40">
          <p className="font-semibold text-neutral-800 dark:text-neutral-100">How to read these results</p>
          <p className="mt-1 text-neutral-600 dark:text-neutral-300">A paragraph counts as an edit only when its text actually changed. Unchanged paragraphs are not failures: the rules leave text alone when no safe, supported correction is available. Preserved headings, references, tables and other non-prose content are counted separately from eligible prose.</p>
          {reviewItems.length > 0 && <p className="mt-2 text-neutral-600 dark:text-neutral-300">{reviewItems.length} paragraph(s) have pending edit decisions or validation issues. Open the Revised tab to review them.</p>}
          {authorNoteCount > 0 && <p className="mt-1 text-neutral-600 dark:text-neutral-300">{authorNoteCount} unchanged paragraph(s) have author-review notes. These are kept separate from pending edits.</p>}
          {warningCount > 0 && <p className="mt-1 text-neutral-600 dark:text-neutral-300">{warningCount} actionable warning message(s); routine “No meaningful change” notices are excluded.</p>}
        </div>

        <div className="overflow-hidden rounded-xl border border-neutral-200 bg-white dark:border-neutral-700 dark:bg-neutral-800">
          <div className="flex flex-wrap border-b border-neutral-200 dark:border-neutral-700">
            {(['original', 'revised', 'compare', 'versions'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-5 py-3 text-sm font-medium capitalize transition-colors ${
                  activeTab === tab
                    ? 'border-b-2 border-primary-500 text-primary-600 dark:text-primary-400'
                    : 'text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200'
                }`}
              >
                {tab}
              </button>
            ))}
          </div>

          <div className="max-h-[620px] space-y-4 overflow-auto p-6">
            {activeTab === 'original' && results.results.map((item) => (
              <p key={item.id} className="leading-relaxed text-neutral-700 dark:text-neutral-300">{item.original}</p>
            ))}

            {activeTab === 'revised' && results.results.map((item) => (
              <div key={item.id} className={`rounded-lg border p-4 ${item.processed ? 'border-neutral-200 dark:border-neutral-700' : 'border-transparent opacity-70'}`}>
                <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-neutral-500">
                  <span className="rounded-full bg-neutral-100 px-2 py-0.5 dark:bg-neutral-700">{item.category.replace(/_/g, ' ')}</span>
                  {item.protected_items.length > 0 && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-green-700 dark:bg-green-900/30 dark:text-green-400">
                      <ShieldCheck size={12} /> {item.protected_items.length} protected
                    </span>
                  )}
                  {item.version_count > 1 && <span>{item.version_count - 1} proposed change(s)</span>}
                </div>
                <p className="leading-relaxed text-neutral-800 dark:text-neutral-200">{item.revised}</p>
                {item.proposal === null && (
                  <div className="mt-3 rounded-lg bg-neutral-50 p-3 text-sm dark:bg-neutral-900/50">
                    <p className="font-medium text-neutral-700 dark:text-neutral-200">No edit suggested</p>
                    <p className="mt-1 text-neutral-600 dark:text-neutral-400">{item.edit_rationale || (item.eligible ? 'No supported rule-based correction was identified; the original wording was preserved.' : 'This content type is preserved and is not eligible for prose refinement.')}</p>
                    {item.requires_human_review && <p className="mt-2 text-xs text-yellow-700 dark:text-yellow-300">Author review is recommended; the system did not guess at a change.</p>}
                  </div>
                )}
                {item.proposal !== null && (
                  <div className="mt-3 rounded-lg bg-neutral-50 p-3 text-sm dark:bg-neutral-900/50">
                    <p className="font-medium text-neutral-700 dark:text-neutral-200">
                      {item.edit_scope} edit · {item.applied_rule_ids.join(', ')}
                    </p>
                    <p className="mt-1 text-neutral-600 dark:text-neutral-400">{item.edit_rationale}</p>
                    {item.change_summary.map((change, index) => (
                      <p key={index} className="mt-1 text-xs text-neutral-500">{change}</p>
                    ))}
                    <div className="mt-3 flex items-center gap-2">
                      <span className="mr-2 text-xs capitalize text-neutral-500">
                        Review: {item.review_status}
                      </span>
                      <button
                        onClick={() => void handleReview(item, 'accept')}
                        disabled={item.review_status === 'accepted'}
                        className="btn-secondary inline-flex items-center gap-1"
                      >
                        <ThumbsUp size={14} /> Accept
                      </button>
                      <button
                        onClick={() => void handleReview(item, 'reject')}
                        disabled={item.review_status === 'rejected'}
                        className="btn-secondary inline-flex items-center gap-1"
                      >
                        <X size={14} /> Reject
                      </button>
                    </div>
                    {item.review_status === 'rejected' && (
                      <p className="mt-3 text-xs text-neutral-500">
                        Rejected suggestion: {item.proposal}
                      </p>
                    )}
                  </div>
                )}
                {item.warnings.length > 0 && (
                  <div className="mt-2 rounded bg-yellow-50 p-2 text-xs text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-200">
                    {item.warnings.map((warning, index) => <p key={index}>⚠ {warning}</p>)}
                  </div>
                )}
              </div>
            ))}

            {activeTab === 'compare' && results.results.filter((item) => item.proposal !== null).map((item) => (
              <div key={item.id} className="border-b border-neutral-200 pb-4 last:border-0 dark:border-neutral-700">
                <p className="mb-2 text-xs font-medium uppercase tracking-wide text-neutral-500">{item.category.replace(/_/g, ' ')}</p>
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="rounded-lg bg-red-50 p-3 dark:bg-red-900/10">
                    <p className="mb-1 text-xs font-semibold text-red-600 dark:text-red-400">Original</p>
                    <p className="text-sm leading-relaxed text-neutral-700 dark:text-neutral-300">{item.original}</p>
                  </div>
                  <div className="rounded-lg bg-green-50 p-3 dark:bg-green-900/10">
                    <p className="mb-1 text-xs font-semibold text-green-600 dark:text-green-400">Revised</p>
                    <p className="text-sm leading-relaxed text-neutral-700 dark:text-neutral-300">{item.proposal}</p>
                  </div>
                </div>
              </div>
            ))}

            {activeTab === 'versions' && (
              <div className="space-y-4">
                <div className="flex flex-wrap gap-2">
                  {results.results.filter((item) => item.version_count > 1).map((item) => (
                    <button
                      key={item.id}
                      onClick={() => setSelectedId(item.id)}
                      className={`rounded-lg border px-3 py-1.5 text-sm ${selectedId === item.id ? 'border-primary-500 bg-primary-50 text-primary-700 dark:bg-primary-900/20 dark:text-primary-300' : 'border-neutral-300 dark:border-neutral-600'}`}
                    >
                      Paragraph {item.index + 1}
                    </button>
                  ))}
                </div>
                {!selected && <p className="text-sm text-neutral-500">Select a paragraph to view its version history.</p>}
                {selected && (
                  <div className="space-y-3">
                    <p className="text-xs text-neutral-500">Paragraph {selected.index + 1} · {selected.versions.length} versions</p>
                    <div className="rounded-lg border border-primary-200 bg-primary-50/60 p-4 dark:border-primary-900 dark:bg-primary-900/10">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <p className="font-medium text-neutral-800 dark:text-neutral-100">Hybrid suggestion review</p>
                          <p className="mt-1 text-xs text-neutral-600 dark:text-neutral-400">Generate traceable proposals from deterministic rules and optional spaCy context. Nothing is applied automatically.</p>
                        </div>
                        <button onClick={() => void handleHybridAnalysis(selected)} disabled={hybridLoading} className="btn-primary inline-flex items-center gap-2">
                          {hybridLoading ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
                          {hybridLoading ? 'Analyzing…' : 'Analyze paragraph'}
                        </button>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-4 text-xs text-neutral-600 dark:text-neutral-400">
                        <label className="inline-flex items-center gap-2">
                          <input type="checkbox" checked={useSpacyContext} onChange={(event) => setUseSpacyContext(event.target.checked)} />
                          Include spaCy context
                        </label>
                      </div>
                      {useSpacyContext && <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">Optional spaCy context analysis must be enabled and configured locally.</p>}
                      {hybridResult && hybridResult.paragraph_id === selected.id && (
                        <div className="mt-4 space-y-3">
                          <p className="text-xs font-medium text-neutral-700 dark:text-neutral-300">{hybridResult.proposals.length} proposal(s) · {hybridResult.applied ? 'Applied' : 'Not applied'} · Review required: {hybridResult.review_required ? 'Yes' : 'No'}</p>
                          {hybridResult.proposals.length === 0 && <p className="text-sm text-neutral-600 dark:text-neutral-400">No additional supported suggestions were produced. The paragraph remains unchanged.</p>}
                          {hybridResult.proposals.map((proposal) => (
                            <div key={proposal.proposal_id} className="rounded-lg border border-neutral-200 bg-white p-3 dark:border-neutral-700 dark:bg-neutral-800">
                              <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-neutral-500">
                                <span className="rounded-full bg-neutral-100 px-2 py-0.5 dark:bg-neutral-700">{proposal.source_engine.replace(/_/g, ' ')}</span>
                                <span>{proposal.category}</span>
                                <span>Risk: {proposal.semantic_risk}</span>
                                {proposal.rule_id && <span>Rule: {proposal.rule_id}</span>}
                              </div>
                              <p className="text-sm leading-relaxed text-neutral-500 line-through">{proposal.original_text}</p>
                              <p className="mt-2 text-sm leading-relaxed text-neutral-800 dark:text-neutral-100">{proposal.suggested_text}</p>
                              {proposal.explanation && <p className="mt-2 text-xs text-neutral-600 dark:text-neutral-400">{proposal.explanation}</p>}
                              <div className="mt-3 flex flex-wrap items-center gap-2">
                                <button onClick={() => void handleHybridReview(proposal, 'accept')} disabled={!!hybridDecisions[proposal.proposal_id]} className="btn-primary inline-flex items-center gap-2">
                                  <ThumbsUp size={14} /> Accept
                                </button>
                                <button onClick={() => void handleHybridReview(proposal, 'reject')} disabled={!!hybridDecisions[proposal.proposal_id]} className="btn-secondary inline-flex items-center gap-2">
                                  <X size={14} /> Reject
                                </button>
                                <button onClick={() => void handleCopyProposal(proposal)} className="btn-secondary inline-flex items-center gap-2">
                                  <FileText size={14} /> {copiedProposalId === proposal.proposal_id ? 'Copied' : 'Copy'}
                                </button>
                                {hybridDecisions[proposal.proposal_id] && <span className="text-xs font-medium capitalize text-neutral-600 dark:text-neutral-300">Decision saved: {hybridDecisions[proposal.proposal_id]}</span>}
                              </div>
                            </div>
                          ))}
                          <p className="text-xs text-neutral-500">These are review-only proposals. Copy a suggestion into your own revision after checking meaning, citations, and technical accuracy.</p>
                        </div>
                      )}
                    </div>
                    {selected.versions.map((version) => (
                      <div key={version.version} className="rounded-lg border border-neutral-200 p-4 dark:border-neutral-700">
                        <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-neutral-500">
                          <span className="rounded-full bg-neutral-100 px-2 py-0.5 dark:bg-neutral-700">
                            {version.source === 'original' ? 'Original' : `Version ${version.version}`}
                          </span>
                          {version.source !== 'original' && <span>Pass {version.pass_number}</span>}
                          {version.instruction && <span>· {version.instruction}</span>}
                          <span>· {version.created_at ? new Date(version.created_at).toLocaleTimeString() : ''}</span>
                        </div>
                        <p className="text-sm leading-relaxed text-neutral-800 dark:text-neutral-200">{version.text}</p>
                        <button onClick={() => void handleRestoreVersion(selected.id, version.version)} disabled={selected.revised === version.text} className="btn-secondary mt-3 text-xs">
                          {selected.revised === version.text ? "Current version" : "Restore this version"}
                        </button>
                        {version.validation?.warnings && version.validation.warnings.length > 0 && (
                          <p className="mt-2 text-xs text-yellow-700 dark:text-yellow-300">{version.validation.warnings.join(' · ')}</p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="card">
          <div className="flex items-start gap-3">
            <History size={20} className="mt-0.5 text-neutral-400" />
            <div className="text-sm text-neutral-600 dark:text-neutral-400">
              <p className="font-medium text-neutral-800 dark:text-neutral-200">Local processing record</p>
              <p>Rule-based engine: {String(results.statistics.applied_rule_count || '0')} rules applied · Cache hits: {String(results.statistics.cache_hits || 0)}</p>
              <p>All document content stayed on this machine. Exports preserve protected citations and numbers.</p>
            </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-8">
        <h1 className="mb-2 text-3xl font-bold">Document Workspace</h1>
        <p className="text-neutral-600 dark:text-neutral-400">
          Complete-document analysis with conservative OG Dataset rules and protected-content validation.
        </p>
      </div>

      {!isConnected && (
        <div className="mb-6 rounded-xl border border-yellow-200 bg-yellow-50 p-4 dark:border-yellow-800 dark:bg-yellow-900/20">
          <div className="flex items-center gap-3 text-sm text-yellow-800 dark:text-yellow-200">
            <AlertCircle size={20} /> Backend is offline. Start the backend service, then retry.
          </div>
        </div>
      )}

      {error && (
        <div className="mb-6 flex items-start justify-between gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          <span className="flex items-center gap-2"><AlertCircle size={18} /> {error}</span>
          <button onClick={() => setError(null)}><X size={16} /></button>
        </div>
      )}

      {!file && isConnected && renderDropzone()}
      {file?.status === 'uploading' && <div className="card flex items-center gap-3"><Loader2 className="animate-spin" size={20} /> Uploading and parsing your document...</div>}
      {(file?.status === 'processing' || file?.status === 'queued') && (
        <>
          <div className="card mb-6 flex items-center gap-3"><File size={20} className="text-neutral-400" /><span className="font-medium">{file.name}</span></div>
          {renderProgress()}
        </>
      )}
      {file?.status === 'completed' && renderResults()}
      {(file?.status === 'failed' || file?.status === 'cancelled') && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-6 dark:border-red-800 dark:bg-red-900/20">
          <div className="mb-3 flex items-center gap-3">
            {file.status === 'cancelled' ? <X className="text-yellow-600" size={24} /> : <AlertCircle className="text-red-600" size={24} />}
            <h3 className="text-lg font-semibold">{file.status === 'cancelled' ? 'Processing cancelled' : 'Processing failed'}</h3>
          </div>
          <p className="mb-4 text-sm text-red-700 dark:text-red-300">{file.error}</p>
          <button onClick={handleReset} className="btn-secondary">Try again</button>
        </div>
      )}

      {file && file.status !== 'completed' && file.status !== 'uploading' && file.status !== 'failed' && file.status !== 'cancelled' && file.status !== 'processing' && file.status !== 'queued' && (
        <div className="card text-sm text-neutral-500">Loading job...</div>
      )}

      {results?.job_id && results.results.length === 0 && (
        <div className="card mt-6 flex items-center gap-3"><Sparkles size={18} /> No eligible prose paragraphs were found. Headings, tables, references and code are preserved untouched.</div>
      )}
    </div>
  );
}