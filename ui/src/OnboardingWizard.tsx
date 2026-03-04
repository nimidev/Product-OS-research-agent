import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  CheckCircle2,
  ChevronRight,
  Loader2,
  AlertCircle,
  Database,
  ArrowLeft,
  Search,
  Zap,
  ExternalLink,
} from 'lucide-react';
import { MondayBoardSchema, MondayEntityMappingConfig, MondayDirection } from './types';

const RESEARCH_API_URL = import.meta.env.VITE_RESEARCH_API_URL || 'http://localhost:8000';

const ENTITY_TYPES = [
  { id: 'feature_request', label: 'Feature Requests', description: 'Ideas and feature asks from customers or internal teams' },
  { id: 'bug', label: 'Bugs', description: 'Defects and issues reported by users or QA' },
  { id: 'support_ticket', label: 'Support Tickets', description: 'Customer support cases and inquiries' },
  { id: 'roadmap_item', label: 'Roadmap Items', description: 'Planned features, milestones, and initiatives' },
  { id: 'prd', label: 'PRDs', description: 'Product requirement documents and specs' },
  { id: 'meeting_note', label: 'Meeting Notes', description: 'Notes and decisions from team meetings' },
] as const;

const TOOL_OPTIONS: readonly { id: string; label: string; enabled: boolean; comingSoon?: boolean }[] = [
  { id: 'monday', label: 'Monday.com', enabled: true },
  { id: 'jira', label: 'Jira', enabled: false, comingSoon: true },
  { id: 'notion', label: 'Notion', enabled: false, comingSoon: true },
  { id: 'linear', label: 'Linear', enabled: false, comingSoon: true },
  { id: 'none', label: 'Not tracked yet', enabled: true },
];

type EntityToolMapping = Record<string, string>;

const DEFAULT_FIELD_MAPPINGS: Record<string, Record<string, string>> = {
  feature_request: { name: 'title', text0: 'description', people0: 'customer', status: 'status' },
  bug: { name: 'title', text0: 'description', status: 'status' },
  support_ticket: { name: 'title', text0: 'description', people0: 'customer', status: 'status' },
  roadmap_item: { name: 'title', text0: 'description', status: 'status' },
  prd: { name: 'title', text0: 'overview', status: 'status' },
  meeting_note: { name: 'title', text0: 'transcript' },
};

interface OnboardingWizardProps {
  onComplete: () => void;
}

