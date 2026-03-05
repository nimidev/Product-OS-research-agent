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

// Canonical Product OS fields per entity type (for field mapping step)
const PRODUCT_OS_ENTITY_FIELDS: Record<string, string[]> = {
  feature_request: ['title', 'description', 'customer', 'priority', 'status', 'votes'],
  roadmap_item: ['title', 'description', 'target_start', 'target_end', 'status', 'priority'],
  support_ticket: ['title', 'description', 'customer', 'priority', 'status', 'resolution'],
  bug: ['title', 'description', 'severity', 'status', 'affected_version', 'priority'],
  prd: ['title', 'overview', 'target_users', 'requirements', 'success_metrics', 'status'],
  meeting_note: ['title', 'transcript', 'summary', 'attendees', 'date', 'tags'],
};

const formatEntityTypeLabel = (entityType: string) =>
  entityType.split('_').map(p => p.charAt(0).toUpperCase() + p.slice(1)).join(' ');

interface OnboardingWizardProps {
  onComplete: () => void;
}

// Step indices: 1=entity tool, 2=API, 3=boards, 4..(4+N-1)=field mapping per entity, 4+N=sync, 5+N=first query
function getStepIndices(mondayCount: number) {
  const firstFieldStep = 4;
  const lastFieldStep = 4 + Math.max(0, mondayCount - 1);
  const syncStep = 4 + mondayCount;
  const completeStep = 5 + mondayCount;
  const total = mondayCount > 0 ? 5 + mondayCount : 2;
  return { firstFieldStep, lastFieldStep, syncStep, completeStep, total };
}

