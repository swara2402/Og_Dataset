import { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import axios, { AxiosError } from 'axios';

export type WritingStyle =
  | 'academic'
  | 'professional'
  | 'natural'
  | 'concise'
  | 'executive'
  | 'preserve_voice';

export interface HealthStatus {
  status: string;
  timestamp: string;
  services: {
    api: string;
    processor: string;
    cache: string;
    rule_engine: string;
  };
  installed_rule_count: number;
  engine_status: string;
  dataset?: {
    version: string;
    rules_loaded: number;
    examples_loaded: number;
    approved_examples: number;
    reference_profile_loaded: boolean;
  };
}

export interface EngineStatus {
  deterministic_rules: { available: boolean; enabled: boolean };
  spacy: { provider: string; available: boolean; enabled: boolean; model: string; error: string | null };
  offline_basic_available: boolean;
}

export interface AppSettings {
  engine_type: string;
  engine_status: string;
  dataset?: {
    version: string;
    rules_loaded: number;
    examples_loaded: number;
    approved_examples: number;
    reference_profile_loaded: boolean;
  };
  batch_size: number;
  max_workers: number;
  max_retries: number;
  passes: number;
  rule_engine_enabled: boolean;
  rule_verbose_logging: boolean;
  privacy: {
    local_only: boolean;
    hosted_llm: boolean;
    originality_search: boolean;
    originality_note: string;
  };
  cache_entries: number;
  styles: WritingStyle[];
}

export interface HybridProposal {
  proposal_id: string;
  paragraph_id: string;
  source_engine: string;
  rule_id: string | null;
  original_text: string;
  suggested_text: string;
  category: string;
  explanation: string;
  confidence: number | null;
  semantic_risk: string;
  requires_review: boolean;
  status: string;
  start_offset: number | null;
  end_offset: number | null;
  dataset_version: string | null;
  model_version: string | null;
  validation: Record<string, unknown>;
}

export interface HybridAnalysisResponse {
  paragraph_id: string;
  proposals: HybridProposal[];
  context: Record<string, unknown>;
  applied: false;
  review_required: boolean;
}

export interface ProcessingProgress {
  phase: string;
  pass: number;
  total_passes: number;
  total: number;
  completed: number;
  failed: number;
  skipped: number;
  pending: number;
  work_completed: number;
  work_total: number;
  percent: number;
  elapsed_seconds: number;
  estimated_remaining: number | null;
}

export interface UploadResponse {
  job_id: string;
  filename: string;
  file_size: number;
  upload_time: string;
  style: WritingStyle;
  status: string;
  statistics: Record<string, unknown>;
  warnings: string[];
}

export interface ProcessingStatusResponse {
  job_id: string;
  status: string;
  progress: ProcessingProgress;
  elapsed_time: number;
  estimated_remaining: number | null;
  error?: string | null;
}

export interface VersionEntry {
  version: number;
  text: string;
  pass_number: number;
  source: string;
  created_at: string;
  instruction: string | null;
  validation: ValidationResult;
  elapsed_seconds: number;
  // Traceability fields for rule-based editing
  applied_rule_ids: string[];
  edit_rationale: string;
  editing_level_applied: string;
  issues_found: string[];
  edit_scope: string;
  change_summary: string[];
  requires_human_review: boolean;
}

export interface ValidationResult {
  valid?: boolean;
  critical?: boolean;
  issues?: string[];
  warnings?: string[];
  checks?: Record<string, boolean>;
  metrics?: Record<string, number>;
}

export interface ParagraphResult {
  id: string;
  index: number;
  original: string;
  revised: string;
  proposal: string | null;
  type: string;
  category: string;
  section: string | null;
  eligible: boolean;
  processed: boolean;
  status: string;
  warnings: string[];
  validation: ValidationResult;
  error?: string | null;
  attempts: number;
  elapsed_seconds: number;
  version_count: number;
  protected_items: { type: string; value: string }[];
  versions: VersionEntry[];
  // Traceability fields for rule-based editing
  applied_rule_ids: string[];
  edit_rationale: string;
  editing_level_applied: string;
  issues_found: string[];
  edit_scope: string;
  change_summary: string[];
  requires_human_review: boolean;
  review_status: string;
}

export interface ResultsResponse {
  job_id: string;
  filename: string;
  file_type: string;
  style: string;
  status: string;
  processing_time: number;
  options: Record<string, unknown>;
  results: ParagraphResult[];
  statistics: Record<string, unknown>;
  warnings: string[];
}

export interface QualityMetrics {
  overall_score: number;
  readability_score: number;
  flesch_reading_ease: number;
  sentence_variety: number;
  vocabulary_diversity: number;
  repetition_score: number;
  transition_usage: number;
  formality: number;
  clarity: number;
  coherence: number;
  verbosity: number;
  terminology_consistency: number;
  word_count: number;
  sentence_count: number;
  paragraph_count: number;
  average_sentence_length: number;
  repeated_phrases: string[];
  recommendations: Recommendation[];
}

export interface Recommendation {
  type: string;
  category: string;
  message: string;
  suggestion: string;
}

export interface AIIndicator {
  id: string;
  label: string;
  score: number;
  severity: string;
  description: string;
  evidence: string[];
}

export interface AIReport {
  detector_available: boolean;
  detector_note: string;
  indicator_score: number | null;
  band: string;
  summary: string;
  indicators: AIIndicator[];
  metrics: Record<string, number>;
}

export interface OriginalityMatch {
  id: string;
  query_sentence: string;
  sentence_index: number;
  matched_text: string;
  source_title: string;
  source_url: string;
  provider: string;
  similarity: number;
  direct_quotation: boolean;
  citation_found: boolean;
  classification: string;
}

export interface OriginalityReport {
  provider: string;
  scope: string;
  disclosure: string;
  summary: string;
  searched_queries: { sentence_index: number; query: string; error?: string }[];
  sentences_searched: number;
  matches: OriginalityMatch[];
  statistics: {
    matched_sources: number;
    potential_matches: number;
    needs_manual_review: number;
    uncited_quotations: number;
    unique_content_percentage: number;
    matched_text_percentage: number;
    similarity_threshold: number;
  };
  limitations: string[];
}

export interface AnalysisReport {
  job_id: string;
  filename: string;
  style: string;
  status: string;
  statistics: Record<string, unknown>;
  writing_quality: {
    original: QualityMetrics;
    revised: QualityMetrics;
    deltas: Record<string, number>;
  };
  ai_indicators: AIReport;
  validation: {
    protected_content_preserved: boolean;
    numbers_preserved: boolean;
    citations_preserved: boolean;
    critical_issues: { paragraph_id: string; issue: string }[];
    warnings: { paragraph_id: string; warning: string }[];
    checked_paragraphs: number;
  };
  originality: OriginalityReport | null;
  disclaimer: string;
}

export interface JobSummary {
  job_id: string;
  filename: string;
  file_type: string;
  style: string;
  status: string;
  created_at: string;
  progress: ProcessingProgress;
  error?: string | null;
  statistics: Record<string, unknown>;
  elapsed_seconds: number;
}

export interface RefineResponse {
  job_id: string;
  paragraph: ParagraphResult;
  statistics: Record<string, unknown>;
}

export interface ReviewResponse {
  job_id: string;
  paragraph: ParagraphResult;
  statistics: Record<string, unknown>;
}

interface APIContextType {
  healthCheck: () => Promise<HealthStatus | null>;
  getSettings: () => Promise<AppSettings | null>;
  getEngineStatus: () => Promise<EngineStatus | null>;
  analyzeParagraph: (request: {
    paragraph_id: string;
    text: string;
    paragraph_type?: string;
    category?: string;
    document_context?: string;
    include_nlp?: boolean;
  }) => Promise<HybridAnalysisResponse | null>;
  updateSettings: (update: Partial<AppSettings>) => Promise<AppSettings | null>;
  clearCache: () => Promise<boolean>;
  uploadDocument: (
    file: File,
    options?: { style?: WritingStyle; passes?: number; batchSize?: number; autoStart?: boolean }
  ) => Promise<UploadResponse | null>;
  getProcessingStatus: (jobId: string) => Promise<ProcessingStatusResponse | null>;
  getProcessingResults: (jobId: string) => Promise<ResultsResponse | null>;
  cancelProcessing: (jobId: string) => Promise<boolean>;
  refineParagraph: (
    jobId: string,
    paragraphId: string,
    instruction: string,
    style?: WritingStyle
  ) => Promise<RefineResponse | null>;
  reviewParagraph: (
    jobId: string,
    paragraphId: string,
    action: 'accept' | 'reject'
  ) => Promise<ReviewResponse | null>;
  restoreVersion: (jobId: string, paragraphId: string, version: number) => Promise<ReviewResponse | null>;
  reviewHybridProposal: (
    jobId: string,
    proposal: HybridProposal,
    action: 'accept' | 'reject'
  ) => Promise<ReviewResponse | null>;
  getAnalysisReport: (jobId: string) => Promise<AnalysisReport | null>;
  runOriginality: (options: {
    jobId?: string;
    paragraphIds?: string[];
    text?: string;
    maxSentences?: number;
    fetchPages?: boolean;
  }) => Promise<OriginalityReport | null>;
  exportDocument: (jobId: string, format: 'docx' | 'txt' | 'md' | 'pdf' | 'tex') => Promise<Blob | null>;
  listJobs: () => Promise<JobSummary[]>;
  errorMessage: (error: unknown) => string;
  isConnected: boolean;
  isCheckingConnection: boolean;
  lastConnectionStatus: HealthStatus | null;
}

const APIContext = createContext<APIContextType | undefined>(undefined);

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 60000,
});