export default function OnboardingWizard({ onComplete }: OnboardingWizardProps) {
  const [step, setStep] = useState(1);
  const totalSteps = 5;

  // Step 1: entity → tool mapping
  const [entityToolMap, setEntityToolMap] = useState<EntityToolMapping>(() =>
    Object.fromEntries(ENTITY_TYPES.map(e => [e.id, '']))
  );

  // Step 2: API key
  const [mondayApiKey, setMondayApiKey] = useState('');
  const [mondaySubdomain, setMondaySubdomain] = useState('');
  const [keyTestStatus, setKeyTestStatus] = useState<'idle' | 'testing' | 'ok' | 'error'>('idle');
  const [keyError, setKeyError] = useState('');

  // Step 3: Board mapping
  const [boards, setBoards] = useState<MondayBoardSchema[]>([]);
  const [boardsLoading, setBoardsLoading] = useState(false);
  const [entityConfigs, setEntityConfigs] = useState<Record<string, MondayEntityMappingConfig>>({});

  // Step 4: Sync
  const [syncStatus, setSyncStatus] = useState<'idle' | 'syncing' | 'done' | 'error'>('idle');
  const [syncStats, setSyncStats] = useState<{ fetched: number; embedded: number } | null>(null);
  const [syncError, setSyncError] = useState('');

  // Step 5: First query
  const [firstQuery, setFirstQuery] = useState('');

  const mondayEntities = Object.entries(entityToolMap)
    .filter(([, tool]) => tool === 'monday')
    .map(([entityId]) => entityId);

  const hasAnyToolSelected = Object.values(entityToolMap).some(v => v && v !== 'none' && v !== '');
  const needsMonday = mondayEntities.length > 0;

  const isSubitemsBoard = (name: string) => /^subitems of /i.test(name.trim());
  const visibleBoards = boards.filter(b => !isSubitemsBoard(b.name));

  // Initialize entity configs when Monday entities change
  useEffect(() => {
    const newConfigs: Record<string, MondayEntityMappingConfig> = {};
    for (const entityId of mondayEntities) {
      newConfigs[entityId] = entityConfigs[entityId] || {
        entity_type: entityId,
        board_ids: [],
        direction: 'monday_to_os' as MondayDirection,
        field_mappings: DEFAULT_FIELD_MAPPINGS[entityId] || { name: 'title' },
      };
    }
    setEntityConfigs(newConfigs);
  }, [entityToolMap]);

  // Load boards when entering step 3
  useEffect(() => {
    if (step === 3 && needsMonday && boards.length === 0 && !boardsLoading) {
      loadBoards();
    }
  }, [step]);

  async function testApiKey() {
    setKeyTestStatus('testing');
    setKeyError('');
    try {
      const res = await fetch(`${RESEARCH_API_URL}/integrations/monday/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: mondayApiKey }),
      });
      if (res.ok) {
        setKeyTestStatus('ok');
      } else {
        setKeyTestStatus('error');
        setKeyError('Invalid API key or Monday.com is unreachable.');
      }
    } catch {
      setKeyTestStatus('error');
      setKeyError('Network error — check that the API server is running.');
    }
  }

  async function loadBoards() {
    setBoardsLoading(true);
    try {
      const res = await fetch(`${RESEARCH_API_URL}/integrations/monday/schema`);
      if (res.ok) {
        const data = await res.json();
        setBoards(data.boards || []);
      }
    } catch {
      // boards will stay empty, user can still proceed
    }
    setBoardsLoading(false);
  }

  async function saveConfigAndSync() {
    setSyncStatus('syncing');
    setSyncError('');
    try {
      const boardIds = [...new Set(
        Object.values(entityConfigs).flatMap(c => c.board_ids)
      )];
      const entityMappings: Record<string, string> = {};
      for (const [entityType, cfg] of Object.entries(entityConfigs)) {
        for (const boardId of cfg.board_ids) {
          entityMappings[boardId] = entityType;
        }
      }

      const putRes = await fetch(`${RESEARCH_API_URL}/integrations/monday`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          enabled: true,
          api_key: mondayApiKey,
          subdomain: mondaySubdomain || undefined,
          board_ids: boardIds,
          entity_mappings: entityMappings,
          entity_configs: entityConfigs,
        }),
      });

      if (!putRes.ok) {
        throw new Error('Failed to save configuration');
      }

      const prepRes = await fetch(`${RESEARCH_API_URL}/integrations/monday/prepare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (prepRes.ok) {
        const data = await prepRes.json();
        setSyncStats({ fetched: data.fetched || 0, embedded: data.embedded || 0 });
        setSyncStatus('done');
      } else {
        throw new Error('Sync failed');
      }
    } catch (e: any) {
      setSyncStatus('error');
      setSyncError(e.message || 'Something went wrong during sync.');
    }
  }

  function getSuggestedQuery(): string {
    if (mondayEntities.includes('support_ticket')) {
      return 'What are the top pain points reported in support tickets?';
    }
    if (mondayEntities.includes('feature_request')) {
      return 'What are the most requested features from customers?';
    }
    if (mondayEntities.includes('bug')) {
      return 'What are the most critical bugs affecting users?';
    }
    return 'What are the key insights from our product data?';
  }

  function handleComplete() {
    if (firstQuery.trim()) {
      localStorage.setItem('onboarding_first_query', firstQuery.trim());
    } else {
      localStorage.setItem('onboarding_first_query', getSuggestedQuery());
    }
    onComplete();
  }

  const canProceedStep1 = hasAnyToolSelected;
  const canProceedStep2 = keyTestStatus === 'ok';
  const canProceedStep3 = Object.values(entityConfigs).every(
    c => c.board_ids.length > 0
  ) && mondayEntities.length > 0;

  return (
    <div className="min-h-screen bg-[#FBFBFA] flex items-center justify-center p-6">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-2xl"
      >
        {/* Progress bar */}
        <div className="mb-8">
          <div className="flex items-center justify-between text-xs text-[#737373] mb-2">
            <span>Step {step} of {totalSteps}</span>
            <span>{Math.round((step / totalSteps) * 100)}% complete</span>
          </div>
          <div className="h-1.5 bg-[#E5E5E5] rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-indigo-600 rounded-full"
              animate={{ width: `${(step / totalSteps) * 100}%` }}
              transition={{ duration: 0.3 }}
            />
          </div>
        </div>

        <AnimatePresence mode="wait">
          {/* ─── Step 1: Entity → Tool Mapping ─── */}
          {step === 1 && (
            <motion.div key="step1" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
              <div className="text-center mb-8">
                <div className="w-12 h-12 bg-indigo-100 rounded-xl flex items-center justify-center mx-auto mb-4">
                  <Database className="w-6 h-6 text-indigo-600" />
                </div>
                <h1 className="text-2xl font-bold tracking-tight mb-2">Welcome to Research Agent</h1>
                <p className="text-[#737373]">Where does your team track these?</p>
              </div>

              <div className="space-y-3">
                {ENTITY_TYPES.map(entity => (
                  <div key={entity.id} className="flex items-center justify-between p-4 bg-white border border-[#E5E5E5] rounded-xl">
                    <div>
                      <div className="font-medium text-sm">{entity.label}</div>
                      <div className="text-xs text-[#737373]">{entity.description}</div>
                    </div>
                    <select
                      value={entityToolMap[entity.id]}
                      onChange={e => setEntityToolMap(prev => ({ ...prev, [entity.id]: e.target.value }))}
                      className="text-sm border border-[#E5E5E5] rounded-lg px-3 py-1.5 bg-white min-w-[160px]"
                    >
                      <option value="">Select tool...</option>
                      {TOOL_OPTIONS.map(tool => (
                        <option key={tool.id} value={tool.id} disabled={!tool.enabled}>
                          {tool.label}{tool.comingSoon ? ' (coming soon)' : ''}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>

              <div className="mt-8 flex justify-end">
                <button
                  onClick={() => {
                    if (!needsMonday) {
                      // No supported tool selected, skip to completion
                      setStep(5);
                    } else {
                      setStep(2);
                    }
                  }}
                  disabled={!canProceedStep1}
                  className="flex items-center gap-2 px-6 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed hover:bg-indigo-700 transition-colors"
                >
                  Continue <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </motion.div>
          )}

          {/* ─── Step 2: Connect Tool ─── */}
          {step === 2 && (
            <motion.div key="step2" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
              <div className="text-center mb-8">
                <div className="w-12 h-12 bg-indigo-100 rounded-xl flex items-center justify-center mx-auto mb-4">
                  <Zap className="w-6 h-6 text-indigo-600" />
                </div>
                <h1 className="text-2xl font-bold tracking-tight mb-2">Connect Monday.com</h1>
                <p className="text-[#737373]">
                  You selected Monday.com for {mondayEntities.length} entity type{mondayEntities.length !== 1 ? 's' : ''}.
                  Let's connect it.
                </p>
              </div>

              <div className="bg-white border border-[#E5E5E5] rounded-xl p-6 space-y-5">
                <div>
                  <label className="block text-sm font-medium mb-1.5">API Token</label>
                  <p className="text-xs text-[#737373] mb-2">
                    Find it in Monday.com → Profile → Admin → API.{' '}
                    <a href="https://support.monday.com/hc/en-us/articles/360005144659-Does-monday-com-have-an-API" target="_blank" rel="noopener noreferrer" className="text-indigo-600 hover:underline inline-flex items-center gap-0.5">
                      How to get your token <ExternalLink className="w-3 h-3" />
                    </a>
                  </p>
                  <input
                    type="password"
                    value={mondayApiKey}
                    onChange={e => { setMondayApiKey(e.target.value); setKeyTestStatus('idle'); }}
                    placeholder="Paste your Monday.com API token"
                    className="w-full px-3 py-2 border border-[#E5E5E5] rounded-lg text-sm"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-1.5">Subdomain (optional)</label>
                  <div className="flex items-center gap-1 text-sm text-[#737373]">
                    <span>https://</span>
                    <input
                      type="text"
                      value={mondaySubdomain}
                      onChange={e => setMondaySubdomain(e.target.value)}
                      placeholder="your-team"
                      className="px-2 py-1.5 border border-[#E5E5E5] rounded-lg text-sm w-40"
                    />
                    <span>.monday.com</span>
                  </div>
                </div>

                <button
                  onClick={testApiKey}
                  disabled={!mondayApiKey.trim() || keyTestStatus === 'testing'}
                  className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-semibold disabled:opacity-40 hover:bg-indigo-700 transition-colors"
                >
                  {keyTestStatus === 'testing' ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                  {keyTestStatus === 'testing' ? 'Testing...' : 'Test Connection'}
                </button>

                {keyTestStatus === 'ok' && (
                  <div className="flex items-center gap-2 text-sm text-green-600">
                    <CheckCircle2 className="w-4 h-4" /> Connected successfully!
                  </div>
                )}
                {keyTestStatus === 'error' && (
                  <div className="flex items-center gap-2 text-sm text-red-600">
                    <AlertCircle className="w-4 h-4" /> {keyError}
                  </div>
                )}
              </div>

              <div className="mt-8 flex justify-between">
                <button onClick={() => setStep(1)} className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-[#737373] hover:text-[#1A1A1A] transition-colors">
                  <ArrowLeft className="w-4 h-4" /> Back
                </button>
                <button
                  onClick={() => setStep(3)}
                  disabled={!canProceedStep2}
                  className="flex items-center gap-2 px-6 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed hover:bg-indigo-700 transition-colors"
                >
                  Continue <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </motion.div>
          )}

          {/* ─── Step 3: Board Mapping ─── */}
          {step === 3 && (
            <motion.div key="step3" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
              <div className="text-center mb-8">
                <div className="w-12 h-12 bg-indigo-100 rounded-xl flex items-center justify-center mx-auto mb-4">
                  <Search className="w-6 h-6 text-indigo-600" />
                </div>
                <h1 className="text-2xl font-bold tracking-tight mb-2">Map your boards</h1>
                <p className="text-[#737373]">Select which Monday.com board contains each entity type.</p>
              </div>

              {boardsLoading ? (
                <div className="flex items-center justify-center py-12 text-[#737373]">
                  <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading boards from Monday.com...
                </div>
              ) : (
                <div className="space-y-4">
                  {mondayEntities.map(entityId => {
                    const entity = ENTITY_TYPES.find(e => e.id === entityId);
                    const cfg = entityConfigs[entityId];
                    return (
                      <div key={entityId} className="bg-white border border-[#E5E5E5] rounded-xl p-4">
                        <div className="font-medium text-sm mb-2">{entity?.label}</div>
                        <select
                          value={cfg?.board_ids[0] || ''}
                          onChange={e => {
                            const boardId = e.target.value;
                            setEntityConfigs(prev => ({
                              ...prev,
                              [entityId]: {
                                ...prev[entityId],
                                board_ids: boardId ? [boardId] : [],
                              },
                            }));
                          }}
                          className="w-full px-3 py-2 border border-[#E5E5E5] rounded-lg text-sm"
                        >
                          <option value="">Select a board...</option>
                          {visibleBoards.map(board => (
                            <option key={board.id} value={board.id}>{board.name}</option>
                          ))}
                        </select>
                      </div>
                    );
                  })}
                </div>
              )}

              <div className="mt-8 flex justify-between">
                <button onClick={() => setStep(2)} className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-[#737373] hover:text-[#1A1A1A] transition-colors">
                  <ArrowLeft className="w-4 h-4" /> Back
                </button>
                <button
                  onClick={() => { setStep(4); saveConfigAndSync(); }}
                  disabled={!canProceedStep3}
                  className="flex items-center gap-2 px-6 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed hover:bg-indigo-700 transition-colors"
                >
                  Sync & Index <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </motion.div>
          )}

          {/* ─── Step 4: Sync & Index ─── */}
          {step === 4 && (
            <motion.div key="step4" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
              <div className="text-center mb-8">
                <div className="w-12 h-12 bg-indigo-100 rounded-xl flex items-center justify-center mx-auto mb-4">
                  {syncStatus === 'done' ? (
                    <CheckCircle2 className="w-6 h-6 text-green-600" />
                  ) : syncStatus === 'error' ? (
                    <AlertCircle className="w-6 h-6 text-red-600" />
                  ) : (
                    <Loader2 className="w-6 h-6 text-indigo-600 animate-spin" />
                  )}
                </div>
                <h1 className="text-2xl font-bold tracking-tight mb-2">
                  {syncStatus === 'syncing' && 'Syncing your data...'}
                  {syncStatus === 'done' && 'Data synced!'}
                  {syncStatus === 'error' && 'Sync failed'}
                  {syncStatus === 'idle' && 'Preparing sync...'}
                </h1>
                <p className="text-[#737373]">
                  {syncStatus === 'syncing' && 'Pulling data from Monday.com and indexing for search. This may take a minute.'}
                  {syncStatus === 'done' && syncStats && `${syncStats.fetched} items fetched, ${syncStats.embedded} chunks indexed.`}
                  {syncStatus === 'error' && syncError}
                </p>
              </div>

              {syncStatus === 'syncing' && (
                <div className="max-w-sm mx-auto">
                  <div className="h-2 bg-[#E5E5E5] rounded-full overflow-hidden">
                    <motion.div
                      className="h-full bg-indigo-600 rounded-full"
                      animate={{ width: ['0%', '60%', '80%', '95%'] }}
                      transition={{ duration: 30, ease: 'easeOut' }}
                    />
                  </div>
                </div>
              )}

              <div className="mt-8 flex justify-end">
                {syncStatus === 'done' && (
                  <button
                    onClick={() => setStep(5)}
                    className="flex items-center gap-2 px-6 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors"
                  >
                    Continue <ChevronRight className="w-4 h-4" />
                  </button>
                )}
                {syncStatus === 'error' && (
                  <div className="flex gap-3">
                    <button
                      onClick={() => setStep(3)}
                      className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-[#737373] hover:text-[#1A1A1A] transition-colors"
                    >
                      <ArrowLeft className="w-4 h-4" /> Back
                    </button>
                    <button
                      onClick={() => { setSyncStatus('idle'); saveConfigAndSync(); }}
                      className="flex items-center gap-2 px-6 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors"
                    >
                      Retry
                    </button>
                  </div>
                )}
              </div>
            </motion.div>
          )}

          {/* ─── Step 5: Complete ─── */}
          {step === 5 && (
            <motion.div key="step5" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}>
              <div className="text-center mb-8">
                <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
                  <CheckCircle2 className="w-8 h-8 text-green-600" />
                </div>
                <h1 className="text-2xl font-bold tracking-tight mb-2">You're all set!</h1>
                <p className="text-[#737373]">
                  {syncStats
                    ? `${syncStats.fetched} items from Monday.com are indexed and ready for research.`
                    : 'Your Research Agent is ready. Connect integrations anytime from Settings.'}
                </p>
              </div>

              <div className="bg-white border border-[#E5E5E5] rounded-xl p-6">
                <label className="block text-sm font-medium mb-3">Ask your first question</label>
                <div className="relative">
                  <input
                    type="text"
                    value={firstQuery}
                    onChange={e => setFirstQuery(e.target.value)}
                    placeholder={getSuggestedQuery()}
                    className="w-full px-4 py-3 pr-12 border border-[#E5E5E5] rounded-xl text-sm"
                    onKeyDown={e => e.key === 'Enter' && handleComplete()}
                  />
                  <button
                    onClick={handleComplete}
                    className="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 bg-indigo-600 text-white rounded-lg flex items-center justify-center hover:bg-indigo-700 transition-colors"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
                <p className="text-xs text-[#737373] mt-2">
                  Press Enter or click the arrow to start your first research query.
                </p>
              </div>

              <div className="mt-4 text-center">
                <button
                  onClick={handleComplete}
                  className="text-sm text-[#737373] hover:text-[#1A1A1A] transition-colors"
                >
                  Skip — go to dashboard
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  );
}
