import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  CheckCircle2,
  ChevronRight,
  ChevronDown,
  Loader2,
  AlertCircle,
  Database,
  ArrowLeft,
  Search,
  Zap,
  ExternalLink,
} from 'lucide-react';
import {
  MondayBoardSchema,
  MondayEntityMappingConfig,
  MondayDirection,
  JiraEntityMappingConfig,
  JiraDirection,
  JiraProjectInfo,
  JiraIssueTypeInfo,
  JiraFieldInfo,
  JiraIntegrationConfigResponse,
} from './types';

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
  { id: 'jira', label: 'Jira', enabled: true },
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

/** Human-readable Jira field type for dropdown (show type instead of API id). */
function jiraFieldTypeLabel(schemaType: string | null | undefined): string {
  if (!schemaType) return 'other';
  const t = schemaType.toLowerCase();
  const map: Record<string, string> = {
    string: 'text',
    number: 'number',
    date: 'date',
    datetime: 'date',
    array: 'list',
    option: 'select',
    user: 'user',
    project: 'project',
    priority: 'priority',
    status: 'status',
    resolution: 'resolution',
    issuetype: 'issue type',
    timetracking: 'time',
  };
  return map[t] ?? t;
}

/** Autocomplete dropdown for Jira field selection: sorted by name, type in brackets, type-to-filter. */
function JiraFieldSelect({
  value,
  onChange,
  options,
  placeholder = 'Not mapped',
  id,
}: {
  value: string;
  onChange: (fieldId: string) => void;
  options: JiraFieldInfo[];
  placeholder?: string;
  id?: string;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const containerRef = React.useRef<HTMLDivElement>(null);

  const sorted = React.useMemo(
    () => [...options].sort((a, b) => (a.name || '').localeCompare(b.name || '', undefined, { sensitivity: 'base' })),
    [options]
  );
  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return sorted;
    return sorted.filter(
      f =>
        (f.name || '').toLowerCase().includes(q) ||
        jiraFieldTypeLabel(f.schema_type).toLowerCase().includes(q) ||
        (f.id || '').toLowerCase().includes(q)
    );
  }, [sorted, query]);

  const selected = options.find(f => f.id === value);
  const displayText = selected
    ? `${selected.name} (${jiraFieldTypeLabel(selected.schema_type)})${selected.custom ? ' [custom]' : ''}`
    : placeholder;

  React.useEffect(() => {
    if (!isOpen) return;
    const onDocClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setIsOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [isOpen]);

  const handleSelect = (fieldId: string) => {
    onChange(fieldId);
    setQuery('');
    setIsOpen(false);
  };

  return (
    <div ref={containerRef} className="relative flex-1">
      <button
        type="button"
        id={id}
        onClick={() => setIsOpen(o => !o)}
        className="w-full text-left text-xs border border-[#E5E5E5] rounded-md px-2 py-1.5 bg-white flex items-center justify-between gap-1 hover:border-[#A3A3A3] focus:outline-none focus:ring-1 focus:ring-indigo-500"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label="Select Jira field"
      >
        <span className={value ? 'text-[#1A1A1A]' : 'text-[#737373]'}>{displayText}</span>
        <ChevronDown className="w-3.5 h-3.5 text-[#737373] shrink-0" />
      </button>
      {isOpen && (
        <div className="absolute z-10 mt-1 w-full bg-white border border-[#E5E5E5] rounded-md shadow-lg max-h-56 flex flex-col">
          <input
            type="text"
            autoFocus
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Escape') {
                setQuery('');
                setIsOpen(false);
              }
            }}
            placeholder="Type to search..."
            className="px-2 py-1.5 text-xs border-b border-[#E5E5E5] rounded-t-md focus:outline-none focus:ring-0"
          />
          <ul
            className="overflow-auto py-1 max-h-44"
            role="listbox"
          >
            <li
              role="option"
              aria-selected={!value}
              onClick={() => handleSelect('')}
              onKeyDown={e => { if (e.key === 'Enter') handleSelect(''); }}
              tabIndex={0}
              className={`px-2 py-1.5 text-xs cursor-pointer border-b border-[#E5E5E5] ${!value ? 'bg-indigo-50 text-indigo-800' : 'hover:bg-[#F5F5F5]'} text-[#737373]`}
            >
              Not mapped
            </li>
            {filtered.length === 0 ? (
              <li className="px-2 py-1.5 text-xs text-[#737373]">No matching field</li>
            ) : (
              filtered.map(f => {
                const label = `${f.name} (${jiraFieldTypeLabel(f.schema_type)})${f.custom ? ' [custom]' : ''}`;
                const isSelected = f.id === value;
                return (
                  <li
                    key={f.id}
                    role="option"
                    aria-selected={isSelected}
                    onClick={() => handleSelect(f.id)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') handleSelect(f.id);
                    }}
                    tabIndex={0}
                    className={`px-2 py-1.5 text-xs cursor-pointer ${isSelected ? 'bg-indigo-50 text-indigo-800' : 'hover:bg-[#F5F5F5]'} ${!f.name ? 'text-[#737373]' : ''}`}
                  >
                    {label}
                  </li>
                );
              })
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

interface OnboardingWizardProps {
  onComplete: () => void;
  /** When true, show only Jira flow for editing mapping from Integrations page. */
  embeddedJira?: boolean;
  /** Current Jira config when editing from Integrations (entity_configs, access_token_set, etc.). */
  initialJiraConfig?: JiraIntegrationConfigResponse | null;
  /** Called when user saves in embedded Jira mode (after PUT). */
  onJiraEditComplete?: () => void;
  /** Called when user cancels (e.g. Back on Connect step) in embedded Jira mode. */
  onJiraEditCancel?: () => void;
}

// Step indices for Monday: 1=entity tool, 2=API, 3=boards, 4..(4+N-1)=field mapping per entity, 4+N=sync, 5+N=first query
function getStepIndices(mondayCount: number) {
  const firstFieldStep = 4;
  const lastFieldStep = 4 + Math.max(0, mondayCount - 1);
  const syncStep = 4 + mondayCount;
  const completeStep = 5 + mondayCount;
  const total = mondayCount > 0 ? 5 + mondayCount : 2;
  return { firstFieldStep, lastFieldStep, syncStep, completeStep, total };
}

// Step indices for Jira: mirrors Monday layout
// 1=entity tool, 2=connect, 3=project+issue types, 4..(4+N-1)=field mapping per entity, 4+N=sync, 5+N=first query
function getJiraStepIndices(jiraCount: number) {
  const firstFieldStep = 4;
  const lastFieldStep = 4 + Math.max(0, jiraCount - 1);
  const syncStep = 4 + jiraCount;
  const completeStep = 5 + jiraCount;
  const total = jiraCount > 0 ? 5 + jiraCount : 2;
  return { firstFieldStep, lastFieldStep, syncStep, completeStep, total };
}

export default function OnboardingWizard({
  onComplete,
  embeddedJira = false,
  initialJiraConfig = null,
  onJiraEditComplete,
  onJiraEditCancel,
}: OnboardingWizardProps) {
  const [step, setStep] = useState(() => {
    if (!embeddedJira || !initialJiraConfig) return 1;
    const configs = initialJiraConfig.entity_configs || {};
    const hasEntities = Object.keys(configs).length > 0;
    if (!hasEntities) return 1; // let user select entities first
    return initialJiraConfig.access_token_set ? 3 : 2;
  });
  const embeddedJiraInitDone = React.useRef(false);

  // Step 1: entity → tool mapping (restore after Jira OAuth return; localStorage so OAuth tab can read what wizard tab saved)
  const [entityToolMap, setEntityToolMap] = useState<EntityToolMapping>(() => {
    if (embeddedJira && initialJiraConfig?.entity_configs) {
      const configs = initialJiraConfig.entity_configs;
      return Object.fromEntries(ENTITY_TYPES.map(e => [e.id, configs[e.id] ? 'jira' : '']));
    }
    try {
      const saved = localStorage.getItem('jira_oauth_entity_tool_map');
      if (saved) {
        const parsed = JSON.parse(saved) as Record<string, string>;
        if (parsed && typeof parsed === 'object') {
          localStorage.removeItem('jira_oauth_entity_tool_map');
          return { ...Object.fromEntries(ENTITY_TYPES.map(e => [e.id, ''])), ...parsed };
        }
      }
    } catch { /* ignore */ }
    return Object.fromEntries(ENTITY_TYPES.map(e => [e.id, '']));
  });

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
  const [syncStats, setSyncStats] = useState<{ fetched: number; embedded: number; total_entities?: number } | null>(null);
  const [syncError, setSyncError] = useState('');

  // Step 5: Sync, Step 6: First query
  const [firstQuery, setFirstQuery] = useState('');
  const [loadingSuggestionsForEntityIds, setLoadingSuggestionsForEntityIds] = useState<Set<string>>(() => new Set());

  // --- Jira-specific state ---
  const [jiraClientId, setJiraClientId] = useState('');
  const [jiraClientSecret, setJiraClientSecret] = useState('');
  const [jiraClientSecretSet, setJiraClientSecretSet] = useState(false);
  const [jiraAccessToken, setJiraAccessToken] = useState('');
  const [jiraCloudId, setJiraCloudId] = useState('');
  const [jiraSiteUrl, setJiraSiteUrl] = useState('');
  const [jiraKeyTestStatus, setJiraKeyTestStatus] = useState<'idle' | 'testing' | 'ok' | 'error'>('idle');
  const [jiraKeyError, setJiraKeyError] = useState('');
  const [jiraOAuthSaveError, setJiraOAuthSaveError] = useState('');
  const [jiraConfigLoaded, setJiraConfigLoaded] = useState(false);
  const [jiraOAuthReady, setJiraOAuthReady] = useState(true);
  const [jiraOAuthNotReadyMessage, setJiraOAuthNotReadyMessage] = useState('');
  const [jiraShowAdvanced, setJiraShowAdvanced] = useState(false);
  const jiraEntityConfigsRef = React.useRef<Record<string, JiraEntityMappingConfig>>({});

  const [jiraProjects, setJiraProjects] = useState<JiraProjectInfo[]>([]);
  const [jiraIssueTypes, setJiraIssueTypes] = useState<JiraIssueTypeInfo[]>([]);
  const [jiraFields, setJiraFields] = useState<JiraFieldInfo[]>([]);
  const [jiraProjectsLoading, setJiraProjectsLoading] = useState(false);
  const [jiraEntityConfigs, setJiraEntityConfigs] = useState<Record<string, JiraEntityMappingConfig>>(() =>
    embeddedJira && initialJiraConfig?.entity_configs ? initialJiraConfig.entity_configs : {}
  );
  /** When true, step 1 shows Jira-only entity list (no Monday/Notion dropdown). Set when opening "Add or remove entity types" from Jira flow. */
  const [entitySelectorJiraOnly, setEntitySelectorJiraOnly] = useState(false);

  const mondayEntities = Object.entries(entityToolMap)
    .filter(([, tool]) => tool === 'monday')
    .map(([entityId]) => entityId);

  const jiraEntities = Object.entries(entityToolMap)
    .filter(([, tool]) => tool === 'jira')
    .map(([entityId]) => entityId);

  jiraEntityConfigsRef.current = jiraEntityConfigs;

  // When embedded Jira edit: init from existing config (entity map, configs, start at Connect or Project step if we have entities)
  useEffect(() => {
    if (!embeddedJira || !initialJiraConfig || embeddedJiraInitDone.current) return;
    embeddedJiraInitDone.current = true;
    const configs = initialJiraConfig.entity_configs || {};
    const map: EntityToolMapping = Object.fromEntries(
      ENTITY_TYPES.map(e => [e.id, configs[e.id] ? 'jira' : ''])
    );
    setEntityToolMap(map);
    setJiraEntityConfigs(configs);
    if (Object.keys(configs).length > 0) setStep(initialJiraConfig.access_token_set ? 3 : 2);
  }, [embeddedJira, initialJiraConfig]);

  // When embedded and we have a pending OAuth token in sessionStorage (same-tab return): show step 2 so we apply and persist it
  useEffect(() => {
    if (!embeddedJira) return;
    try {
      if (typeof window !== 'undefined' && window.sessionStorage?.getItem('jira_oauth_token')) setStep(2);
    } catch { /* ignore */ }
  }, [embeddedJira]);

  // When embedded and already connected: skip Connect (step 2) and go straight to project mapping.
  // Do not skip if there is a pending OAuth token in sessionStorage (same-tab return from Integrations).
  useEffect(() => {
    if (!embeddedJira || step !== 2 || !initialJiraConfig?.access_token_set) return;
    try {
      if (typeof window !== 'undefined' && window.sessionStorage?.getItem('jira_oauth_token')) return;
    } catch { /* ignore */ }
    setStep(3);
  }, [embeddedJira, step, initialJiraConfig?.access_token_set]);

  const hasAnyToolSelected = Object.values(entityToolMap).some(v => v && v !== 'none' && v !== '');
  const needsMonday = mondayEntities.length > 0;
  const needsJira = jiraEntities.length > 0;
  const stepIndices = getStepIndices(mondayEntities.length);
  const jiraStepIndices = getJiraStepIndices(jiraEntities.length);

  // Active tool determines which flow we show (Monday takes priority if both, but usually only one)
  const activeTool = needsMonday ? 'monday' : needsJira ? 'jira' : 'none';
  const totalSteps = activeTool === 'monday'
    ? stepIndices.total
    : activeTool === 'jira'
    ? jiraStepIndices.total
    : 2;

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

  // Initialize Jira entity configs when Jira entities change
  useEffect(() => {
    const newConfigs: Record<string, JiraEntityMappingConfig> = {};
    for (const entityId of jiraEntities) {
      newConfigs[entityId] = jiraEntityConfigs[entityId] || {
        entity_type: entityId,
        project_key: '',
        issue_type_names: [],
        board_id: null,
        sprint_id: null,
        backlog_only: false,
        direction: 'jira_to_os' as JiraDirection,
        field_mappings: { summary: 'title' },
      };
    }
    setJiraEntityConfigs(newConfigs);
  }, [entityToolMap]);

  // Load boards when entering step 3 (Monday)
  useEffect(() => {
    if (step === 3 && needsMonday && boards.length === 0 && !boardsLoading) {
      loadBoards();
    }
  }, [step]);

  // Load Jira projects when entering step 3 (Jira)
  useEffect(() => {
    if (step === 3 && needsJira && !needsMonday && jiraProjects.length === 0 && !jiraProjectsLoading) {
      loadJiraSchema();
    }
  }, [step]);

  // After OAuth: read token/cloud_id/site_url or error from sessionStorage; persist to server and mark connected
  const applyJiraOAuthFromStorage = React.useCallback(() => {
    try {
      const errorMsg = sessionStorage.getItem('jira_oauth_error_message');
      if (errorMsg) {
        setJiraOAuthSaveError(errorMsg);
        sessionStorage.removeItem('jira_oauth_error_message');
        return;
      }
      const token = sessionStorage.getItem('jira_oauth_token');
      const cloudId = sessionStorage.getItem('jira_oauth_cloud_id');
      const siteUrl = sessionStorage.getItem('jira_oauth_site_url');
      if (token) {
        setJiraAccessToken(token);
        if (cloudId) setJiraCloudId(cloudId);
        if (siteUrl) setJiraSiteUrl(siteUrl);
        setJiraKeyTestStatus('ok');
        setJiraOAuthSaveError('');
        sessionStorage.removeItem('jira_oauth_token');
        sessionStorage.removeItem('jira_oauth_cloud_id');
        sessionStorage.removeItem('jira_oauth_site_url');
        // Persist token/cloud_id/site_url to server so sync and search work
        const body: Record<string, unknown> = {
          enabled: true,
          entity_configs: jiraEntityConfigsRef.current,
          access_token: token,
          cloud_id: cloudId ?? '',
          site_url: siteUrl ?? '',
        };
        fetch(`${RESEARCH_API_URL}/integrations/jira`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        }).catch(() => {});
      }
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    applyJiraOAuthFromStorage();
  }, [applyJiraOAuthFromStorage]);

  // Restore step after Jira OAuth redirect (new-tab return): land on step 2 so user can continue to mapping (localStorage so OAuth tab sees what wizard tab saved)
  useEffect(() => {
    try {
      const saved = localStorage.getItem('jira_oauth_return_step');
      if (!saved) return;
      const stepNum = parseInt(saved, 10);
      if (Number.isFinite(stepNum) && stepNum >= 1) {
        setStep(stepNum);
      }
      localStorage.removeItem('jira_oauth_return_step');
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (!needsJira || step !== 2) return;
    const onResult = () => applyJiraOAuthFromStorage();
    window.addEventListener('focus', onResult);
    window.addEventListener('jira_oauth_result', onResult);
    return () => {
      window.removeEventListener('focus', onResult);
      window.removeEventListener('jira_oauth_result', onResult);
    };
  }, [needsJira, step, applyJiraOAuthFromStorage]);

  // Load existing Jira config and OAuth-ready state when on Connect Jira step
  useEffect(() => {
    if (!needsJira || step !== 2 || jiraConfigLoaded) return;
    let cancelled = false;
    (async () => {
      try {
        const [configRes, readyRes] = await Promise.all([
          fetch(`${RESEARCH_API_URL}/integrations/jira`),
          fetch(`${RESEARCH_API_URL}/integrations/jira/oauth/ready`),
        ]);
        if (cancelled) return;
        if (configRes.ok) {
          const data = await configRes.json();
          if (data.client_id) setJiraClientId(data.client_id);
          if (data.cloud_id) setJiraCloudId(data.cloud_id);
          if (data.site_url) setJiraSiteUrl(data.site_url);
          if (data.client_secret_set) setJiraClientSecretSet(true);
        }
        if (readyRes.ok) {
          const readyData = await readyRes.json();
          setJiraOAuthReady(!!readyData.ready);
          setJiraOAuthNotReadyMessage(readyData.message || '');
        }
      } catch {
        // ignore
      } finally {
        if (!cancelled) setJiraConfigLoaded(true);
      }
    })();
    return () => { cancelled = true; };
  }, [needsJira, step, jiraConfigLoaded]);

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

  async function testJiraConnection() {
    setJiraKeyTestStatus('testing');
    setJiraKeyError('');
    try {
      const res = await fetch(`${RESEARCH_API_URL}/integrations/jira/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ access_token: jiraAccessToken, cloud_id: jiraCloudId }),
      });
      if (res.ok) {
        setJiraKeyTestStatus('ok');
      } else {
        setJiraKeyTestStatus('error');
        setJiraKeyError('Invalid token or Cloud ID. Check your Jira connection.');
      }
    } catch {
      setJiraKeyTestStatus('error');
      setJiraKeyError('Network error — check that the API server is running.');
    }
  }

  function buildJiraPutBody(): Record<string, unknown> {
    const entity_configs = Object.fromEntries(
      jiraEntities.filter(id => jiraEntityConfigs[id]).map(id => [id, jiraEntityConfigs[id]])
    );
    const body: Record<string, unknown> = {
      enabled: true,
      entity_configs,
    };
    if (jiraCloudId?.trim()) body.cloud_id = jiraCloudId.trim();
    if (jiraSiteUrl?.trim()) body.site_url = jiraSiteUrl.trim();
    if (jiraAccessToken?.trim()) body.access_token = jiraAccessToken.trim();
    if (jiraClientId?.trim()) body.client_id = jiraClientId.trim();
    if (jiraClientSecret?.trim()) body.client_secret = jiraClientSecret.trim();
    return body;
  }

  async function handleConnectWithJiraOAuth() {
    setJiraOAuthSaveError('');
    const useFormCreds = !jiraOAuthReady && jiraClientId.trim() && (jiraClientSecret.trim() || jiraClientSecretSet);
    if (!jiraOAuthReady && !useFormCreds) {
      setJiraOAuthSaveError(jiraOAuthNotReadyMessage || 'Enter Client ID and Client Secret below, or set them in the server environment.');
      return;
    }
    try {
      if (useFormCreds) {
        const putRes = await fetch(`${RESEARCH_API_URL}/integrations/jira`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(buildJiraPutBody()),
        });
        if (!putRes.ok) {
          const err = await putRes.json().catch(() => ({}));
          throw new Error(err.detail || putRes.statusText || 'Failed to save');
        }
        setJiraClientSecretSet(true);
      }
      localStorage.setItem('jira_oauth_return_step', '2');
      localStorage.setItem('jira_oauth_entity_tool_map', JSON.stringify(entityToolMap));
      const returnTo = embeddedJira ? 'integrations' : 'onboarding';
      window.open(`${RESEARCH_API_URL}/integrations/jira/oauth/authorize?return_to=${encodeURIComponent(returnTo)}`, '_blank', 'noopener,noreferrer');
    } catch (e: unknown) {
      setJiraOAuthSaveError(e instanceof Error ? e.message : 'Failed to start OAuth.');
    }
  }

  async function loadJiraSchema(projectKey?: string) {
    setJiraProjectsLoading(true);
    try {
      // Save credentials first
      if (jiraAccessToken?.trim() && jiraCloudId?.trim()) {
        await fetch(`${RESEARCH_API_URL}/integrations/jira`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(buildJiraPutBody()),
        });
      }
      const url = projectKey
        ? `${RESEARCH_API_URL}/integrations/jira/schema?project_key=${encodeURIComponent(projectKey)}`
        : `${RESEARCH_API_URL}/integrations/jira/schema`;
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        setJiraProjects(data.projects || []);
        if (data.issue_types?.length) setJiraIssueTypes(data.issue_types);
        if (data.fields?.length) setJiraFields(data.fields);
      }
    } catch {
      // projects will stay empty
    }
    setJiraProjectsLoading(false);
  }

  /** Clear stored Jira token/cloud_id on server and locally, then go to Connect Jira step for a fresh OAuth. */
  async function clearJiraConnectionAndGoToConnect() {
    try {
      await fetch(`${RESEARCH_API_URL}/integrations/jira`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...buildJiraPutBody(),
          access_token: '',
          cloud_id: '',
          site_url: '',
        }),
      });
    } catch {
      // ignore
    }
    setJiraAccessToken('');
    setJiraCloudId('');
    setJiraSiteUrl('');
    setJiraKeyTestStatus('idle');
    setSyncStatus('idle');
    setSyncError('');
    setStep(2);
  }

  async function saveJiraConfigAndSync() {
    setSyncStatus('syncing');
    setSyncError('');
    try {
      const putRes = await fetch(`${RESEARCH_API_URL}/integrations/jira`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildJiraPutBody()),
      });

      if (!putRes.ok) throw new Error('Failed to save Jira configuration');

      const prepRes = await fetch(`${RESEARCH_API_URL}/integrations/jira/prepare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      const data = await prepRes.json().catch(() => ({}));
      setSyncStats({
        fetched: data.fetched ?? 0,
        embedded: data.embedded ?? 0,
        total_entities: typeof data.total_entities === 'number' ? data.total_entities : undefined,
      });
      if (prepRes.ok && data.ok !== false) {
        setSyncStatus('done');
      } else {
        setSyncStatus('error');
        setSyncError(data.detail || (prepRes.ok ? 'Jira sync failed' : 'Sync request failed. Check server logs.'));
      }
    } catch (e: any) {
      setSyncStatus('error');
      setSyncError(e.message || 'Something went wrong during Jira sync.');
    }
  }

  /** Run Jira prepare/sync only (no PUT). Used in embedded flow after save. */
  async function saveJiraPrepareOnly() {
    setSyncStatus('syncing');
    setSyncError('');
    try {
      const prepRes = await fetch(`${RESEARCH_API_URL}/integrations/jira/prepare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await prepRes.json().catch(() => ({}));
      setSyncStats({
        fetched: data.fetched ?? 0,
        embedded: data.embedded ?? 0,
        total_entities: typeof data.total_entities === 'number' ? data.total_entities : undefined,
      });
      if (prepRes.ok && data.ok !== false) {
        setSyncStatus('done');
      } else {
        setSyncStatus('error');
        setSyncError(data.detail || (prepRes.ok ? 'Jira sync failed' : 'Sync request failed. Check server logs.'));
      }
    } catch (e: any) {
      setSyncStatus('error');
      setSyncError(e.message || 'Something went wrong during Jira sync.');
    }
  }

  /** Save Jira entity_configs only (no sync). Used in embedded Integrations edit. */
  async function saveJiraConfigOnly(): Promise<boolean> {
    try {
      const putRes = await fetch(`${RESEARCH_API_URL}/integrations/jira`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildJiraPutBody()),
      });
      return putRes.ok;
    } catch {
      return false;
    }
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
  const canProceedStep2 = activeTool === 'monday'
    ? keyTestStatus === 'ok'
    : activeTool === 'jira'
    ? jiraKeyTestStatus === 'ok'
    : false;
  const canProceedStep3 = activeTool === 'monday'
    ? Object.values(entityConfigs).every(c => c.board_ids.length > 0) && mondayEntities.length > 0
    : activeTool === 'jira'
    ? Object.values(jiraEntityConfigs).every(c => c.project_key && c.issue_type_names.length > 0) && jiraEntities.length > 0
    : false;

  return (
    <div className={embeddedJira ? 'w-full' : 'min-h-screen bg-[#FBFBFA] flex items-center justify-center p-6'}>
      <motion.div
        initial={{ opacity: 0, y: embeddedJira ? 10 : 30 }}
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
          {/* ─── Step 1: Entity selection ─── */}
          {/* Jira-context only: which entities sync with Jira (same UX as Monday in Integrations) */}
          {step === 1 && (embeddedJira || entitySelectorJiraOnly) && (
            <motion.div key="step1-jira-only" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
              <div className="mb-6">
                <h2 className="text-[10px] font-black uppercase tracking-widest text-[#737373]">Select entity types for Jira</h2>
                <p className="text-xs text-[#737373] mt-1">Choose which Product OS entities sync with Jira. You can add or remove them here.</p>
              </div>
              <div className="space-y-1">
                {ENTITY_TYPES.map(entity => {
                  const checked = entityToolMap[entity.id] === 'jira';
                  const hasConfig = Boolean(jiraEntityConfigs[entity.id]);
                  return (
                    <label
                      key={entity.id}
                      className={`flex items-center justify-between gap-3 px-3 py-2 rounded-lg border text-[11px] cursor-pointer ${
                        checked ? 'border-indigo-500 bg-indigo-50/50' : 'border-[#E5E5E5] bg-white'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          className="w-3 h-3 rounded border-[#D4D4D4] text-indigo-600"
                          checked={checked}
                          onChange={e => {
                            e.stopPropagation();
                            const nextChecked = !checked;
                            setEntityToolMap(prev => ({ ...prev, [entity.id]: nextChecked ? 'jira' : '' }));
                            if (!nextChecked) {
                              setJiraEntityConfigs(prev => {
                                const next = { ...prev };
                                delete next[entity.id];
                                return next;
                              });
                            }
                          }}
                        />
                        <span className="font-medium text-[#1A1A1A]">{entity.label}</span>
                      </div>
                      <div className="flex items-center gap-3">
                        {hasConfig && (
                          <button
                            type="button"
                            onClick={e => {
                              e.preventDefault();
                              e.stopPropagation();
                              setEntityToolMap(prev => ({ ...prev, [entity.id]: '' }));
                              setJiraEntityConfigs(prev => {
                                const next = { ...prev };
                                delete next[entity.id];
                                return next;
                              });
                            }}
                            className="text-[10px] font-bold text-red-500 hover:text-red-600"
                          >
                            Remove configuration
                          </button>
                        )}
                        <span className="text-[10px] font-mono text-[#A3A3A3]">{entity.id}</span>
                      </div>
                    </label>
                  );
                })}
              </div>
              <div className="mt-8 flex justify-between">
                {embeddedJira && onJiraEditCancel ? (
                  <button onClick={onJiraEditCancel} className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-[#737373] hover:text-[#1A1A1A] transition-colors">
                    <ArrowLeft className="w-4 h-4" /> Back to Integrations
                  </button>
                ) : <div />}
                <button
                  onClick={() => {
                    setEntitySelectorJiraOnly(false);
                    setStep(embeddedJira && initialJiraConfig?.access_token_set ? 3 : 2);
                  }}
                  disabled={jiraEntities.length === 0}
                  className="flex items-center gap-2 px-6 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed hover:bg-indigo-700 transition-colors ml-auto"
                >
                  Continue <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </motion.div>
          )}
          {/* Full onboarding: entity → tool mapping (Monday / Jira / etc.) */}
          {step === 1 && !embeddedJira && !entitySelectorJiraOnly && (
            <motion.div key="step1-full" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
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
                    if (!needsMonday) setStep(2);
                    else setStep(2);
                  }}
                  disabled={!canProceedStep1}
                  className="flex items-center gap-2 px-6 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed hover:bg-indigo-700 transition-colors"
                >
                  Continue <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </motion.div>
          )}

          {/* ─── Step 2: Connect Tool (Monday or Jira) ─── */}
          {/* ─── Step 2: Connect Jira ─── */}
          {needsJira && !needsMonday && step === 2 && (
            <motion.div key="step2-jira" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
              <div className="text-center mb-8">
                <div className="w-12 h-12 bg-indigo-100 rounded-xl flex items-center justify-center mx-auto mb-4">
                  <Zap className="w-6 h-6 text-indigo-600" />
                </div>
                <h1 className="text-2xl font-bold tracking-tight mb-2">Connect Jira</h1>
                <p className="text-[#737373]">
                  You selected Jira for {jiraEntities.length} entity type{jiraEntities.length !== 1 ? 's' : ''}.
                  Sign in with Jira to continue — we&apos;ll save the connection in the background.
                </p>
                <p className="text-sm mt-2">
                    <button
                      type="button"
                      onClick={() => { setEntitySelectorJiraOnly(true); setStep(1); }}
                      className="text-indigo-600 hover:text-indigo-700 font-medium underline"
                    >
                      Add or remove entity types
                    </button>
                  </p>
              </div>

              <div className="bg-white border border-[#E5E5E5] rounded-xl p-6 space-y-5">
                {!jiraOAuthReady && (
                  <div className="flex items-center gap-2 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                    <AlertCircle className="w-4 h-4 shrink-0" /> {jiraOAuthNotReadyMessage}
                  </div>
                )}
                <div>
                  <p className="text-sm text-[#525252] mb-4">
                    Click the button below to open Jira, approve access, then return here. Your token and site URL are saved automatically.
                  </p>
                  <button
                    type="button"
                    onClick={handleConnectWithJiraOAuth}
                    disabled={!jiraOAuthReady && !(jiraClientId.trim() && (jiraClientSecret.trim() || jiraClientSecretSet))}
                    className="flex items-center gap-2 px-5 py-3 bg-indigo-600 text-white rounded-xl text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed hover:bg-indigo-700 transition-colors"
                  >
                    Connect with Jira (OAuth)
                  </button>
                </div>
                {jiraOAuthSaveError && (
                  <div className="flex items-center gap-2 text-sm text-red-600">
                    <AlertCircle className="w-4 h-4 shrink-0" /> {jiraOAuthSaveError}
                  </div>
                )}
                {/* Cloud ID / token filled by OAuth — not shown */}
                <div style={{ display: 'none' }}>
                  <label className="block text-sm font-medium mb-1.5">Cloud ID</label>
                  <p className="text-xs text-[#737373] mb-2">
                    Filled automatically when you use “Connect with Jira (OAuth)” above. Not the same as Client ID (that goes in the server .env only).
                  </p>
                  <input
                    type="text"
                    value={jiraCloudId}
                    onChange={e => { setJiraCloudId(e.target.value); setJiraKeyTestStatus('idle'); }}
                    placeholder="Filled by OAuth, or paste from your token response"
                    className="w-full px-3 py-2 border border-[#E5E5E5] rounded-lg text-sm"
                  />
                </div>

                <div style={{ display: 'none' }}>
                  <label className="block text-sm font-medium mb-1.5">OAuth Access Token</label>
                  <input type="password" value={jiraAccessToken} readOnly className="w-full px-3 py-2 border border-[#E5E5E5] rounded-lg text-sm" />
                </div>

                {jiraKeyTestStatus === 'ok' && (
                  <div className="flex items-center gap-2 text-sm text-green-600">
                    <CheckCircle2 className="w-4 h-4" /> Connected to Jira successfully. You can continue to map projects.
                  </div>
                )}
                {jiraKeyTestStatus === 'error' && (
                  <div className="flex items-center gap-2 text-sm text-red-600">
                    <AlertCircle className="w-4 h-4" /> {jiraKeyError}
                  </div>
                )}
                {jiraKeyTestStatus === 'ok' && (
                  <button
                    onClick={testJiraConnection}
                    disabled={jiraKeyTestStatus === 'testing'}
                    className="flex items-center gap-2 px-3 py-1.5 text-sm text-[#737373] hover:text-[#1A1A1A] border border-[#E5E5E5] rounded-lg hover:bg-[#F5F5F5] transition-colors"
                  >
                    {jiraKeyTestStatus === 'testing' ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                    Test connection again
                  </button>
                )}
                <details className="group" open={jiraShowAdvanced}>
                  <summary
                    className="text-sm font-medium text-[#737373] cursor-pointer hover:text-[#1A1A1A] list-none flex items-center gap-1"
                    onClick={e => { e.preventDefault(); setJiraShowAdvanced(v => !v); }}
                  >
                    <span className="select-none">Use your own Atlassian app (Client ID / Secret)</span>
                  </summary>
                  {jiraShowAdvanced && (
                    <div className="mt-4 space-y-4 pt-4 border-t border-[#E5E5E5]">
                      <div>
                        <label className="block text-sm font-medium mb-1">Client ID</label>
                        <input
                          type="text"
                          value={jiraClientId}
                          onChange={e => { setJiraClientId(e.target.value); setJiraOAuthSaveError(''); }}
                          placeholder="From Atlassian app Settings"
                          className="w-full px-3 py-2 border border-[#E5E5E5] rounded-lg text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium mb-1">Client Secret</label>
                        <input
                          type="password"
                          value={jiraClientSecret}
                          onChange={e => { setJiraClientSecret(e.target.value); setJiraOAuthSaveError(''); }}
                          placeholder={jiraClientSecretSet ? 'Leave blank to keep existing' : 'From Atlassian app Settings'}
                          className="w-full px-3 py-2 border border-[#E5E5E5] rounded-lg text-sm"
                        />
                      </div>
                    </div>
                  )}
                </details>
              </div>

              <div className="mt-8 flex justify-between">
                <button
                  onClick={() => { if (embeddedJira && onJiraEditCancel) onJiraEditCancel(); else setStep(1); }}
                  className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-[#737373] hover:text-[#1A1A1A] transition-colors"
                >
                  <ArrowLeft className="w-4 h-4" /> {embeddedJira ? 'Back to Integrations' : 'Back'}
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

          {/* ─── Step 2: Connect Monday ─── */}
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

          {/* ─── Step 3: Monday board mapping (only when Monday is selected) ─── */}
          {needsMonday && step === 3 && (
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

          {/* ─── Step 3: Jira Project + Issue Type Mapping ─── */}
          {needsJira && !needsMonday && step === 3 && (
            <motion.div key="step3-jira" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
              <div className="text-center mb-8">
                <div className="w-12 h-12 bg-indigo-100 rounded-xl flex items-center justify-center mx-auto mb-4">
                  <Search className="w-6 h-6 text-indigo-600" />
                </div>
                <h1 className="text-2xl font-bold tracking-tight mb-2">Map your Jira projects</h1>
                <p className="text-[#737373]">Select which Jira project and issue type(s) contain each entity type.</p>
                <p className="text-sm mt-2">
                    <button
                      type="button"
                      onClick={() => { setEntitySelectorJiraOnly(true); setStep(1); }}
                      className="text-indigo-600 hover:text-indigo-700 font-medium underline"
                    >
                      Add or remove entity types
                    </button>
                  </p>
              </div>

              {jiraProjectsLoading ? (
                <div className="flex items-center justify-center py-12 text-[#737373]">
                  <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading projects from Jira...
                </div>
              ) : (
                <div className="space-y-4">
                  {jiraEntities.map(entityId => {
                    const entity = ENTITY_TYPES.find(e => e.id === entityId);
                    const cfg = jiraEntityConfigs[entityId];
                    return (
                      <div key={entityId} className="bg-white border border-[#E5E5E5] rounded-xl p-4 space-y-3">
                        <div className="font-medium text-sm">{entity?.label}</div>
                        <div>
                          <label className="block text-xs text-[#737373] mb-1">Jira Project</label>
                          <select
                            value={cfg?.project_key || ''}
                            onChange={e => {
                              const key = e.target.value;
                              setJiraEntityConfigs(prev => ({
                                ...prev,
                                [entityId]: { ...prev[entityId], project_key: key, issue_type_names: [] },
                              }));
                              if (key) loadJiraSchema(key);
                            }}
                            className="w-full px-3 py-2 border border-[#E5E5E5] rounded-lg text-sm"
                          >
                            <option value="">Select a project...</option>
                            {jiraProjects.map(p => (
                              <option key={p.key} value={p.key}>{p.name} ({p.key})</option>
                            ))}
                          </select>
                        </div>
                        {cfg?.project_key && jiraIssueTypes.length > 0 && (
                          <div>
                            <label className="block text-xs text-[#737373] mb-1">Issue Type</label>
                            <div className="flex flex-wrap gap-2">
                              {jiraIssueTypes.map(it => {
                                const selected = cfg.issue_type_names.includes(it.name);
                                return (
                                  <button
                                    key={it.name}
                                    type="button"
                                    onClick={() => {
                                      setJiraEntityConfigs(prev => {
                                        const cur = prev[entityId];
                                        return { ...prev, [entityId]: { ...cur, issue_type_names: [it.name] } };
                                      });
                                    }}
                                    className={`px-3 py-1.5 text-xs rounded-lg border transition-colors ${
                                      selected
                                        ? 'bg-indigo-600 text-white border-indigo-600'
                                        : 'bg-white text-[#1A1A1A] border-[#E5E5E5] hover:border-indigo-400'
                                    }`}
                                  >
                                    {it.name}
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                        )}
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

          {/* ─── Steps 4..(4+N-1): Field mapping (one step per entity) — Monday ─── */}
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

          {/* ─── Steps 4..(4+N-1): Field mapping (one step per entity) — Jira ─── */}
          {needsJira && !needsMonday && step >= jiraStepIndices.firstFieldStep && step <= jiraStepIndices.lastFieldStep && (() => {
            const entityIndex = step - jiraStepIndices.firstFieldStep;
            const entityId = jiraEntities[entityIndex];
            const entity = ENTITY_TYPES.find(e => e.id === entityId);
            const cfg = jiraEntityConfigs[entityId];
            const canonicalFields = PRODUCT_OS_ENTITY_FIELDS[entityId] || [];
            const fieldMappings = cfg?.field_mappings || {};
            const filteredJiraFields = jiraFields.filter(f => f.name && f.id);
            const isLastFieldStep = step === jiraStepIndices.lastFieldStep;
            return (
            <motion.div key={`step4-jira-${entityId}`} initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
              <div className="text-center mb-6">
                <div className="w-12 h-12 bg-indigo-100 rounded-xl flex items-center justify-center mx-auto mb-4">
                  <Zap className="w-6 h-6 text-indigo-600" />
                </div>
                <h1 className="text-2xl font-bold tracking-tight mb-2">Map fields: {entity?.label}</h1>
                <p className="text-[#737373]">Map Jira fields to Product OS fields for better search.</p>
                <p className="text-sm mt-2">
                    <button
                      type="button"
                      onClick={() => { setEntitySelectorJiraOnly(true); setStep(1); }}
                      className="text-indigo-600 hover:text-indigo-700 font-medium underline"
                    >
                      Add or remove entity types
                    </button>
                  </p>
              </div>

              <div className="space-y-6">
                <div className="bg-white border border-[#E5E5E5] rounded-xl p-4 min-h-[200px]">
                  <div className="mb-3">
                    <div className="font-medium text-sm">{entity?.label}</div>
                    {cfg?.project_key && <div className="text-xs text-[#737373]">Project: {cfg.project_key} &middot; Types: {cfg.issue_type_names.join(', ') || 'all'}</div>}
                  </div>
                  {filteredJiraFields.length > 0 ? (
                    <div className="space-y-2">
                      {canonicalFields.map(canonicalName => {
                        const mappedFieldId = Object.entries(fieldMappings).find(([, t]) => t === canonicalName)?.[0];
                        return (
                          <div key={canonicalName} className="flex items-center gap-2 text-sm">
                            <span className="w-32 font-mono text-xs text-[#737373] shrink-0">{formatEntityTypeLabel(entityId)}.{canonicalName}</span>
                            <span className="text-[#737373]">&rarr;</span>
                            <JiraFieldSelect
                              value={mappedFieldId || ''}
                              onChange={fid => {
                                setJiraEntityConfigs(prev => {
                                  const cur = prev[entityId] || { entity_type: entityId, project_key: '', issue_type_names: [], direction: 'jira_to_os' as JiraDirection, field_mappings: {} };
                                  const next = { ...(cur.field_mappings || {}) };
                                  Object.keys(next).forEach(k => { if (next[k] === canonicalName) delete next[k]; });
                                  if (fid) next[fid] = canonicalName;
                                  return { ...prev, [entityId]: { ...cur, field_mappings: next } };
                                });
                              }}
                              options={filteredJiraFields}
                              placeholder="Not mapped"
                            />
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="text-xs text-[#737373]">No Jira fields loaded. Go back and select a project.</p>
                  )}
                </div>
              </div>

              <div className="mt-8 flex justify-between">
                <button
                  onClick={() => setStep(step === jiraStepIndices.firstFieldStep ? 3 : step - 1)}
                  className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-[#737373] hover:text-[#1A1A1A] transition-colors"
                >
                  <ArrowLeft className="w-4 h-4" /> Back
                </button>
                <button
                  onClick={async () => {
                    if (isLastFieldStep) {
                      if (embeddedJira && onJiraEditComplete) {
                        const ok = await saveJiraConfigOnly();
                        if (ok) {
                          setStep(jiraStepIndices.syncStep);
                          saveJiraPrepareOnly();
                        }
                      } else {
                        setStep(jiraStepIndices.syncStep);
                        saveJiraConfigAndSync();
                      }
                    } else {
                      setStep(step + 1);
                    }
                  }}
                  className="flex items-center gap-2 px-6 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors"
                >
                  {isLastFieldStep && embeddedJira ? <>Save & sync <ChevronRight className="w-4 h-4" /></> : isLastFieldStep ? <>Sync & Index <ChevronRight className="w-4 h-4" /></> : <>Continue <ChevronRight className="w-4 h-4" /></>}
                </button>
              </div>
            </motion.div>
            );
          })()}

          {/* ─── Sync & Index — Jira ─── */}
          {needsJira && !needsMonday && step === jiraStepIndices.syncStep && (
            <motion.div key="step5-jira" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
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
                  {syncStatus === 'syncing' && 'Syncing your Jira data...'}
                  {syncStatus === 'done' && 'Jira data synced!'}
                  {syncStatus === 'error' && 'Sync failed'}
                  {syncStatus === 'idle' && 'Preparing sync...'}
                </h1>
                <p className="text-[#737373]">
                  {syncStatus === 'syncing' && 'Pulling data from Jira and indexing for search. This may take a minute.'}
                  {syncStatus === 'done' && syncStats && (
                    <>
                      {syncStats.fetched} items fetched, {syncStats.embedded} chunks indexed.
                      {typeof syncStats.total_entities === 'number' && (
                        <span className="block mt-1 font-medium text-[#1A1A1A]">
                          {syncStats.total_entities} Jira {syncStats.total_entities === 1 ? 'entity' : 'entities'} in search.
                        </span>
                      )}
                    </>
                  )}
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
                    onClick={() => {
                      if (embeddedJira && onJiraEditComplete) onJiraEditComplete();
                      else setStep(jiraStepIndices.completeStep);
                    }}
                    className="flex items-center gap-2 px-6 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors"
                  >
                    {embeddedJira ? 'Back to Integrations' : <><ChevronRight className="w-4 h-4" /> Continue</>}
                  </button>
                )}
                {syncStatus === 'error' && (
                  <div className="flex flex-col gap-3">
                    <div className="flex gap-3">
                      <button
                        onClick={() => embeddedJira && onJiraEditCancel ? onJiraEditCancel() : setStep(jiraStepIndices.lastFieldStep)}
                        className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-[#737373] hover:text-[#1A1A1A] transition-colors"
                      >
                        <ArrowLeft className="w-4 h-4" /> {embeddedJira ? 'Back to Integrations' : 'Back'}
                      </button>
                      <button
                        onClick={() => { setSyncStatus('idle'); embeddedJira ? saveJiraPrepareOnly() : saveJiraConfigAndSync(); }}
                        className="flex items-center gap-2 px-6 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors"
                      >
                        Retry
                      </button>
                      {!embeddedJira && (
                      <button
                        onClick={clearJiraConnectionAndGoToConnect}
                        className="flex items-center gap-2 px-6 py-2.5 border border-indigo-600 text-indigo-600 rounded-xl text-sm font-semibold hover:bg-indigo-50 transition-colors"
                      >
                        Reconnect Jira
                      </button>
                      )}
                    </div>
                    <p className="text-xs text-[#737373]">
                      Use “Reconnect Jira” to sign in again with a fresh connection. If the error persists, try a different Jira Cloud site or Atlassian account.
                    </p>
                  </div>
                )}
              </div>
            </motion.div>
          )}

          {/* ─── Complete (step 2 when no tool, else step 5+N for Monday or Jira) ─── */}
          {((!needsMonday && !needsJira && step === 2) || (needsMonday && step === stepIndices.completeStep) || (needsJira && !needsMonday && step === jiraStepIndices.completeStep)) && (
            <motion.div key="step6" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}>
              <div className="text-center mb-8">
                <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
                  <CheckCircle2 className="w-8 h-8 text-green-600" />
                </div>
                <h1 className="text-2xl font-bold tracking-tight mb-2">You're all set!</h1>
                <p className="text-[#737373]">
                  {syncStats
                    ? `${syncStats.fetched} items from ${activeTool === 'jira' ? 'Jira' : 'Monday.com'} are indexed and ready for research.`
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