export default function OnboardingWizard({ onComplete }: OnboardingWizardProps) {
  const [step, setStep] = useState(1);

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

  // Step 5: Sync, Step 6: First query
  const [firstQuery, setFirstQuery] = useState('');
  const [loadingSuggestionsForEntityIds, setLoadingSuggestionsForEntityIds] = useState<Set<string>>(() => new Set());

  const mondayEntities = Object.entries(entityToolMap)
    .filter(([, tool]) => tool === 'monday')
    .map(([entityId]) => entityId);

  const hasAnyToolSelected = Object.values(entityToolMap).some(v => v && v !== 'none' && v !== '');
  const needsMonday = mondayEntities.length > 0;
  const stepIndices = getStepIndices(mondayEntities.length);
  const totalSteps = needsMonday ? stepIndices.total : 2;

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

  // Per-entity ref: which entity IDs have had suggestions applied (prevents re-fetch)
  const suggestionsAppliedForEntityRef = React.useRef<Set<string>>(new Set());

  // Preload suggestions for all entities with a board when we're in field-mapping steps (avoids lag on "Continue")
  useEffect(() => {
    const { firstFieldStep, lastFieldStep } = getStepIndices(mondayEntities.length);
    if (!needsMonday || step < firstFieldStep || step > lastFieldStep || boards.length === 0) return;

    const toFetch: { entityId: string; board: MondayBoardSchema }[] = [];
    for (const entityId of mondayEntities) {
      if (suggestionsAppliedForEntityRef.current.has(entityId)) continue;
      const cfg = entityConfigs[entityId];
      const boardId = cfg?.board_ids?.[0];
      const board = boardId ? visibleBoards.find((b) => b.id === boardId) : null;
      if (board?.columns?.length) toFetch.push({ entityId, board });
    }
    if (toFetch.length === 0) return;

    for (const { entityId, board } of toFetch) {
      suggestionsAppliedForEntityRef.current.add(entityId);
      setLoadingSuggestionsForEntityIds((prev) => new Set(prev).add(entityId));
      (async () => {
        try {
          const res = await fetch(`${RESEARCH_API_URL}/integrations/monday/suggest-field-mapping`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              entity_type: entityId,
              source_columns: board.columns.map((c) => ({ id: c.id, title: (c.title ?? c.id) || c.id })),
            }),
          });
          if (res.ok) {
            const data = await res.json();
            const field_mappings = data.field_mappings || {};
            if (Object.keys(field_mappings).length > 0) {
              setEntityConfigs((prev) => {
                const cur = prev[entityId] || { entity_type: entityId, board_ids: [], direction: 'monday_to_os' as MondayDirection, field_mappings: {} };
                return { ...prev, [entityId]: { ...cur, field_mappings: { ...field_mappings } } };
              });
            }
          }
        } finally {
          setLoadingSuggestionsForEntityIds((prev) => {
            const next = new Set(prev);
            next.delete(entityId);
            return next;
          });
        }
      })();
    }
  }, [step, needsMonday, boards.length, mondayEntities, entityConfigs, visibleBoards]);

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
      // Save key/subdomain first so GET /schema can read from config (avoids custom headers/CORS)
      if (mondayApiKey?.trim()) {
        await fetch(`${RESEARCH_API_URL}/integrations/monday`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            enabled: true,
            api_key: mondayApiKey.trim(),
            subdomain: mondaySubdomain?.trim() || undefined,
            board_ids: [],
            entity_mappings: {},
            entity_configs: entityConfigs,
          }),
        });
      }
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
                      setStep(2); // totalSteps=2; step 2 is the Complete screen
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

          {/* ─── Step 2: Connect Tool (only when Monday selected) ─── */}
          {needsMonday && step === 2 && (
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
                  onClick={() => setStep(4)}
                  disabled={!canProceedStep3}
                  className="flex items-center gap-2 px-6 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed hover:bg-indigo-700 transition-colors"
                >
                  Continue <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </motion.div>
          )}

          {/* ─── Steps 4..(4+N-1): Field mapping (one step per entity) ─── */}
          {needsMonday && step >= stepIndices.firstFieldStep && step <= stepIndices.lastFieldStep && (() => {
            const entityIndex = step - stepIndices.firstFieldStep;
            const entityId = mondayEntities[entityIndex];
            const entity = ENTITY_TYPES.find(e => e.id === entityId);
            const cfg = entityConfigs[entityId];
            const boardId = cfg?.board_ids?.[0];
            const board = boardId ? visibleBoards.find(b => b.id === boardId) : null;
            const canonicalFields = PRODUCT_OS_ENTITY_FIELDS[entityId] || [];
            const fieldMappings = cfg?.field_mappings || {};
            const isLastFieldStep = step === stepIndices.lastFieldStep;
            return (
            <motion.div key={`step4-${entityId}`} initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
              <div className="text-center mb-6">
                <div className="w-12 h-12 bg-indigo-100 rounded-xl flex items-center justify-center mx-auto mb-4">
                  <Zap className="w-6 h-6 text-indigo-600" />
                </div>
                <h1 className="text-2xl font-bold tracking-tight mb-2">Map fields: {entity?.label}</h1>
                <p className="text-[#737373]">Map Monday.com columns to Product OS fields for better search. Suggestions are applied automatically.</p>
              </div>

              <div className="space-y-6">
                <div className="bg-white border border-[#E5E5E5] rounded-xl p-4 relative min-h-[200px]">
                  {loadingSuggestionsForEntityIds.has(entityId) && (
                    <div className="absolute inset-0 rounded-xl bg-white/95 flex flex-col items-center justify-center gap-3 z-10">
                      <Loader2 className="w-8 h-8 text-indigo-600 animate-spin" />
                      <p className="text-sm font-medium text-[#1A1A1A]">Matching your board columns</p>
                      <p className="text-xs text-[#737373]">This usually takes a moment</p>
                    </div>
                  )}
                  <div className="mb-3">
                    <div className="font-medium text-sm">{entity?.label}</div>
                    {board && <div className="text-xs text-[#737373]">Board: {board.name}</div>}
                  </div>
                  {board?.columns?.length ? (
                    <div className="space-y-2">
                      {canonicalFields.map(canonicalName => {
                        const mappedColumnId = Object.entries(fieldMappings).find(([, t]) => t === canonicalName)?.[0];
                        const mappedColumn = mappedColumnId && board.columns.find(c => c.id === mappedColumnId);
                        return (
                          <div key={canonicalName} className="flex items-center gap-2 text-sm">
                            <span className="w-32 font-mono text-xs text-[#737373] shrink-0">{formatEntityTypeLabel(entityId)}.{canonicalName}</span>
                            <span className="text-[#737373]">→</span>
                            <select
                              value={mappedColumnId || ''}
                              onChange={e => {
                                const colId = e.target.value;
                                setEntityConfigs(prev => {
                                  const cur = prev[entityId] || { entity_type: entityId, board_ids: [], direction: 'monday_to_os' as MondayDirection, field_mappings: {} };
                                  const next = { ...(cur.field_mappings || {}) };
                                  Object.keys(next).forEach(k => { if (next[k] === canonicalName) delete next[k]; });
                                  if (colId) next[colId] = canonicalName;
                                  return { ...prev, [entityId]: { ...cur, field_mappings: next } };
                                });
                              }}
                              className="flex-1 text-xs border border-[#E5E5E5] rounded-md px-2 py-1.5 bg-white"
                            >
                              <option value="">Not mapped</option>
                              {board.columns.map(col => (
                                <option key={col.id} value={col.id}>{col.title || col.id}</option>
                              ))}
                            </select>
                            {mappedColumn && <span className="text-xs text-[#737373] truncate max-w-[120px]">{mappedColumn.title || mappedColumn.id}</span>}
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="text-xs text-[#737373]">Select a board in the previous step to map fields.</p>
                  )}
                </div>
              </div>

              <div className="mt-8 flex justify-between">
                <button
                  onClick={() => setStep(step === stepIndices.firstFieldStep ? 3 : step - 1)}
                  className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-[#737373] hover:text-[#1A1A1A] transition-colors"
                >
                  <ArrowLeft className="w-4 h-4" /> Back
                </button>
                <button
                  onClick={() => {
                    if (isLastFieldStep) {
                      setStep(stepIndices.syncStep);
                      saveConfigAndSync();
                    } else {
                      setStep(step + 1);
                    }
                  }}
                  className="flex items-center gap-2 px-6 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors"
                >
                  {isLastFieldStep ? <>Sync & Index <ChevronRight className="w-4 h-4" /></> : <>Continue <ChevronRight className="w-4 h-4" /></>}
                </button>
              </div>
            </motion.div>
            );
          })()}

          {/* ─── Sync & Index ─── */}
          {needsMonday && step === stepIndices.syncStep && (
            <motion.div key="step5" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
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
                    onClick={() => setStep(stepIndices.completeStep)}
                    className="flex items-center gap-2 px-6 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors"
                  >
                    Continue <ChevronRight className="w-4 h-4" />
                  </button>
                )}
                {syncStatus === 'error' && (
                  <div className="flex gap-3">
                    <button
                      onClick={() => setStep(stepIndices.lastFieldStep)}
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

          {/* ─── Complete (step 2 when !needsMonday, else step 5+N) ─── */}
          {((!needsMonday && step === 2) || (needsMonday && step === stepIndices.completeStep)) && (
            <motion.div key="step6" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}>
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
