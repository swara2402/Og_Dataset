import { useCallback, useEffect, useState } from 'react';
import {
  AlertCircle,
  Check,
  Database,
  HardDrive,
  Loader2,
  Save,
  Shield,
  Sliders,
  Terminal,
} from 'lucide-react';
import { AppSettings, EngineStatus, useAPI } from '../contexts/APIContext';

export default function SettingsPage() {
  const { getSettings, getEngineStatus, updateSettings, isConnected } = useAPI();
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [engineStatus, setEngineStatus] = useState<EngineStatus | null>(null);
  const [verboseLogging, setVerboseLogging] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const [current, providers] = await Promise.all([getSettings(), getEngineStatus()]);
    setEngineStatus(providers);
    if (!current) {
      setError('Could not load settings from the backend.');
      setLoading(false);
      return;
    }
    setSettings(current);
    setVerboseLogging(current.rule_verbose_logging);
    setLoading(false);
  }, [getSettings, getEngineStatus]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    setError(null);
    const updated = await updateSettings({ rule_verbose_logging: verboseLogging });
    if (!updated) {
      setError('Settings could not be saved. Check the backend logs.');
    } else {
      setSettings(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    }
    setSaving(false);
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="animate-spin text-primary-500" size={32} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6">
        <h1 className="mb-2 text-3xl font-bold">Settings</h1>
        <p className="text-neutral-600 dark:text-neutral-400">
          Deterministic editing, OG Dataset status and privacy configuration.
        </p>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          {error}
        </div>
      )}
      {!isConnected && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-yellow-200 bg-yellow-50 p-4 text-sm text-yellow-800 dark:border-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-300">
          <AlertCircle size={18} /> Backend is not reachable. Start the backend server and refresh.
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <section className="card">
            <div className="mb-6 flex items-center gap-3">
              <div className="rounded-lg bg-blue-100 p-2 dark:bg-blue-900/30">
                <Database className="text-blue-600 dark:text-blue-400" size={20} />
              </div>
              <h2 className="text-lg font-semibold">OG Dataset editor</h2>
            </div>
            <div className="space-y-4 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-neutral-500">Engine</span>
                <span>{settings?.engine_type || 'Unavailable'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-neutral-500">Dataset version</span>
                <span>{settings?.dataset?.version || 'Unavailable'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-neutral-500">Rules loaded</span>
                <span>{settings?.dataset?.rules_loaded ?? 0}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-neutral-500">Examples loaded / approved</span>
                <span>
                  {settings?.dataset?.examples_loaded ?? 0} / {settings?.dataset?.approved_examples ?? 0}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-neutral-500">Reference profile</span>
                <span>{settings?.dataset?.reference_profile_loaded ? 'Loaded' : 'Unavailable'}</span>
              </div>
              <div className="flex items-center justify-between border-t border-neutral-200 pt-4 dark:border-neutral-700">
                <span className="text-neutral-500">Processing</span>
                <span>One complete-document deterministic pass</span>
              </div>
              <label className="flex items-center justify-between border-t border-neutral-200 pt-4 dark:border-neutral-700">
                <span>
                  <span className="block font-medium">Verbose rule logging</span>
                  <span className="text-neutral-500">Log each paragraph's detected issues and applied rules.</span>
                </span>
                <input
                  type="checkbox"
                  checked={verboseLogging}
                  onChange={(event) => setVerboseLogging(event.target.checked)}
                  className="h-4 w-4 accent-primary-600"
                />
              </label>
            </div>
          </section>

          <section className="card">
            <div className="mb-4 flex items-center gap-3">
              <div className="rounded-lg bg-emerald-100 p-2 dark:bg-emerald-900/30">
                <Terminal className="text-emerald-700 dark:text-emerald-300" size={20} />
              </div>
              <h2 className="text-lg font-semibold">Optional local engines</h2>
            </div>
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span>Deterministic Python rules</span>
                <span className="font-medium text-green-600">Available</span>
              </div>
              <div className="flex items-center justify-between">
                <span>spaCy context analysis</span>
                <span className={engineStatus?.spacy.enabled ? 'font-medium text-green-600' : 'text-neutral-500'}>
                  {engineStatus?.spacy.enabled
                    ? (engineStatus.spacy.available ? 'Loaded' : 'Enabled · model not loaded')
                    : 'Disabled'}
                </span>
              </div>
              <p className="border-t border-neutral-200 pt-3 text-xs text-neutral-500 dark:border-neutral-700 dark:text-neutral-400">
                spaCy is optional and runs locally when installed and enabled. It provides linguistic context observations; deterministic Python rules remain responsible for all edits.
              </p>
            </div>
          </section>

          <section className="card">
            <div className="mb-4 flex items-center gap-3">
              <div className="rounded-lg bg-purple-100 p-2 dark:bg-purple-900/30">
                <Sliders className="text-purple-600 dark:text-purple-400" size={20} />
              </div>
              <h2 className="text-lg font-semibold">Editing safeguards</h2>
            </div>
            <ul className="list-inside list-disc space-y-2 text-sm text-neutral-600 dark:text-neutral-400">
              <li>Clear text remains unchanged; only concrete local issues are corrected automatically.</li>
              <li>Technical terminology, quotations, citations, equations and identifiers are protected.</li>
              <li>Uncertain sentence or paragraph issues are flagged rather than rewritten.</li>
              <li>Each proposed change records its rule, scope, rationale and review status.</li>
            </ul>
          </section>
        </div>

        <div className="space-y-6">
          <section className="card p-4">
            <h3 className="mb-4 font-semibold">Actions</h3>
            <button
              onClick={() => void handleSave()}
              disabled={saving}
              className="btn-primary inline-flex w-full items-center justify-center gap-2"
            >
              {saving ? <Loader2 className="animate-spin" size={16} /> : <Save size={16} />}
              {saving ? 'Saving...' : 'Save settings'}
            </button>
            {saved && (
              <p className="mt-3 flex items-center gap-2 text-sm text-green-600 dark:text-green-400">
                <Check size={15} /> Settings saved
              </p>
            )}
          </section>

          <section className="card p-4">
            <h3 className="mb-4 flex items-center gap-2 font-semibold">
              <Terminal size={16} /> System
            </h3>
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between border-b border-neutral-200 pb-2 dark:border-neutral-700">
                <span className="text-neutral-500">Backend</span>
                <span className={isConnected ? 'text-green-600' : 'text-red-600'}>
                  {isConnected ? 'Online' : 'Offline'}
                </span>
              </div>
              <div className="rounded-lg bg-green-50 p-4 dark:bg-green-900/20">
                <p className="mb-1 flex items-center gap-2 font-medium text-green-700 dark:text-green-300">
                  <HardDrive size={16} /> Local processing
                </p>
                <p className="text-green-700 dark:text-green-400">
                  The editing pipeline uses local deterministic rules and does not call external model services.
                </p>
              </div>
              <div className="flex items-center gap-2 border-t border-neutral-200 pt-3 dark:border-neutral-700">
                <Shield size={16} className="text-green-600" />
                <span className="text-neutral-500">{settings?.privacy.originality_note}</span>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