function extractError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<{ detail?: string }>;
    return axiosError.response?.data?.detail || axiosError.message;
  }
  return error instanceof Error ? error.message : 'Unexpected error';
}

export function APIProvider({ children }: { children: ReactNode }) {
  const [isConnected, setIsConnected] = useState(false);
  const [isCheckingConnection, setIsCheckingConnection] = useState(false);
  const [lastConnectionStatus, setLastConnectionStatus] = useState<HealthStatus | null>(null);

  const healthCheck = useCallback(async (): Promise<HealthStatus | null> => {
    setIsCheckingConnection(true);
    try {
      const response = await api.get<HealthStatus>('/health');
      setLastConnectionStatus(response.data);
      setIsConnected(response.data.engine_status === 'ready');
      return response.data;
    } catch {
      setIsConnected(false);
      return null;
    } finally {
      setIsCheckingConnection(false);
    }
  }, []);



  const getEngineStatus = useCallback(async (): Promise<EngineStatus | null> => {
    try {
      const response = await api.get<EngineStatus>('/engines/status');
      return response.data;
    } catch {
      return null;
    }
  }, []);

  const analyzeParagraph = useCallback(async (request: {
    paragraph_id: string;
    text: string;
    paragraph_type?: string;
    category?: string;
    document_context?: string;
    include_nlp?: boolean;
  }): Promise<HybridAnalysisResponse | null> => {
    try {
      const response = await api.post<HybridAnalysisResponse>('/analysis/paragraph', request, { timeout: 180000 });
      return response.data;
    } catch (error) {
      console.error('Hybrid paragraph analysis failed:', extractError(error));
      return null;
    }
  }, []);

  const getSettings = useCallback(async (): Promise<AppSettings | null> => {
    try {
      const response = await api.get<AppSettings>('/config/settings');
      return response.data;
    } catch {
      return null;
    }
  }, []);

  const updateSettings = useCallback(
    async (update: Partial<AppSettings>): Promise<AppSettings | null> => {
      try {
        const response = await api.patch<AppSettings>('/config/settings', update);
        return response.data;
      } catch {
        return null;
      }
    },
    []
  );

  const clearCache = useCallback(async (): Promise<boolean> => {
    try {
      await api.post('/config/cache/clear');
      return true;
    } catch {
      return false;
    }
  }, []);

  const uploadDocument = useCallback(
    async (
      file: File,
      options?: { style?: WritingStyle; passes?: number; batchSize?: number; autoStart?: boolean }
    ): Promise<UploadResponse | null> => {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('style', options?.style || 'academic');
      formData.append('passes', String(options?.passes || 0));
      formData.append('batch_size', String(options?.batchSize || 0));
      formData.append('auto_start', String(options?.autoStart ?? true));
      try {
        const response = await api.post<UploadResponse>('/documents/upload', formData, {

          timeout: 120000,
        });
        return response.data;
      } catch (error) {
        console.error('Document upload failed:', extractError(error));
        return null;
      }
    },
    []
  );

  const getProcessingStatus = useCallback(
    async (jobId: string): Promise<ProcessingStatusResponse | null> => {
      try {
        const response = await api.get<ProcessingStatusResponse>(`/processing/${jobId}/status`);
        return response.data;
      } catch {
        return null;
      }
    },
    []
  );

  const getProcessingResults = useCallback(
    async (jobId: string): Promise<ResultsResponse | null> => {
      try {
        const response = await api.get<ResultsResponse>(`/processing/${jobId}/results`);
        return response.data;
      } catch {
        return null;
      }
    },
    []
  );

  const cancelProcessing = useCallback(async (jobId: string): Promise<boolean> => {
    try {
      const response = await api.post<{ cancelled: boolean }>(`/processing/${jobId}/cancel`);
      return response.data.cancelled;
    } catch {
      return false;
    }
  }, []);

  const refineParagraph = useCallback(
    async (
      jobId: string,
      paragraphId: string,
      instruction: string,
      style?: WritingStyle
    ): Promise<RefineResponse | null> => {
      try {
        const response = await api.post<RefineResponse>(
          `/processing/${jobId}/refine`,
          { paragraph_id: paragraphId, instruction, style },
          { timeout: 240000 }
        );
        return response.data;
      } catch (error) {
        console.error('Refinement failed:', extractError(error));
        return null;
      }
    },
    []
  );

  const reviewParagraph = useCallback(
    async (
      jobId: string,
      paragraphId: string,
      action: 'accept' | 'reject'
    ): Promise<ReviewResponse | null> => {
      try {
        const response = await api.post<ReviewResponse>(
          `/processing/${jobId}/review`,
          { paragraph_id: paragraphId, action }
        );
        return response.data;
      } catch (error) {
        console.error(`Could not ${action} paragraph change:`, extractError(error));
        return null;
      }
    },
    []
  );

  const restoreVersion = useCallback(
    async (jobId: string, paragraphId: string, version: number): Promise<ReviewResponse | null> => {
      try {
        const response = await api.post<ReviewResponse>(
          '/processing/' + jobId + '/restore-version',
          { paragraph_id: paragraphId, version }
        );
        return response.data;
      } catch (error) {
        console.error('Could not restore paragraph version:', extractError(error));
        return null;
      }
    },
    []
  );

  const reviewHybridProposal = useCallback(
    async (
      jobId: string,
      proposal: HybridProposal,
      action: 'accept' | 'reject'
    ): Promise<ReviewResponse | null> => {
      try {
        const response = await api.post<ReviewResponse>(
          `/processing/${jobId}/proposal-review`,
          {
            paragraph_id: proposal.paragraph_id,
            proposal_id: proposal.proposal_id,
            original_text: proposal.original_text,
            suggested_text: proposal.suggested_text,
            source_engine: proposal.source_engine,
            category: proposal.category,
            explanation: proposal.explanation,
            semantic_risk: proposal.semantic_risk,
            action,
          }
        );
        return response.data;
      } catch (error) {
        console.error(`Could not ${action} hybrid proposal:`, extractError(error));
        return null;
      }
    },
    []
  );

  const getAnalysisReport = useCallback(async (jobId: string): Promise<AnalysisReport | null> => {
    try {
      const response = await api.get<AnalysisReport>(`/analysis/${jobId}/report`);
      return response.data;
    } catch {
      return null;
    }
  }, []);

  const runOriginality = useCallback(
    async (options: {
      jobId?: string;
      paragraphIds?: string[];
      text?: string;
      maxSentences?: number;
      fetchPages?: boolean;
    }): Promise<OriginalityReport | null> => {
      try {
        const response = await api.post<OriginalityReport>(
          '/originality/check',
          {
            confirm_search: true,
            job_id: options.jobId,
            paragraph_ids: options.paragraphIds,
            text: options.text,
            max_sentences: options.maxSentences ?? 6,
            fetch_pages: options.fetchPages ?? true,
          },
          { timeout: 180000 }
        );
        return response.data;
      } catch (error) {
        console.error('Originality check failed:', extractError(error));
        return null;
      }
    },
    []
  );

  const exportDocument = useCallback(
    async (jobId: string, format: 'docx' | 'txt' | 'md' | 'pdf' | 'tex'): Promise<Blob | null> => {
      try {
        const response = await api.post(`/export/${jobId}?format=${format}`, null, {
          responseType: 'blob',
          timeout: 120000,
        });
        return response.data as Blob;
      } catch (error) {
        console.error('Export failed:', extractError(error));
        return null;
      }
    },
    []
  );

  const listJobs = useCallback(async (): Promise<JobSummary[]> => {
    try {
      const response = await api.get<{ jobs: JobSummary[] }>('/jobs');
      return response.data.jobs;
    } catch {
      return [];
    }
  }, []);

  const value: APIContextType = {
    healthCheck,
    getSettings,
    getEngineStatus,
    analyzeParagraph,
    updateSettings,
    clearCache,
    uploadDocument,
    getProcessingStatus,
    getProcessingResults,
    cancelProcessing,
    refineParagraph,
    reviewParagraph,
    restoreVersion,
    reviewHybridProposal,
    getAnalysisReport,
    runOriginality,
    exportDocument,
    listJobs,
    errorMessage: extractError,
    isConnected,
    isCheckingConnection,
    lastConnectionStatus,
  };

  return <APIContext.Provider value={value}>{children}</APIContext.Provider>;
}

export function useAPI() {
  const context = useContext(APIContext);
  if (context === undefined) {
    throw new Error('useAPI must be used within an APIProvider');
  }
  return context;
}