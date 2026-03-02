import React, { useState, useEffect, useRef } from 'react';
import { 
  Settings, 
  MessageSquare, 
  Database, 
  ExternalLink, 
  CheckCircle2, 
  AlertCircle, 
  Send, 
  Loader2,
  ChevronRight,
  Plus,
  Link as LinkIcon,
  FileText,
  Video,
  Trello,
  X,
  Github,
  CreditCard,
  Users,
  Search,
  ArrowLeft,
  Check,
  Zap
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import confetti from 'canvas-confetti';
import ReactMarkdown from 'react-markdown';
import { AppConfig, ContextItem, AgentResponse, ChatSession, MondayBoardSchema, MondayIntegrationConfigResponse, MondayEntityMappingConfig, MondayDirection } from './types';

const ANSWER_MARKDOWN_COMPONENTS = {
  p: ({ children, ...props }: any) => <p className="mb-4 last:mb-0" {...props}>{children}</p>,
  ul: ({ children, ...props }: any) => <ul className="list-disc pl-5 mb-4 space-y-1.5" {...props}>{children}</ul>,
  ol: ({ children, ...props }: any) => <ol className="list-decimal pl-5 mb-4 space-y-2" {...props}>{children}</ol>,
  li: ({ children, ...props }: any) => <li className="leading-snug" {...props}>{children}</li>,
  strong: ({ children, ...props }: any) => <strong className="font-semibold text-[#0F0F0F]" {...props}>{children}</strong>,
  h3: ({ children, ...props }: any) => <h3 className="text-base font-semibold mt-5 mb-2 first:mt-0" {...props}>{children}</h3>,
  h4: ({ children, ...props }: any) => <h4 className="text-sm font-semibold mt-4 mb-1.5" {...props}>{children}</h4>,
  blockquote: ({ children, ...props }: any) => <blockquote className="border-l-2 border-[#E5E5E5] pl-4 my-3 text-[#525252] italic" {...props}>{children}</blockquote>,
  a: ({ href, children, ...props }: any) => <a href={href} target="_blank" rel="noopener noreferrer" className="text-indigo-600 hover:underline" {...props}>{children}</a>,
  hr: (props: any) => <hr className="my-4 border-[#E5E5E5]" {...props} />,
};

function splitAnswerSections(answer: string): { tldr: string | null; rest: string } {
  // Look for a TL;DR line like "**TL;DR:** ..." at the top of the answer.
  const regex = /\*\*TL;DR\*\*:?([\s\S]*?)(\n{2,}|$)/i;
  const match = answer.match(regex);
  if (!match || match.index === undefined) {
    return { tldr: null, rest: answer };
  }
  const tldrBlock = match[0].trim();
  const rest = answer.slice(match.index + match[0].length).trim();
  return {
    tldr: tldrBlock,
    rest: rest || '',
  };
}

const INITIAL_CONFIG: AppConfig = {
  integrations: {
    jira: false,
    monday: false,
    docs: false,
    zoom: false,
    slack: false,
    github: false,
    stripe: false,
    hubspot: false
  },
  mappings: {
    jira: {
      "Summary": "Feature.title",
      "Assignee": "Feature.owner",
      "Status": "Feature.status",
      "Labels": "Feature.tags"
    },
    monday: {
      "Name": "Epic.title",
      "Status": "Epic.status"
    },
    docs: {
      "Title": "Requirement.title",
      "Content": "Requirement.description"
    },
    zoom: {
      "Summary": "Decision.title",
      "Transcript": "Decision.rationale"
    },
    slack: {
      "Channel": "Feature.tags",
      "Message": "Decision.rationale"
    },
    github: {
      "PR Title": "Feature.title",
      "Issue Body": "Feature.description"
    }
  }
};

const INTEGRATION_PROVIDERS = [
  { id: 'jira', name: 'Jira', tagline: 'Sync issues & epics', icon: Trello, color: 'text-blue-600', bg: 'bg-blue-50', enabled: false },
  { id: 'monday', name: 'Monday.com', tagline: 'Sync boards & items', icon: CheckCircle2, color: 'text-indigo-600', bg: 'bg-indigo-50', enabled: true },
  { id: 'docs', name: 'Google Docs', tagline: 'Sync PRDs & specs', icon: FileText, color: 'text-amber-600', bg: 'bg-amber-50', enabled: false },
  { id: 'zoom', name: 'Zoom', tagline: 'Sync meeting transcripts', icon: Video, color: 'text-orange-600', bg: 'bg-orange-50', enabled: false },
  { id: 'slack', name: 'Slack', tagline: 'Sync channels & comments', icon: MessageSquare, color: 'text-purple-600', bg: 'bg-purple-50', enabled: false },
  { id: 'github', name: 'GitHub', tagline: 'Sync PRs & issues', icon: Github, color: 'text-gray-900', bg: 'bg-gray-100', enabled: false },
  { id: 'stripe', name: 'Stripe', tagline: 'Sync payments & customers', icon: CreditCard, color: 'text-blue-500', bg: 'bg-blue-50', enabled: false },
  { id: 'hubspot', name: 'HubSpot', tagline: 'Sync deals & feedback', icon: Users, color: 'text-orange-500', bg: 'bg-orange-50', enabled: false },
];

const OAUTH_SETUP_INSTRUCTIONS: Record<string, {
  title: string;
  dashboardUrl: string;
  docsUrl: string;
  scopes: string[];
  steps: string[];
}> = {
  jira: {
    title: 'Set up Atlassian OAuth 2.0',
    dashboardUrl: 'https://developer.atlassian.com/console/myapps/',
    docsUrl: 'https://developer.atlassian.com/cloud/jira/platform/oauth-2-3lo-apps/',
    scopes: ['read:jira-work', 'read:jira-user', 'offline_access'],
    steps: [
      'Go to the Atlassian Developer Console and create a new "OAuth 2.0 (3LO)" app.',
      'Under "Permissions", add the "Jira platform REST API" and select the required scopes.',
      'Under "Authorization", add the Callback URL provided below.',
      'Copy your Client ID and Client Secret to continue.'
    ]
  },
  monday: {
    title: 'Create a Monday.com App',
    dashboardUrl: 'https://developers.monday.com/apps/',
    docsUrl: 'https://developer.monday.com/apps/docs/oauth',
    scopes: ['me:read', 'boards:read', 'workspaces:read'],
    steps: [
      'Open the Monday.com Developers section and create a new App.',
      'Navigate to the "OAuth" tab in your app settings.',
      'Add the Redirect URI (Callback URL) provided below.',
      'Select the required scopes under the "Scopes" section.',
      'Copy your Client ID and Client Secret from the "App Credentials" tab.'
    ]
  }
};

const MOCK_CONTEXT_ITEMS: ContextItem[] = [
  {
    id: "JIRA-101",
    source_type: "jira",
    source_id: "PROJ-101",
    title: "Real-time Collaboration Engine",
    url: "https://jira.mock.com/browse/PROJ-101",
    type: "Feature",
    status: "In Progress",
    owner: "Sarah Chen",
    description: "Core engine for multi-user sync using WebSockets.",
    priority: "High",
    tags: ["core", "real-time"],
    lastModified: "2026-02-21"
  },
  {
    id: "JIRA-BUG-1",
    source_type: "jira",
    source_id: "BUG-1",
    title: "APAC Latency Spike",
    url: "https://jira.mock.com/browse/BUG-1",
    type: "Bug",
    severity: "Critical",
    status: "Open",
    owner: "Sarah Chen",
    lastModified: "2026-02-22"
  },
  {
    id: "MONDAY-1",
    source_type: "monday",
    source_id: "ITEM-1",
    title: "Q1 Product Roadmap",
    url: "https://monday.mock.com/boards/1/item/1",
    type: "Epic",
    status: "Planning",
    features: ["JIRA-101"],
    lastModified: "2026-02-20"
  },
  {
    id: "DOC-1",
    source_type: "doc",
    source_id: "DOC-PRD-001",
    title: "PRD: AI Search Integration",
    url: "https://docs.mock.com/d/PRD-001",
    type: "Requirement",
    description: "System must support semantic search across all connected services.",
    sourceDocId: "DOC-PRD-001",
    lastModified: "2026-02-19"
  },
  {
    id: "ZOOM-1",
    source_type: "zoom",
    source_id: "MEET-992",
    title: "Architecture Review: WebSocket vs Polling",
    url: "https://zoom.mock.com/rec/992",
    type: "Decision",
    rationale: "Selected WebSockets for lower latency and better scalability for 100+ concurrent users.",
    date: "2026-02-20",
    meetingId: "MEET-992",
    lastModified: "2026-02-20"
  },
  {
    id: "JIRA-102",
    source_type: "jira",
    source_id: "PROJ-102",
    title: "Mobile Offline Mode",
    url: "https://jira.mock.com/browse/PROJ-102",
    type: "Feature",
    status: "Backlog",
    owner: "Mike Ross",
    description: "Enable basic editing while offline with sync on reconnect.",
    priority: "Medium",
    lastModified: "2026-02-18"
  },
  {
    id: "MONDAY-2",
    source_type: "monday",
    source_id: "ITEM-2",
    title: "User Growth Strategy",
    url: "https://monday.mock.com/boards/1/item/2",
    type: "Epic",
    status: "In Progress",
    features: ["JIRA-102"],
    lastModified: "2026-02-21"
  },
  {
    id: "DOC-2",
    source_type: "doc",
    source_id: "DOC-SPEC-002",
    title: "Technical Spec: Offline Sync",
    url: "https://docs.mock.com/d/SPEC-002",
    type: "Requirement",
    description: "Use IndexedDB for local storage and conflict resolution via CRDT.",
    sourceDocId: "DOC-SPEC-002",
    lastModified: "2026-02-15"
  },
  {
    id: "ZOOM-2",
    source_type: "zoom",
    source_id: "MEET-995",
    title: "Go-to-Market Strategy Sync",
    url: "https://zoom.mock.com/rec/995",
    type: "Decision",
    rationale: "Launch beta in EU first to test GDPR compliance workflows.",
    date: "2026-02-21",
    meetingId: "MEET-995",
    lastModified: "2026-02-21"
  },
  {
    id: "JIRA-BUG-2",
    source_type: "jira",
    source_id: "BUG-2",
    title: "GDPR Export Failure",
    url: "https://jira.mock.com/browse/BUG-2",
    type: "Bug",
    severity: "High",
    status: "In Progress",
    owner: "Legal Team",
    lastModified: "2026-02-22"
  }
];

const SERVICE_FIELDS: Record<string, string[]> = {
  jira: ["Summary", "Assignee", "Status", "Labels", "Description", "Priority", "Created Date"],
  monday: ["Name", "Status", "Owner", "Timeline", "Priority", "Notes"],
  docs: ["Title", "Content", "Author", "Last Modified", "Tags"],
  zoom: ["Summary", "Transcript", "Duration", "Participants", "Date"],
  slack: ["Channel", "Message", "User", "Timestamp", "Thread ID"],
  github: ["PR Title", "Issue Body", "Repo Name", "Author", "Branch"],
  stripe: ["Customer Email", "Amount", "Plan Name", "Status", "Created"],
  hubspot: ["Deal Name", "Company", "Amount", "Stage", "Owner"]
};

const TARGET_ENTITIES = [
  "Feature.title", "Feature.owner", "Feature.status", "Feature.description", "Feature.tags",
  "Epic.title", "Epic.status", "Epic.description",
  "Bug.title", "Bug.severity", "Bug.status", "Bug.owner",
  "SupportTicket.subject", "SupportTicket.customer", "SupportTicket.status",
  "Decision.title", "Decision.rationale", "Decision.date"
];

// Canonical Product OS entity fields for Monday integration, mirrored from backend EntityType/CANONICAL_FIELDS.
const PRODUCT_OS_ENTITY_FIELDS: Record<string, string[]> = {
  feature_request: ["title", "description", "customer", "priority", "status", "votes"],
  roadmap_item: ["title", "description", "target_start", "target_end", "status", "priority"],
  support_ticket: ["title", "description", "customer", "priority", "status", "resolution"],
  bug: ["title", "description", "severity", "status", "affected_version", "priority"],
  prd: ["title", "overview", "target_users", "requirements", "success_metrics", "status"],
  meeting_note: ["title", "transcript", "summary", "attendees", "date", "tags"],
};

const formatEntityTypeLabel = (entityType: string) =>
  entityType
    .split("_")
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");

const RESEARCH_API_URL = import.meta.env.VITE_RESEARCH_API_URL || 'http://localhost:8000';

export default function App() {
  const [mode, setMode] = useState<'admin' | 'pm'>('pm');
  const [config, setConfig] = useState<AppConfig | null>(INITIAL_CONFIG);
  const [contextItems, setContextItems] = useState<ContextItem[]>([]);
  const [chats, setChats] = useState<ChatSession[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<{ role: 'user' | 'assistant', content: string | AgentResponse }[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [editingService, setEditingService] = useState<string | null>(null);
  const [selectedServiceForMapping, setSelectedServiceForMapping] = useState<string | null>(null);
  const [activeTargetEntity, setActiveTargetEntity] = useState<string | null>(null);
  const [activeSourceField, setActiveSourceField] = useState<string | null>(null);
  const [showSidebar, setShowSidebar] = useState(true);
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [wizardStep, setWizardStep] = useState(1);
  const [selectedProviderForWizard, setSelectedProviderForWizard] = useState<string | null>(null);
  const [isConnecting, setIsConnecting] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [mondayApiKey, setMondayApiKey] = useState('');
  const [mondayTestStatus, setMondayTestStatus] = useState<'idle' | 'testing' | 'ok' | 'error'>('idle');
  const [mondayConnectError, setMondayConnectError] = useState<string | null>(null);
  const [mondayEntityConfigs, setMondayEntityConfigs] = useState<Record<string, MondayEntityMappingConfig>>({});
  const [osEntityTypes, setOsEntityTypes] = useState<string[]>([]);
  const [selectedOsEntityTypes, setSelectedOsEntityTypes] = useState<string[]>([]);
  const [activeMondayEntityTypeForFields, setActiveMondayEntityTypeForFields] = useState<string | null>(null);
  const [mondayPrepareStatus, setMondayPrepareStatus] = useState<'idle' | 'preparing' | 'ok' | 'error'>('idle');
  const [mondayPrepareMessage, setMondayPrepareMessage] = useState<string | null>(null);
  const [mondayPrepareStats, setMondayPrepareStats] = useState<{ fetched: number; embedded: number; totalEntities: number } | null>(null);
  const [mondayConfig, setMondayConfig] = useState<MondayIntegrationConfigResponse | null>(null);
  const [mondaySubdomain, setMondaySubdomain] = useState<string>('');
  const [mondayBoards, setMondayBoards] = useState<MondayBoardSchema[]>([]);
  const [mondaySchemaLoading, setMondaySchemaLoading] = useState(false);
  const [mondaySchemaError, setMondaySchemaError] = useState<string | null>(null);
  const mappingsRef = useRef<HTMLDivElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const [entityModal, setEntityModal] = useState<{ entities: any[] } | null>(null);
  const prevActiveChatIdRef = useRef<string | null>(activeChatId);

  // Load Monday integration state from backend so UI reflects real connectivity
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${RESEARCH_API_URL}/integrations/monday`);
        if (!res.ok || cancelled) return;
        const data: MondayIntegrationConfigResponse = await res.json();
        setMondayConfig(data);
        setMondaySubdomain(data.subdomain ?? '');
        if (data.entity_configs) {
          setMondayEntityConfigs(data.entity_configs);
        }
        const mondayConnected = Boolean(data.enabled && data.api_key_set);
        setConfig(prev => prev ? { ...prev, integrations: { ...prev.integrations, monday: mondayConnected } } : null);
        const anyIntegrationActive = mondayConnected; // extend when more integrations exist
        if (anyIntegrationActive) setContextItems([]);
        else setContextItems(MOCK_CONTEXT_ITEMS);
      } catch {
        if (!cancelled) setConfig(prev => prev ?? null);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Keep the Monday field-mapping wizard scoped to a single active Product OS entity.
  useEffect(() => {
    if (selectedServiceForMapping !== 'monday') return;
    setActiveMondayEntityTypeForFields(prev => {
      if (prev && selectedOsEntityTypes.includes(prev)) {
        return prev;
      }
      return selectedOsEntityTypes[0] || null;
    });
  }, [selectedServiceForMapping, selectedOsEntityTypes]);

  // Load Product OS entity types so Monday mapping stays in sync with backend EntityType enum
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${RESEARCH_API_URL}/sources`);
        if (!res.ok || cancelled) return;
        const data = await res.json();
        if (Array.isArray(data?.entity_types)) {
          setOsEntityTypes(data.entity_types);
        }
      } catch {
        /* ignore; UI can still function with an empty list */
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const lastAssistantMessage = [...messages].reverse().find(m => m.role === 'assistant')?.content as AgentResponse | undefined;

  const productContextStats = lastAssistantMessage
    ? Object.keys(PRODUCT_OS_ENTITY_FIELDS).map((entityType) => {
        const count = lastAssistantMessage.entities.filter(
          (e: any) => e.type === entityType || e.entity_type === entityType,
        ).length;
        return {
          entityType,
          label: formatEntityTypeLabel(entityType),
          count,
        };
      })
    : null;

  useEffect(() => {
    // Initialize first chat if none exists
    if (chats.length === 0) {
      const initialId = Math.random().toString(36).substring(7);
      const initialChat: ChatSession = {
        id: initialId,
        title: 'New Research Chat',
        messages: [],
        timestamp: Date.now()
      };
      setChats([initialChat]);
      setActiveChatId(initialId);
    }
  }, []);

  useEffect(() => {
    // Sync active chat messages to messages state only when user switches chat.
    // When chats updates from the messages effect (new reply), we must NOT overwrite messages
    // or the sidebar briefly shows empty state and flickers.
    const switchedChat = prevActiveChatIdRef.current !== activeChatId;
    prevActiveChatIdRef.current = activeChatId;
    if (switchedChat) {
      const activeChat = chats.find(c => c.id === activeChatId);
      if (activeChat) setMessages(activeChat.messages);
    }
  }, [activeChatId, chats]);

  useEffect(() => {
    // Sync messages back to chats state
    if (activeChatId) {
      setChats(prev => prev.map(chat => {
        if (chat.id === activeChatId) {
          // Update title if it's the first user message
          let newTitle = chat.title;
          const firstUserMsg = messages.find(m => m.role === 'user');
          if (firstUserMsg && chat.title === 'New Research Chat') {
            newTitle = typeof firstUserMsg.content === 'string' 
              ? firstUserMsg.content.substring(0, 30) + (firstUserMsg.content.length > 30 ? '...' : '')
              : 'Research Analysis';
          }
          return { ...chat, messages, title: newTitle };
        }
        return chat;
      }));
    }
  }, [messages]);

  const createNewChat = () => {
    const newId = Math.random().toString(36).substring(7);
    const newChat: ChatSession = {
      id: newId,
      title: 'New Research Chat',
      messages: [],
      timestamp: Date.now()
    };
    setChats(prev => [newChat, ...prev]);
    setActiveChatId(newId);
    setMode('pm');
  };

  useEffect(() => {
    if (!messages.length) return;
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [messages]);

  const getStatusBadge = (status?: string) => {
    if (!status) return null;
    const s = status.toLowerCase();
    let emoji = '⚪';
    let color = 'bg-gray-50 text-gray-600';
    
    if (s.includes('in progress')) {
      emoji = '🟡';
      color = 'bg-amber-50 text-amber-700';
    } else if (s.includes('open') || s.includes('backlog') || s.includes('planning')) {
      emoji = '🔴';
      color = 'bg-red-50 text-red-700';
    } else if (s.includes('done') || s.includes('completed') || s.includes('resolved')) {
      emoji = '🟢';
      color = 'bg-emerald-50 text-emerald-700';
    }
    
    return (
      <span className={`flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${color}`}>
        <span>{emoji}</span>
        {status}
      </span>
    );
  };

  const handleSendMessage = async (query?: string) => {
    const userMsg = query || input;
    if (!userMsg.trim() || loading) return;

    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setLoading(true);

    // Fallback response when API is unavailable.
    const fallbackResponse: AgentResponse = {
      mode: 'pm',
      answer: `I've analyzed the top items in your Product OS. You have a high-priority feature "Real-time Collaboration Engine" (JIRA-101) currently in progress, but there is a critical bug regarding latency in APAC (BUG-1) that needs attention.`,
      entities: [
        { ...MOCK_CONTEXT_ITEMS.find(i => i.id === 'JIRA-101') },
        { ...MOCK_CONTEXT_ITEMS.find(i => i.id === 'JIRA-BUG-1') }
      ],
      references: [
        { source_type: 'jira', source_id: 'PROJ-101', title: 'Real-time Collaboration Engine', url: 'https://jira.mock.com/browse/PROJ-101' },
        { source_type: 'jira', source_id: 'BUG-1', title: 'APAC Latency Spike', url: 'https://jira.mock.com/browse/BUG-1' }
      ],
      suggestions: ["Related features?", "Update status?"]
    };

    try {
      const response = await fetch(`${RESEARCH_API_URL}/search_memories`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: userMsg,
          top_k: 10
        }),
      });

      if (!response.ok) {
        throw new Error(`Search request failed: ${response.status}`);
      }

      const data = await response.json();
      const rawEntities = (data.raw_results || []).map((result: any) => ({
        id: result.id,
        source_type: result.source,
        source_id: result.id,
        title: result.title || result.body || 'Untitled',
        type: result.entity_type || result.type || 'Entity',
        url: result.url || result.metadata?.url || '#',
        status: result.status ?? result.metadata?.status,
        score: typeof result.score === 'number' ? result.score : 0,
        priority: result.priority ?? result.metadata?.priority,
        votes: typeof result.votes === 'number'
          ? result.votes
          : Number(result.votes ?? result.metadata?.votes ?? 0),
      }));
      const seenKeys = new Set<string>();
      const entities = rawEntities
        .filter((e: { id: string; source_type: string; title: string }) => {
          if (e.source_type === 'mock') return false;
          const baseTitle = (e.title || '').toLowerCase().trim();
          const key = baseTitle || `${e.source_type}:${e.id}`;
          if (seenKeys.has(key)) return false;
          seenKeys.add(key);
          return true;
        })
        .sort((a, b) => {
          // Higher semantic score first
          const scoreDiff = (b.score ?? 0) - (a.score ?? 0);
          if (Math.abs(scoreDiff) > 1e-6) return scoreDiff;

          // Then by votes (descending)
          const va = a.votes ?? 0;
          const vb = b.votes ?? 0;
          if (vb !== va) return vb - va;

          // Then by priority (critical/high/medium/low)
          const rank = (p: any) => {
            if (!p || typeof p !== 'string') return 0;
            const v = p.toLowerCase();
            if (v.includes('critical')) return 3;
            if (v.includes('high')) return 2;
            if (v.includes('medium')) return 1;
            if (v.includes('low')) return 0;
            return 0;
          };
          const pa = rank(a.priority);
          const pb = rank(b.priority);
          return pb - pa;
        });
      const references = (data.references || [])
        .map((ref: any) => ({
          source_type: ref.source || 'monday',
          // Prefer URL as stable source_id; fall back to title.
          source_id: ref.url || ref.title || 'source',
          title: ref.title || 'Reference',
          url: ref.url || '#'
        }))
        .filter((r: { source_type: string }) => r.source_type !== 'mock');
      const mappedResponse: AgentResponse = {
        mode: 'pm',
        answer: data.summary || 'No summary available.',
        entities,
        references,
        suggestions: ['Show more details', 'What changed recently?']
      };

      setMessages(prev => [...prev, { role: 'assistant', content: mappedResponse }]);
    } catch (error) {
      console.error('Research Agent API error:', error);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: {
          mode: 'pm',
          answer: 'Search is unavailable. Check that the Research Agent API is running and your Monday integration is connected.',
          entities: [],
          references: [],
          suggestions: ['Retry', 'Check Integration Setup']
        }
      }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-screen bg-[#F5F5F4] text-[#1A1A1A] font-sans">
      {/* Sidebar */}
      <div className="w-64 border-r border-[#E5E5E5] bg-white flex flex-col">
        <div className="p-6 border-bottom border-[#E5E5E5]">
          <div className="flex items-center gap-2 mb-8">
            <div className="w-8 h-8 bg-[#1A1A1A] rounded-lg flex items-center justify-center">
              <Database className="w-5 h-5 text-white" />
            </div>
            <span className="font-bold tracking-tight text-lg">Product OS</span>
          </div>

          <nav className="space-y-1">
            <button 
              onClick={() => setMode('pm')}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${mode === 'pm' ? 'bg-[#F5F5F4] text-[#1A1A1A]' : 'text-[#737373] hover:bg-[#F5F5F4] hover:text-[#1A1A1A]'}`}
            >
              <MessageSquare className="w-4 h-4" />
              Product Chat
            </button>
            <button 
              onClick={() => setMode('admin')}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${mode === 'admin' ? 'bg-[#F5F5F4] text-[#1A1A1A]' : 'text-[#737373] hover:bg-[#F5F5F4] hover:text-[#1A1A1A]'}`}
            >
              <Settings className="w-4 h-4" />
              Integration Setup
            </button>
          </nav>

          <div className="mt-8">
            <div className="flex items-center justify-between mb-4 px-3">
              <span className="text-[10px] font-black uppercase tracking-widest text-[#737373]">Chat History</span>
              <button 
                onClick={createNewChat}
                className="p-1 hover:bg-[#F5F5F4] rounded-md transition-colors text-blue-600"
                title="New Chat"
              >
                <Plus className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-1 max-h-[300px] overflow-y-auto scrollbar-hide">
              {chats.map(chat => (
                <button
                  key={chat.id}
                  onClick={() => {
                    setActiveChatId(chat.id);
                    setMode('pm');
                  }}
                  className={`w-full text-left px-3 py-2 rounded-lg text-xs font-medium transition-colors truncate ${
                    activeChatId === chat.id && mode === 'pm'
                      ? 'bg-blue-50 text-blue-700' 
                      : 'text-[#737373] hover:bg-[#F5F5F4] hover:text-[#1A1A1A]'
                  }`}
                >
                  {chat.title}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-auto p-6 border-t border-[#E5E5E5]">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-700 font-bold text-xs">
              PM
            </div>
            <div className="flex flex-col">
              <span className="text-xs font-semibold">Alex Rivera</span>
              <span className="text-[10px] text-[#737373]">Senior Product Manager</span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {mode === 'pm' ? (
          <div className="flex-1 flex overflow-hidden relative">
            {/* Chat Area */}
            <div className="flex-1 flex flex-col min-w-0 bg-white">
              {/* Chat Header */}
              <div className="px-8 py-4 border-b border-[#E5E5E5] flex items-center justify-between bg-white">
                <div className="flex items-center gap-3">
                  <MessageSquare className="w-5 h-5 text-blue-600" />
                  <h2 className="font-bold text-sm truncate max-w-[300px]">
                    {chats.find(c => c.id === activeChatId)?.title || 'Product Chat'}
                  </h2>
                </div>
                <button 
                  onClick={createNewChat}
                  className="flex items-center gap-2 px-3 py-1.5 bg-[#F5F5F4] hover:bg-[#E5E5E5] rounded-lg text-xs font-bold transition-all"
                >
                  <Plus className="w-4 h-4" />
                  New Chat
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-8 space-y-8 bg-[#FBFBFA]">
              <AnimatePresence initial={false}>
                {messages.length === 0 && (
                  <motion.div 
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="max-w-2xl mx-auto mt-20 text-center"
                  >
                    <h1 className="text-4xl font-bold tracking-tight mb-4">Ask product questions across your tools</h1>
                    <p className="text-[#737373] mb-8">
                      {config && Object.values(config.integrations).some(Boolean)
                      ? `Connected to ${Object.entries(config.integrations).filter(([_, v]) => v).map(([k]) => k.charAt(0).toUpperCase() + k.slice(1)).join(', ')}.`
                      : 'No integrations connected. Connect Monday.com below to sync data.'}
                    </p>
                    <div className="grid grid-cols-2 gap-4">
                      {[
                        "What are our top product risks right now?",
                        "Summarize recent decisions from meetings",
                        "Show Sarah Chen's high priority features",
                        "What's in the latest PRD document?"
                      ].map((q) => (
                        <button 
                          key={q}
                          onClick={() => handleSendMessage(q)}
                          className="p-4 bg-white border border-[#E5E5E5] rounded-xl text-sm text-left hover:border-[#1A1A1A] hover:shadow-md transition-all group"
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-medium">{q}</span>
                            <ChevronRight className="w-4 h-4 opacity-0 group-hover:opacity-100 transition-opacity" />
                          </div>
                        </button>
                      ))}
                    </div>
                  </motion.div>
                )}

                {messages.map((msg, i) => (
                  <motion.div 
                    key={i}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    ref={i === messages.length - 1 ? chatEndRef : undefined}
                    className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div className={`max-w-[80%] ${msg.role === 'user' ? 'bg-[#1A1A1A] text-white p-4 rounded-2xl' : 'w-full'}`}>
                      {msg.role === 'user' ? (
                        <p className="text-sm">{msg.content as string}</p>
                      ) : (
                        <div className="space-y-6">
                          <div className="bg-white border border-[#E5E5E5] p-6 rounded-2xl shadow-sm">
                            <div className="chat-prose text-sm text-[#1A1A1A] leading-relaxed">
                              {(() => {
                                const { answer } = msg.content as AgentResponse;
                                const { tldr, rest } = splitAnswerSections(answer);
                                return (
                                  <>
                                    {tldr && (
                                      <div className="mb-4 rounded-xl bg-[#F9FAFB] border border-[#E5E5E5] px-4 py-3">
                                        <ReactMarkdown components={ANSWER_MARKDOWN_COMPONENTS}>
                                          {tldr}
                                        </ReactMarkdown>
                                      </div>
                                    )}
                                    <ReactMarkdown components={ANSWER_MARKDOWN_COMPONENTS}>
                                      {rest || (!tldr ? answer : '')}
                                    </ReactMarkdown>
                                  </>
                                );
                              })()}
                            </div>
                          </div>

                          {((msg.content as AgentResponse).entities.length > 0 || (msg.content as AgentResponse).references.length > 0) && (
                            <div className="flex flex-wrap gap-2 pt-2">
                              {/* Entities as small bubbles */}
                              {(() => {
                                const { entities: allEntities } = msg.content as AgentResponse;
                                const maxVisibleEntities = 12;
                                const visibleEntities = allEntities.slice(0, maxVisibleEntities);
                                const extraEntitiesCount = allEntities.length - visibleEntities.length;
                                return (
                                  <>
                                    {visibleEntities.map((entity, ei) => (
                                      <a 
                                        key={`entity-${ei}`}
                                        href={entity.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex items-center gap-2 px-3 py-1.5 bg-white border border-[#E5E5E5] rounded-lg text-[10px] font-bold hover:border-[#1A1A1A] hover:shadow-sm transition-all group"
                                      >
                                        <div className="flex items-center gap-1.5">
                                          {entity.source_type === 'jira' && <Trello className="w-3 h-3 text-blue-600" />}
                                          {entity.source_type === 'monday' && <CheckCircle2 className="w-3 h-3 text-indigo-600" />}
                                          {entity.source_type === 'doc' && <FileText className="w-3 h-3 text-amber-600" />}
                                          {entity.source_type === 'zoom' && <Video className="w-3 h-3 text-orange-600" />}
                                          <span className="text-[#737373] uppercase tracking-tighter">{entity.type}:</span>
                                          <span className="text-[#1A1A1A] truncate max-w-[150px]">{entity.title || entity.description}</span>
                                          <span className="opacity-30 group-hover:opacity-100 transition-opacity">🔗</span>
                                        </div>
                                      </a>
                                    ))}
                                    {extraEntitiesCount > 0 && (
                                      <button
                                        type="button"
                                        onClick={() => setEntityModal({ entities: allEntities })}
                                        className="flex items-center gap-2 px-3 py-1.5 bg-[#F5F5F4] border border-dashed border-[#D4D4D4] rounded-lg text-[10px] font-bold text-[#525252] hover:border-[#1A1A1A] hover:bg-white hover:text-[#111827] transition-all"
                                      >
                                        +{extraEntitiesCount} more
                                      </button>
                                    )}
                                  </>
                                );
                              })()}
                              {/* References as small bubbles (if not already in entities) */}
                              {(msg.content as AgentResponse).references.filter(ref => 
                                !(msg.content as AgentResponse).entities.some(e => {
                                  const ent = e as any;
                                  const entUrl = ent.url as string | undefined;
                                  const entTitle = (ent.title || '').toLowerCase();
                                  const refTitle = (ref.title || '').toLowerCase();
                                  return (
                                    ent.id === ref.source_id ||
                                    ent.source_id === ref.source_id ||
                                    (!!entUrl && entUrl === ref.source_id) ||
                                    (entTitle && refTitle && entTitle === refTitle)
                                  );
                                })
                              ).map((ref, ri) => (
                                <a 
                                  key={`ref-${ri}`}
                                  href={ref.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="flex items-center gap-2 px-3 py-1.5 bg-white border border-[#E5E5E5] rounded-lg text-[10px] font-bold hover:border-[#1A1A1A] hover:shadow-sm transition-all group"
                                >
                                  {ref.source_type === 'jira' && <Trello className="w-3 h-3 text-blue-600" />}
                                  {ref.source_type === 'monday' && <CheckCircle2 className="w-3 h-3 text-indigo-600" />}
                                  {ref.source_type === 'doc' && <FileText className="w-3 h-3 text-amber-600" />}
                                  {ref.source_type === 'zoom' && <Video className="w-3 h-3 text-orange-600" />}
                                  <span className="text-[#1A1A1A] truncate max-w-[150px]">{ref.title || ref.source_id}</span>
                                  <span className="opacity-30 group-hover:opacity-100 transition-opacity">🔗</span>
                                </a>
                              ))}
                            </div>
                          )}

                          {(msg.content as AgentResponse).suggestions && (msg.content as AgentResponse).suggestions!.length > 0 && (
                            <div className="flex flex-wrap gap-2 pt-4 border-t border-[#F5F5F4]">
                              {(msg.content as AgentResponse).suggestions!.map((suggestion, si) => (
                                <button
                                  key={si}
                                  onClick={() => handleSendMessage(suggestion)}
                                  className="px-3 py-1.5 bg-[#F5F5F4] text-[#1A1A1A] rounded-full text-[10px] font-bold hover:bg-[#1A1A1A] hover:text-white transition-all border border-transparent hover:border-[#1A1A1A]"
                                >
                                  {suggestion}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>

            {/* Input Area */}
            <div className="p-6 bg-white border-t border-[#E5E5E5]">
              <div className="max-w-3xl mx-auto relative">
                <input 
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
                  placeholder="Ask about features, bugs, or decisions..."
                  className="w-full pl-6 pr-14 py-4 bg-[#F5F5F4] border-none rounded-2xl text-sm focus:ring-2 focus:ring-[#1A1A1A] transition-all"
                />
                <button 
                  onClick={() => handleSendMessage()}
                  disabled={loading || !input.trim()}
                  className="absolute right-2 top-2 bottom-2 w-10 bg-[#1A1A1A] text-white rounded-xl flex items-center justify-center disabled:opacity-50 transition-opacity"
                >
                  {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                </button>
              </div>
        </div>

        {entityModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
            <div className="bg-white rounded-2xl shadow-xl max-w-2xl w-full max-h-[70vh] p-6 flex flex-col">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-[#111827]">All related entities</h2>
                <button
                  type="button"
                  onClick={() => setEntityModal(null)}
                  className="p-1 rounded-full hover:bg-[#F3F4F6] text-[#4B5563]"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="space-y-2 max-h-[60vh] overflow-y-auto pr-2 scrollbar-hide">
                {entityModal.entities.map((entity, idx) => (
                  <a
                    key={`modal-entity-${idx}`}
                    href={entity.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center justify-between gap-3 px-3 py-2 bg-white border border-[#E5E5E5] rounded-lg text-[11px] hover:border-[#1A1A1A] hover:shadow-sm transition-all"
                  >
                    <div className="flex items-center gap-2">
                      {entity.source_type === 'jira' && <Trello className="w-3 h-3 text-blue-600" />}
                      {entity.source_type === 'monday' && <CheckCircle2 className="w-3 h-3 text-indigo-600" />}
                      {entity.source_type === 'doc' && <FileText className="w-3 h-3 text-amber-600" />}
                      {entity.source_type === 'zoom' && <Video className="w-3 h-3 text-orange-600" />}
                      <span className="text-[#737373] uppercase tracking-tighter">{entity.type}:</span>
                      <span className="text-[#111827] truncate max-w-[260px]">
                        {entity.title || entity.description}
                      </span>
                    </div>
                    {entity.status && (
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#F3F4F6] text-[#4B5563]">
                        {entity.status}
                      </span>
                    )}
                  </a>
                ))}
              </div>
            </div>
          </div>
        )}
          </div>

          {/* Right Sidebar: Product Context */}
          <AnimatePresence>
            {showSidebar && (
              <motion.div
                key="product-context"
                initial={false}
                animate={{ x: 0, opacity: 1 }}
                exit={{ x: 300, opacity: 0 }}
                className="w-80 min-w-[20rem] flex-shrink-0 border-l border-[#E5E5E5] bg-white flex flex-col hidden lg:flex"
              >
                <div className="p-6 border-b border-[#E5E5E5] flex items-center justify-between">
                  <h2 className="font-bold text-sm uppercase tracking-widest flex items-center gap-2">
                    <Database className="w-4 h-4" />
                    Product Context
                  </h2>
                  <button onClick={() => setShowSidebar(false)} className="text-[#737373] hover:text-[#1A1A1A]">
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>

                <div className="flex-1 overflow-y-auto p-6 space-y-8">
                  {lastAssistantMessage ? (
                    <>
                      {/* Stats */}
                      <div className="grid grid-cols-2 gap-3">
                        {productContextStats?.map((stat) => (
                          <div key={stat.entityType} className="p-3 bg-[#F5F5F4] rounded-xl">
                            <div className="text-xl font-bold">{stat.count}</div>
                            <div className="text-[10px] uppercase font-bold text-[#737373]">
                              {stat.label}
                            </div>
                          </div>
                        ))}
                      </div>

                      {/* Entities Vertical Stack */}
                      <div className="space-y-4">
                        <h3 className="text-[10px] font-black uppercase tracking-widest text-[#737373]">Extracted Entities</h3>
                        <div className="space-y-3">
                          {lastAssistantMessage.entities.map((entity, ei) => (
                            <a
                              key={entity.id ?? entity.source_id ?? `entity-${ei}`} 
                              href={entity.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="block p-4 border border-[#E5E5E5] rounded-xl bg-white shadow-sm hover:border-[#1A1A1A] hover:shadow-md transition-all group"
                            >
                              <div className="flex items-center justify-between mb-2">
                                <div className="flex items-center gap-1.5">
                                  {entity.source_type === 'jira' && <Trello className="w-3 h-3 text-blue-600" />}
                                  {entity.source_type === 'monday' && <CheckCircle2 className="w-3 h-3 text-indigo-600" />}
                                  {entity.source_type === 'doc' && <FileText className="w-3 h-3 text-amber-600" />}
                                  {entity.source_type === 'zoom' && <Video className="w-3 h-3 text-orange-600" />}
                                  <span className="text-[9px] font-black uppercase text-[#737373]">{entity.type}</span>
                                </div>
                                {getStatusBadge(entity.status)}
                              </div>
                              <div className="text-xs font-bold mb-2 leading-tight group-hover:text-blue-600 transition-colors">{entity.title || entity.description}</div>
                              <div className="flex items-center justify-between text-[9px] font-medium text-[#737373]">
                                <span className="capitalize">{entity.source_type || 'Unknown'}</span>
                                <span>{entity.lastModified || 'Recent'}</span>
                              </div>
                            </a>
                          ))}
                        </div>
                      </div>
                    </>
                  ) : (
                    <div className="h-full flex flex-col items-center justify-center text-center p-8">
                      <Database className="w-8 h-8 text-[#E5E5E5] mb-4" />
                      <p className="text-xs text-[#737373]">Ask a question to populate the product context.</p>
                    </div>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {!showSidebar && (
            <button 
              onClick={() => setShowSidebar(true)}
              className="absolute right-6 top-6 w-10 h-10 bg-white border border-[#E5E5E5] rounded-full flex items-center justify-center shadow-sm hover:shadow-md transition-all hidden lg:flex"
            >
              <Database className="w-4 h-4" />
            </button>
          )}
        </div>
        ) : (
          <div className="flex-1 overflow-y-auto bg-[#FBFBFA]">
            {/* Hero Section */}
            <div className="bg-white border-b border-[#E5E5E5] px-8 py-12">
              <div className="max-w-5xl mx-auto flex flex-col md:flex-row items-center justify-between gap-8">
                <div>
                  <h1 className="text-4xl font-black tracking-tight mb-4">Connect your tools and map data to Product OS</h1>
                  <p className="text-lg text-[#737373] max-w-xl">
                    Automate your product research by syncing data from Jira, Slack, GitHub and more. 
                    Map external fields to Product OS entities in seconds.
                  </p>
                </div>
                <button 
                  onClick={() => {
                    setIsWizardOpen(true);
                    setWizardStep(1);
                    setSelectedProviderForWizard(null);
                  }}
                  className="px-8 py-4 bg-blue-600 text-white rounded-2xl font-bold text-lg hover:bg-blue-700 transition-all shadow-xl shadow-blue-100 flex items-center gap-3 group"
                >
                  <Plus className="w-6 h-6 group-hover:rotate-90 transition-transform" />
                  Add New Integration
                </button>
              </div>
            </div>

            <div className="max-w-5xl mx-auto p-8">
              <div className="grid grid-cols-1 gap-12">
                {/* Service Grid */}
                <section>
                  <div className="flex items-center justify-between mb-6">
                    <h2 className="text-xl font-bold">Connected Services</h2>
                    <span className="text-xs text-[#737373] font-medium">Click a service to manage mappings</span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                        {config && INTEGRATION_PROVIDERS.filter(p => config.integrations[p.id]).map((provider) => (
                      <button 
                        key={provider.id} 
                        onClick={() => setSelectedServiceForMapping(provider.id)}
                        className={`p-5 rounded-2xl border transition-all text-left relative group ${
                          selectedServiceForMapping === provider.id 
                            ? 'bg-white border-blue-600 shadow-lg ring-2 ring-blue-50' 
                            : 'bg-white border-[#E5E5E5] hover:border-blue-400 hover:shadow-md'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-4">
                          <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${provider.bg} ${provider.color}`}>
                            <provider.icon className="w-5 h-5" />
                          </div>
                          <div className="flex items-center gap-1 text-emerald-600">
                            <CheckCircle2 className="w-4 h-4" />
                            <span className="text-[10px] font-bold uppercase tracking-wider">Connected</span>
                          </div>
                        </div>
                        <h3 className="font-bold text-lg mb-1">{provider.name}</h3>
                        <p className="text-xs text-[#737373]">Last synced 2m ago</p>
                        
                        {selectedServiceForMapping === provider.id && (
                          <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-12 h-1 bg-blue-600 rounded-full" />
                        )}
                      </button>
                    ))}

                    {/* Coming soon providers (phase 1 excludes non-Monday integrations) */}
                    {INTEGRATION_PROVIDERS.filter(p => p.id !== 'monday').map((provider) => (
                      <div key={provider.id} className="p-5 rounded-2xl border border-dashed border-[#E5E5E5] bg-white opacity-80">
                        <div className="flex items-center justify-between mb-4">
                          <div className={`w-10 h-10 rounded-xl flex items-center justify-center bg-gray-50 text-gray-400`}>
                            <provider.icon className="w-5 h-5" />
                          </div>
                          <div className="flex items-center gap-1 text-gray-400">
                            <div className="w-2 h-2 rounded-full bg-gray-300" />
                            <span className="text-[10px] font-bold uppercase tracking-wider">Coming Soon</span>
                          </div>
                        </div>
                        <h3 className="font-bold text-lg mb-1 text-gray-400">{provider.name}</h3>
                        <p className="text-xs text-gray-400">Available in a future phase</p>
                      </div>
                    ))}
                  </div>
                </section>

                {/* Field Mappings for Selected Service */}
                {selectedServiceForMapping && config?.integrations[selectedServiceForMapping] && (
                  <section ref={mappingsRef} className="bg-white border border-[#E5E5E5] rounded-3xl overflow-hidden shadow-sm">
                    <div className="p-6 border-b border-[#E5E5E5] flex items-center justify-between bg-[#FBFBFA]">
                      <h2 className="text-lg font-bold flex items-center gap-2">
                        <Settings className="w-5 h-5" />
                        Field Mappings: <span className="capitalize text-blue-600">{selectedServiceForMapping}</span>
                      </h2>
                      <div className="flex items-center gap-4">
                        <span className="text-xs text-[#737373] font-medium">Auto-sync enabled</span>
                        <button 
                          onClick={async () => {
                            const currentService = selectedServiceForMapping as string;
                            const next = editingService === currentService ? null : currentService;
                            setEditingService(next);
                            setActiveTargetEntity(null);
                            setActiveSourceField(null);
                            if (next === 'monday' && mondayBoards.length === 0) {
                              setMondaySchemaLoading(true);
                              setMondaySchemaError(null);
                              try {
                                const res = await fetch(`${RESEARCH_API_URL}/integrations/monday/schema`);
                                if (!res.ok) {
                                  throw new Error(`Schema request failed: ${res.status}`);
                                }
                                const data = await res.json();
                                setMondayBoards(data.boards || []);
                              } catch (e) {
                                console.error('Failed to load Monday schema', e);
                                setMondaySchemaError('Failed to load Monday boards. Check Monday API key and integration config.');
                              } finally {
                                setMondaySchemaLoading(false);
                              }
                            }
                          }}
                          className="px-4 py-1.5 rounded-full text-xs font-bold transition-all bg-[#1A1A1A] text-white hover:bg-opacity-90"
                        >
                          {editingService === selectedServiceForMapping ? 'Close Editor' : 'Edit Mappings'}
                        </button>
                      </div>
                    </div>
                    
                    <div className="p-6">
                      {editingService === selectedServiceForMapping ? (
                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 p-6 bg-[#FBFBFA] rounded-2xl border border-[#E5E5E5]">
                          {selectedServiceForMapping === 'monday' && (
                            <div className="lg:col-span-3 mb-4 space-y-4">
                              <h4 className="text-[10px] font-black uppercase tracking-widest text-[#737373]">1. Select Product OS entities</h4>
                              <div className="flex flex-wrap gap-2">
                                {osEntityTypes.map(entityType => {
                                  const label = entityType
                                    .split('_')
                                    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
                                    .join(' ');
                                  const checked = selectedOsEntityTypes.includes(entityType);
                                  return (
                                    <button
                                      key={entityType}
                                      type="button"
                                      onClick={() => {
                                        setSelectedOsEntityTypes(prev =>
                                          checked
                                            ? prev.filter(e => e !== entityType)
                                            : [...prev, entityType]
                                        );
                                      }}
                                      className={`px-3 py-1 rounded-full text-[10px] font-bold border ${
                                        checked
                                          ? 'bg-indigo-600 text-white border-indigo-600'
                                          : 'bg-white text-[#737373] border-[#E5E5E5]'
                                      }`}
                                    >
                                      {label}
                                    </button>
                                  );
                                })}
                                {osEntityTypes.length === 0 && (
                                  <span className="text-xs text-[#737373]">
                                    No Product OS entity types available.
                                  </span>
                                )}
                              </div>
                              <h4 className="text-[10px] font-black uppercase tracking-widest text-[#737373]">2. Monday Boards</h4>
                              {mondaySchemaLoading && (
                                <p className="text-xs text-[#737373]">Loading boards from Monday…</p>
                              )}
                              {mondaySchemaError && (
                                <p className="text-xs text-red-600">{mondaySchemaError}</p>
                              )}
                              {!mondaySchemaLoading && !mondaySchemaError && mondayBoards.length > 0 && (
                                <div className="flex flex-wrap gap-2">
                                  {mondayBoards.map(board => (
                                    <span
                                      key={board.id}
                                      className="px-2 py-1 bg-white border border-[#E5E5E5] rounded text-[10px] font-medium"
                                    >
                                      {board.name}
                                    </span>
                                  ))}
                                </div>
                              )}
                              {!mondaySchemaLoading && !mondaySchemaError && mondayBoards.length === 0 && (
                                <p className="text-xs text-[#737373]">
                                  No boards found for your Monday account, or the token does not have access.
                                </p>
                              )}
                            </div>
                          )}
                          {selectedServiceForMapping === 'monday' && (
                            <div className="lg:col-span-3 mb-4 space-y-3">
                              <div className="space-y-1">
                                <label className="text-[10px] font-bold text-[#737373] uppercase">Monday subdomain (for item links)</label>
                                <input
                                  type="text"
                                  placeholder="e.g. my-team → https://my-team.monday.com"
                                  value={mondaySubdomain}
                                  onChange={(e) => setMondaySubdomain(e.target.value)}
                                  className="w-full px-3 py-2 border border-[#E5E5E5] rounded-lg text-xs bg-white placeholder:text-[#A3A3A3]"
                                />
                                <p className="text-[10px] text-[#737373]">Your board URL is https://<strong>{mondaySubdomain || '…'}</strong>.monday.com — enter the subdomain only.</p>
                              </div>
                              <h4 className="text-[10px] font-black uppercase tracking-widest text-[#737373]">3. Entity ↔ Board mappings</h4>
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                {selectedOsEntityTypes.map(entityType => {
                                  const label = entityType
                                    .split('_')
                                    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
                                    .join(' ');
                                  const defaultDirection: MondayDirection =
                                    entityType === 'bug' || entityType === 'support_ticket'
                                      ? 'monday_to_os'
                                      : 'two_way';
                                  const current: MondayEntityMappingConfig = mondayEntityConfigs[entityType] || {
                                    entity_type: entityType,
                                    board_ids: [],
                                    direction: defaultDirection,
                                    field_mappings: {},
                                  };
                                  const selectedBoardId = current.board_ids[0] || '';
                                  return (
                                    <div key={entityType} className="p-4 rounded-xl bg-white border border-[#E5E5E5] space-y-2">
                                      <div className="flex items-center justify-between">
                                        <span className="text-xs font-bold text-[#1A1A1A]">{label}</span>
                                        <span className="text-[10px] text-[#737373] font-mono">{current.entity_type}</span>
                                      </div>
                                      <div className="space-y-2">
                                        <label className="text-[10px] font-bold text-[#737373] uppercase">Board</label>
                                        <select
                                          value={selectedBoardId}
                                          onChange={(e) => {
                                            const value = e.target.value;
                                            setMondayEntityConfigs(prev => {
                                              const nextBoardIds = value ? [value] : [];
                                              const boardChanged = value !== selectedBoardId;
                                              return {
                                                ...prev,
                                                [entityType]: {
                                                  entity_type: entityType,
                                                  direction: current.direction || defaultDirection,
                                                  board_ids: nextBoardIds,
                                                  // If the board changes, clear field mappings so the user remaps columns.
                                                  field_mappings: boardChanged ? {} : current.field_mappings || {},
                                                },
                                              };
                                            });
                                          }}
                                          className="w-full px-3 py-2 border border-[#E5E5E5] rounded-lg text-xs bg-white"
                                        >
                                          <option value="">Select a board…</option>
                                          {mondayBoards.map(board => (
                                            <option key={board.id} value={board.id}>{board.name}</option>
                                          ))}
                                        </select>
                                      </div>
                                      <div className="space-y-1">
                                        <label className="text-[10px] font-bold text-[#737373] uppercase">Sync direction</label>
                                        <div className="flex gap-2">
                                          <button
                                            type="button"
                                            onClick={() => {
                                              setMondayEntityConfigs(prev => ({
                                                ...prev,
                                                [entityType]: {
                                                  entity_type: entityType,
                                                  board_ids: current.board_ids,
                                                  field_mappings: current.field_mappings || {},
                                                  direction: 'two_way',
                                                },
                                              }));
                                            }}
                                            className={`flex-1 px-2 py-1 rounded-full text-[10px] font-bold border ${
                                              (current.direction || option.defaultDirection) === 'two_way'
                                                ? 'bg-blue-600 text-white border-blue-600'
                                                : 'bg-white text-[#737373] border-[#E5E5E5]'
                                            }`}
                                          >
                                            Two-way
                                          </button>
                                          <button
                                            type="button"
                                            onClick={() => {
                                              setMondayEntityConfigs(prev => ({
                                                ...prev,
                                                [entityType]: {
                                                  entity_type: entityType,
                                                  board_ids: current.board_ids,
                                                  field_mappings: current.field_mappings || {},
                                                  direction: 'monday_to_os',
                                                },
                                              }));
                                            }}
                                            className={`flex-1 px-2 py-1 rounded-full text-[10px] font-bold border ${
                                              (current.direction || option.defaultDirection) === 'monday_to_os'
                                                ? 'bg-indigo-600 text-white border-indigo-600'
                                                : 'bg-white text-[#737373] border-[#E5E5E5]'
                                            }`}
                                          >
                                            Monday → Product OS
                                          </button>
                                        </div>
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                              <div className="flex justify-end">
                                <button
                                  type="button"
                                  onClick={async () => {
                                    if (!mondayConfig) return;
                                    setMondayConnectError(null);
                                    setMondayPrepareMessage(null);
                                    setMondayPrepareStatus('idle');
                                    setMondayPrepareStats(null);
                                    try {
                                      const activeConfigs = Object.entries(mondayEntityConfigs).filter(
                                        ([entityType, cfg]) =>
                                          selectedOsEntityTypes.includes(entityType) &&
                                          Array.isArray(cfg.board_ids) &&
                                          cfg.board_ids.length > 0
                                      );
                                      if (activeConfigs.length === 0) {
                                        throw new Error('Select at least one Product OS entity and board before preparing for search.');
                                      }
                                      const allBoardIds = Array.from(
                                        new Set(
                                          activeConfigs.flatMap(([, cfg]) => cfg.board_ids || [])
                                        )
                                      );
                                      const entityMappings: Record<string, string> = {};
                                      activeConfigs.forEach(([, cfg]) => {
                                        (cfg.board_ids || []).forEach(boardId => {
                                          entityMappings[boardId] = cfg.entity_type;
                                        });
                                      });
                                      const entityConfigsPayload: Record<string, MondayEntityMappingConfig> = {};
                                      activeConfigs.forEach(([entityType, cfg]) => {
                                        entityConfigsPayload[entityType] = cfg;
                                      });
                                      const payload = {
                                        enabled: true,
                                        api_key: null as string | null,
                                        board_ids: allBoardIds,
                                        entity_mappings: entityMappings,
                                        entity_configs: entityConfigsPayload,
                                        sync_interval_seconds: mondayConfig.sync_interval_seconds,
                                        subdomain: (mondaySubdomain || mondayConfig?.subdomain || '').trim() || null,
                                      };
                                      const res = await fetch(`${RESEARCH_API_URL}/integrations/monday`, {
                                        method: 'PUT',
                                        headers: { 'Content-Type': 'application/json' },
                                        body: JSON.stringify(payload),
                                      });
                                      if (!res.ok) {
                                        const err = await res.json().catch(() => ({}));
                                        throw new Error(err.detail || `Failed to save mappings (${res.status})`);
                                      }
                                      const updated: MondayIntegrationConfigResponse = await res.json();
                                      setMondayConfig(updated);
                                      setMondaySubdomain(updated.subdomain ?? '');
                                      if (updated.entity_configs) {
                                        setMondayEntityConfigs(updated.entity_configs);
                                      }

                                      // Immediately run a Monday-only sync to prepare data for search.
                                      setMondayPrepareStatus('preparing');
                                      const prepRes = await fetch(`${RESEARCH_API_URL}/integrations/monday/prepare`, {
                                        method: 'POST',
                                        headers: { 'Content-Type': 'application/json' },
                                      });
                                      if (!prepRes.ok) {
                                        const err = await prepRes.json().catch(() => ({}));
                                        throw new Error(err.detail || `Failed to prepare Monday data for search (${prepRes.status})`);
                                      }
                                      const prep = await prepRes.json() as {
                                        ok: boolean;
                                        detail: string;
                                        fetched: number;
                                        embedded: number;
                                        errors: number;
                                        total_entities: number;
                                      };
                                      setMondayPrepareStatus(prep.ok ? 'ok' : 'error');
                                      setMondayPrepareMessage(prep.detail);
                                      setMondayPrepareStats({
                                        fetched: prep.fetched,
                                        embedded: prep.embedded,
                                        totalEntities: prep.total_entities,
                                      });
                                    } catch (e) {
                                      const msg = e instanceof Error ? e.message : 'Failed to save and prepare Monday mappings.';
                                      setMondayConnectError(msg);
                                      setMondayPrepareStatus('error');
                                    }
                                  }}
                                  className="px-4 py-2 bg-blue-600 text-white text-xs font-bold rounded-full hover:bg-blue-700 transition-colors"
                                >
                                  Save &amp; Prepare for Search
                                </button>
                              </div>
                              <div className="mt-2 space-y-1">
                                {mondayPrepareStatus === 'preparing' && !mondayConnectError && (
                                  <p className="text-xs text-[#737373]">
                                    Syncing Monday data and indexing for search…
                                  </p>
                                )}
                                {mondayPrepareStatus === 'ok' && mondayPrepareStats && (
                                  <div className="text-xs text-emerald-600 space-y-0.5">
                                    <p>
                                      {mondayPrepareStats.embedded > 0
                                        ? `Search ready: embedded ${mondayPrepareStats.embedded} new Monday items for Product OS search.`
                                        : `Search ready: Monday data is already indexed (0 new items in this run).`}
                                    </p>
                                    <p className="text-[11px] text-emerald-700/80">
                                      Total Monday entities in Product OS: {mondayPrepareStats.totalEntities}.
                                    </p>
                                  </div>
                                )}
                                {mondayConnectError && (
                                  <p className="text-xs text-red-600">{mondayConnectError}</p>
                                )}
                                {mondayPrepareStatus === 'error' && !mondayConnectError && mondayPrepareMessage && (
                                  <p className="text-xs text-red-600">{mondayPrepareMessage}</p>
                                )}
                              </div>
                            </div>
                          )}
                          {/* Step 1: Select Target Entity */}
                          <div className="space-y-3">
                            <h4 className="text-[10px] font-black uppercase tracking-widest text-[#737373] mb-4">1. Select Product Entity</h4>
                            <div className="space-y-2 max-h-[400px] overflow-y-auto pr-2 scrollbar-hide">
                              {selectedServiceForMapping === 'monday'
                                ? (() => {
                                    const entityType = activeMondayEntityTypeForFields;
                                    const canonicalFields = entityType ? PRODUCT_OS_ENTITY_FIELDS[entityType] || [] : [];
                                    const currentConfig =
                                      entityType && mondayEntityConfigs[entityType]
                                        ? mondayEntityConfigs[entityType]
                                        : null;
                                    const selectedBoardId = currentConfig?.board_ids?.[0] || '';
                                    const selectedBoard = selectedBoardId
                                      ? mondayBoards.find(b => b.id === selectedBoardId)
                                      : undefined;
                                    const fieldMappings = currentConfig?.field_mappings || {};

                                    if (!entityType) {
                                      return (
                                        <p className="text-xs text-[#737373]">
                                          Select a Product OS entity above to start mapping fields.
                                        </p>
                                      );
                                    }

                                    if (!selectedBoard) {
                                      return (
                                        <p className="text-xs text-[#737373]">
                                          Select a Monday board for this entity in step 3 above to map fields.
                                        </p>
                                      );
                                    }

                                    if (canonicalFields.length === 0) {
                                      return (
                                        <p className="text-xs text-[#737373]">
                                          No canonical fields defined for this entity type.
                                        </p>
                                      );
                                    }

                                    return canonicalFields.map(fieldName => {
                                      const mappedSourceId =
                                        Object.entries(fieldMappings).find(
                                          ([, target]) => target === fieldName,
                                        )?.[0] || null;
                                      const mappedColumnTitle =
                                        mappedSourceId &&
                                        selectedBoard.columns.find(c => c.id === mappedSourceId)?.title;
                                      const isSelected = activeTargetEntity === fieldName;
                                      return (
                                        <motion.button
                                          key={fieldName}
                                          whileHover={{ scale: 1.02 }}
                                          whileTap={{ scale: 0.98 }}
                                          onClick={() => {
                                            setActiveTargetEntity(fieldName);
                                            setActiveSourceField(mappedSourceId);
                                          }}
                                          className={`w-full p-4 rounded-xl border text-left transition-all flex items-center justify-between group ${
                                            isSelected
                                              ? 'bg-indigo-600 border-indigo-600 text-white shadow-lg'
                                              : 'bg-white border-[#E5E5E5] hover:border-indigo-400'
                                          }`}
                                        >
                                          <div className="flex flex-col">
                                            <span
                                              className={`text-xs font-mono font-bold ${
                                                isSelected ? 'text-white' : 'text-indigo-600'
                                              }`}
                                            >
                                              {formatEntityTypeLabel(entityType)}.{fieldName}
                                            </span>
                                            {mappedColumnTitle && !isSelected && (
                                              <span className="text-[10px] text-[#737373]">
                                                Mapped to: {mappedColumnTitle}
                                              </span>
                                            )}
                                          </div>
                                          <ChevronRight
                                            className={`w-4 h-4 transition-transform ${
                                              isSelected ? 'translate-x-1' : 'opacity-0 group-hover:opacity-100'
                                            }`}
                                          />
                                        </motion.button>
                                      );
                                    });
                                  })()
                                : TARGET_ENTITIES.map(entity => {
                                    const currentSource = config
                                      ? Object.entries(
                                          config.mappings[selectedServiceForMapping] || {},
                                        ).find(([, target]) => target === entity)?.[0]
                                      : null;
                                    const isSelected = activeTargetEntity === entity;
                                    return (
                                      <motion.button
                                        key={entity}
                                        whileHover={{ scale: 1.02 }}
                                        whileTap={{ scale: 0.98 }}
                                        onClick={() => {
                                          setActiveTargetEntity(entity);
                                          setActiveSourceField(currentSource || null);
                                        }}
                                        className={`w-full p-4 rounded-xl border text-left transition-all flex items-center justify-between group ${
                                          isSelected
                                            ? 'bg-indigo-600 border-indigo-600 text-white shadow-lg'
                                            : 'bg-white border-[#E5E5E5] hover:border-indigo-400'
                                        }`}
                                      >
                                        <div className="flex flex-col">
                                          <span
                                            className={`text-xs font-mono font-bold ${
                                              isSelected ? 'text-white' : 'text-indigo-600'
                                            }`}
                                          >
                                            {entity}
                                          </span>
                                          {currentSource && !isSelected && (
                                            <span className="text-[10px] text-[#737373]">
                                              Mapped to: {currentSource}
                                            </span>
                                          )}
                                        </div>
                                        <ChevronRight
                                          className={`w-4 h-4 transition-transform ${
                                            isSelected ? 'translate-x-1' : 'opacity-0 group-hover:opacity-100'
                                          }`}
                                        />
                                      </motion.button>
                                    );
                                  })}
                            </div>
                          </div>

                          {/* Step 2: Select Source Field */}
                          <div className="space-y-3">
                            <div className="flex items-center justify-between mb-4">
                              <h4 className="text-[10px] font-black uppercase tracking-widest text-[#737373]">2. Select {selectedServiceForMapping} Field</h4>
                              {activeTargetEntity && activeSourceField && (
                                <button 
                                  onClick={() => {
                                    if (selectedServiceForMapping === 'monday') {
                                      const entityType = activeMondayEntityTypeForFields;
                                      if (!entityType) return;
                                      setMondayEntityConfigs(prev => {
                                        const current = prev[entityType] || {
                                          entity_type: entityType,
                                          board_ids: [],
                                          direction: 'two_way' as MondayDirection,
                                          field_mappings: {},
                                        };
                                        const nextFieldMappings = { ...(current.field_mappings || {}) };
                                        const sourceToClear = Object.entries(nextFieldMappings).find(
                                          ([, target]) => target === activeTargetEntity,
                                        )?.[0];
                                        if (sourceToClear) {
                                          delete nextFieldMappings[sourceToClear];
                                        }
                                        return {
                                          ...prev,
                                          [entityType]: {
                                            ...current,
                                            field_mappings: nextFieldMappings,
                                          },
                                        };
                                      });
                                      setActiveSourceField(null);
                                    } else if (config) {
                                      const newConfig = { ...config };
                                      const currentMaps = {
                                        ...newConfig.mappings[selectedServiceForMapping],
                                      };
                                      const sourceToClear = Object.entries(currentMaps).find(
                                        ([, target]) => target === activeTargetEntity,
                                      )?.[0];
                                      if (sourceToClear) {
                                        delete currentMaps[sourceToClear];
                                        newConfig.mappings[selectedServiceForMapping] = currentMaps;
                                        setConfig(newConfig);
                                        setActiveSourceField(null);
                                      }
                                    }
                                  }}
                                  className="flex items-center gap-1 text-[10px] font-bold text-red-500 hover:text-red-600 transition-colors"
                                >
                                  <X className="w-3 h-3" />
                                  Remove
                                </button>
                              )}
                            </div>
                            <div className="space-y-2 max-h-[400px] overflow-y-auto pr-2 scrollbar-hide">
                              {selectedServiceForMapping === 'monday'
                                ? (() => {
                                    const entityType = activeMondayEntityTypeForFields;
                                    const current =
                                      entityType && mondayEntityConfigs[entityType]
                                        ? mondayEntityConfigs[entityType]
                                        : null;
                                    const selectedBoardId = current?.board_ids?.[0] || '';
                                    const selectedBoard = selectedBoardId
                                      ? mondayBoards.find(b => b.id === selectedBoardId)
                                      : undefined;
                                    if (!entityType || !activeTargetEntity) {
                                      return (
                                        <p className="text-xs text-[#B0B0B0]">
                                          Select a Product OS field on the left to map it to a Monday column.
                                        </p>
                                      );
                                    }
                                    if (!selectedBoard) {
                                      return (
                                        <p className="text-xs text-[#B0B0B0]">
                                          Select a Monday board for this entity in step 3 above.
                                        </p>
                                      );
                                    }
                                    if (!selectedBoard.columns.length) {
                                      return (
                                        <p className="text-xs text-[#B0B0B0]">
                                          This board does not expose any columns for mapping.
                                        </p>
                                      );
                                    }
                                    return selectedBoard.columns.map(column => {
                                      const fieldId = column.id;
                                      const isSelected = activeSourceField === fieldId;
                                      return (
                                        <motion.button
                                          key={fieldId}
                                          disabled={!activeTargetEntity}
                                          whileHover={activeTargetEntity ? { scale: 1.02 } : {}}
                                          onClick={() => {
                                            if (!activeTargetEntity) return;
                                            setMondayEntityConfigs(prev => {
                                              const currentCfg = prev[entityType] || {
                                                entity_type: entityType,
                                                board_ids: current?.board_ids || [],
                                                direction: current?.direction || ('two_way' as MondayDirection),
                                                field_mappings: current?.field_mappings || {},
                                              };
                                              const nextFieldMappings = {
                                                ...(currentCfg.field_mappings || {}),
                                              };
                                              // Ensure one-to-one: remove any existing mapping for this target field.
                                              const existingSource = Object.entries(nextFieldMappings).find(
                                                ([, target]) => target === activeTargetEntity,
                                              )?.[0];
                                              if (existingSource) {
                                                delete nextFieldMappings[existingSource];
                                              }
                                              nextFieldMappings[fieldId] = activeTargetEntity;
                                              return {
                                                ...prev,
                                                [entityType]: {
                                                  ...currentCfg,
                                                  field_mappings: nextFieldMappings,
                                                },
                                              };
                                            });
                                            setActiveSourceField(fieldId);
                                          }}
                                          className={`w-full p-4 rounded-xl border text-left transition-all flex items-center justify-between ${
                                            isSelected
                                              ? 'bg-emerald-50 border-emerald-500 text-emerald-700'
                                              : 'bg-white border-[#E5E5E5]'
                                          } ${
                                            !activeTargetEntity
                                              ? 'opacity-50 cursor-not-allowed'
                                              : 'hover:border-emerald-400'
                                          }`}
                                        >
                                          <span className="text-sm font-bold">{column.title || fieldId}</span>
                                          {isSelected && (
                                            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                                          )}
                                        </motion.button>
                                      );
                                    });
                                  })()
                                : (SERVICE_FIELDS[selectedServiceForMapping] || []).map(field => {
                                    const isSelected = activeSourceField === field;
                                    return (
                                      <motion.button
                                        key={field}
                                        disabled={!activeTargetEntity}
                                        whileHover={activeTargetEntity ? { scale: 1.02 } : {}}
                                        onClick={() => {
                                          if (config && activeTargetEntity) {
                                            const newConfig = { ...config };
                                            const currentMaps = {
                                              ...(newConfig.mappings[selectedServiceForMapping] || {}),
                                            };
                                            const oldSource = Object.entries(currentMaps).find(
                                              ([, target]) => target === activeTargetEntity,
                                            )?.[0];
                                            if (oldSource) delete currentMaps[oldSource];
                                            currentMaps[field] = activeTargetEntity;
                                            newConfig.mappings[selectedServiceForMapping] = currentMaps;
                                            setConfig(newConfig);
                                            setActiveSourceField(field);
                                          }
                                        }}
                                        className={`w-full p-4 rounded-xl border text-left transition-all flex items-center justify-between ${
                                          isSelected
                                            ? 'bg-emerald-50 border-emerald-500 text-emerald-700'
                                            : 'bg-white border-[#E5E5E5]'
                                        } ${
                                          !activeTargetEntity
                                            ? 'opacity-50 cursor-not-allowed'
                                            : 'hover:border-emerald-400'
                                        }`}
                                      >
                                        <span className="text-sm font-bold">{field}</span>
                                        {isSelected && <CheckCircle2 className="w-4 h-4 text-emerald-600" />}
                                      </motion.button>
                                    );
                                  })}
                            </div>
                          </div>

                          {/* Step 3: Preview */}
                          <div className="flex flex-col gap-4">
                            <h4 className="text-[10px] font-black uppercase tracking-widest text-[#737373] mb-0">3. Live Preview</h4>
                            <div className="flex-1 bg-[#1A1A1A] rounded-2xl p-6 text-white font-mono text-xs overflow-hidden flex flex-col">
                              <div className="flex items-center justify-between mb-4">
                                <span className="text-[10px] font-bold uppercase tracking-widest opacity-50">Transformation Logic</span>
                                <div className="flex gap-1">
                                  <div className="w-2 h-2 rounded-full bg-red-500" />
                                  <div className="w-2 h-2 rounded-full bg-amber-500" />
                                  <div className="w-2 h-2 rounded-full bg-emerald-500" />
                                </div>
                              </div>
                              <div className="space-y-4 flex-1">
                                <div>
                                  <div className="text-emerald-400 mb-1">// Source: {selectedServiceForMapping}</div>
                                  <pre className="opacity-70 whitespace-pre-wrap">
{`{
  "${activeSourceField || '...'}": "Sample data from ${selectedServiceForMapping}..."
}`}
                                  </pre>
                                </div>
                                <div className="flex justify-center">
                                  <ChevronRight className="w-4 h-4 rotate-90 opacity-30" />
                                </div>
                                <div>
                                  <div className="text-indigo-400 mb-1">// Target: Product OS</div>
                                  <pre className="whitespace-pre-wrap">
{selectedServiceForMapping === 'monday'
  ? `{
  "${activeMondayEntityTypeForFields ? formatEntityTypeLabel(activeMondayEntityTypeForFields) : 'Entity'}": {
    "${activeTargetEntity || 'field'}": "Sample data from ${selectedServiceForMapping}..."
  }
}`
  : `{
  "${activeTargetEntity?.split('.')[0] || 'Entity'}": {
    "${activeTargetEntity?.split('.')[1] || 'field'}": "Sample data from ${selectedServiceForMapping}..."
  }
}`}
                                  </pre>
                                </div>
                              </div>
                              
                              <div className="mt-6 p-4 bg-white/5 rounded-xl border border-white/10">
                                <div className="flex items-center gap-2 text-emerald-400 mb-1">
                                  <CheckCircle2 className="w-3 h-3" />
                                  <span className="text-[10px] font-bold uppercase tracking-widest">Auto-saved</span>
                                </div>
                                <p className="text-[10px] text-white/50">Changes are applied instantly to your integration pipeline.</p>
                              </div>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          {selectedServiceForMapping === 'monday'
                            ? (() => {
                                const enabledEntities = Object.entries(mondayEntityConfigs).filter(
                                  ([, cfg]) => Array.isArray(cfg.board_ids) && cfg.board_ids.length > 0,
                                );
                                if (enabledEntities.length === 0) {
                                  return (
                                    <div className="col-span-2 py-12 text-center bg-[#FBFBFA] rounded-2xl border border-dashed border-[#E5E5E5]">
                                      <p className="text-sm text-[#737373]">
                                        No Product OS entities are mapped yet for Monday.com.
                                      </p>
                                      <p className="text-xs text-[#737373] mt-1">
                                        Click &ldquo;Edit Mappings&rdquo; to choose entities and boards.
                                      </p>
                                    </div>
                                  );
                                }
                                return enabledEntities.map(([entityType, cfg]) => {
                                  const label = formatEntityTypeLabel(entityType);
                                  const boards = (cfg.board_ids || []).map(id => {
                                    const board = mondayBoards.find(b => b.id === id);
                                    return board?.name || id;
                                  });
                                  const directionLabel =
                                    cfg.direction === 'monday_to_os'
                                      ? 'Monday → Product OS'
                                      : 'Two-way';
                                  return (
                                    <div key={entityType} className="group">
                                      <div className="flex flex-col gap-2 p-4 bg-white border border-[#E5E5E5] rounded-xl">
                                        <div className="flex items-center justify-between">
                                          <span className="text-sm font-bold">{label}</span>
                                          <span className="text-[10px] font-mono text-[#737373]">
                                            {entityType}
                                          </span>
                                        </div>
                                        <div className="flex items-center justify-between text-xs text-[#737373]">
                                          <span>
                                            Boards:{' '}
                                            {boards.length > 0 ? boards.join(', ') : 'Not selected'}
                                          </span>
                                          <span className="font-semibold">{directionLabel}</span>
                                        </div>
                                      </div>
                                    </div>
                                  );
                                });
                              })()
                            : config &&
                              Object.entries(config.mappings[selectedServiceForMapping as string] || {}).map(
                                ([source, target]) => (
                                  <div key={source} className="group">
                                    <div className="flex items-center justify-between p-4 bg-white border border-[#E5E5E5] rounded-xl hover:border-blue-600 transition-colors">
                                      <div className="flex items-center gap-3">
                                        <span className="text-sm font-medium">{source}</span>
                                        <ChevronRight className="w-4 h-4 text-[#737373]" />
                                        <span className="text-sm font-mono text-indigo-600 font-semibold">
                                          {target}
                                        </span>
                                      </div>
                                      <div className="flex items-center gap-2 text-[10px] text-[#737373] opacity-0 group-hover:opacity-100 transition-opacity">
                                        <Database className="text-blue-600 w-3 h-3" />
                                        Active
                                      </div>
                                    </div>
                                  </div>
                                ),
                              )}
                          {selectedServiceForMapping !== 'monday' &&
                            (!config ||
                              Object.keys(
                                config.mappings[selectedServiceForMapping as string] || {},
                              ).length === 0) && (
                              <div className="col-span-2 py-12 text-center bg-[#FBFBFA] rounded-2xl border border-dashed border-[#E5E5E5]">
                                <p className="text-sm text-[#737373]">
                                  No field mappings defined for this service.
                                </p>
                                <button
                                  onClick={() => setEditingService(selectedServiceForMapping)}
                                  className="mt-4 text-sm font-bold text-blue-600 hover:underline"
                                >
                                  Start Mapping Fields
                                </button>
                              </div>
                            )}
                        </div>
                      )}
                    </div>
                  </section>
                )}

              </div>
            </div>

            {/* Integration Wizard Modal */}
            <AnimatePresence>
              {isWizardOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
                  <motion.div 
                    initial={{ scale: 0.9, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    exit={{ scale: 0.9, opacity: 0 }}
                    className="bg-white w-full max-w-4xl rounded-3xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
                  >
                    {/* Wizard Header */}
                    <div className="px-8 py-6 border-b border-[#E5E5E5] flex items-center justify-between bg-[#FBFBFA]">
                      <div className="flex items-center gap-4">
                        <div className="flex items-center gap-2">
                          {[1, 2, 3, 4].map((s) => (
                            <div 
                              key={s} 
                              className={`w-8 h-1 rounded-full transition-all ${
                                s <= wizardStep ? 'bg-blue-600' : 'bg-gray-200'
                              }`} 
                            />
                          ))}
                        </div>
                        <span className="text-xs font-bold text-[#737373] uppercase tracking-widest">Step {wizardStep} of 4</span>
                      </div>
                      <button onClick={() => setIsWizardOpen(false)} className="p-2 hover:bg-gray-100 rounded-full transition-colors">
                        <X className="w-5 h-5" />
                      </button>
                    </div>

                    {/* Wizard Content */}
                    <div className="flex-1 overflow-y-auto p-12">
                      <AnimatePresence mode="wait">
                        {wizardStep === 1 && (
                          <motion.div 
                            key="step1"
                            initial={{ x: 20, opacity: 0 }}
                            animate={{ x: 0, opacity: 1 }}
                            exit={{ x: -20, opacity: 0 }}
                            className="space-y-8"
                          >
                            <div className="text-center max-w-xl mx-auto">
                              <h2 className="text-3xl font-black mb-4">Select a Provider</h2>
                              <p className="text-[#737373]">Choose the tool you want to connect to Product OS.</p>
                            </div>

                            <div className="relative max-w-md mx-auto">
                              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-[#737373]" />
                              <input 
                                type="text" 
                                placeholder="Search integrations..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                className="w-full pl-12 pr-4 py-3 bg-[#F5F5F4] border-none rounded-2xl text-sm focus:ring-2 focus:ring-blue-600 transition-all"
                              />
                            </div>

                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                              {INTEGRATION_PROVIDERS.filter(p => p.name.toLowerCase().includes(searchQuery.toLowerCase())).map((provider) => (
                                <button
                                  key={provider.id}
                                  onClick={() => provider.enabled && setSelectedProviderForWizard(provider.id)}
                                  className={`p-6 rounded-2xl border-2 transition-all text-center flex flex-col items-center gap-4 group ${
                                    selectedProviderForWizard === provider.id 
                                      ? 'border-blue-600 bg-blue-50 shadow-md' 
                                      : !provider.enabled 
                                        ? 'border-[#E5E5E5] opacity-40 cursor-not-allowed'
                                        : 'border-[#E5E5E5] hover:border-blue-400 hover:bg-white'
                                  }`}
                                >
                                  <div className={`w-12 h-12 rounded-2xl flex items-center justify-center transition-transform group-hover:scale-110 ${provider.bg} ${provider.color}`}>
                                    <provider.icon className="w-6 h-6" />
                                  </div>
                                  <div>
                                    <div className="font-bold text-sm">{provider.name}</div>
                                    <div className="text-[10px] text-[#737373] mt-1">{!provider.enabled ? 'Coming Soon' : provider.tagline}</div>
                                  </div>
                                  <div className={`w-6 h-6 rounded-full border-2 flex items-center justify-center transition-all ${
                                    selectedProviderForWizard === provider.id ? 'bg-blue-600 border-blue-600' : 'border-[#E5E5E5]'
                                  }`}>
                                    {selectedProviderForWizard === provider.id && <Check className="w-3 h-3 text-white" />}
                                  </div>
                                </button>
                              ))}
                            </div>
                          </motion.div>
                        )}

                        {wizardStep === 2 && selectedProviderForWizard && (
                          <motion.div 
                            key="step2"
                            initial={{ x: 20, opacity: 0 }}
                            animate={{ x: 0, opacity: 1 }}
                            exit={{ x: -20, opacity: 0 }}
                            className="flex flex-col md:flex-row items-center gap-12"
                          >
                            <div className="flex-1 space-y-8">
                              <div>
                                <h2 className="text-3xl font-black mb-4">What you'll get with {INTEGRATION_PROVIDERS.find(p => p.id === selectedProviderForWizard)?.name}</h2>
                                <p className="text-[#737373]">Streamline your workflow and keep your team in sync with real-time data updates.</p>
                              </div>

                              <div className="space-y-4">
                                {[
                                  { icon: Zap, text: "Auto-notify team on new features" },
                                  { icon: MessageSquare, text: "Sync comments to channels" },
                                  { icon: Database, text: "Centralize project documentation" },
                                  { icon: CheckCircle2, text: "Automate status updates" }
                                ].map((benefit, i) => (
                                  <div key={i} className="flex items-center gap-4 p-4 bg-[#FBFBFA] rounded-2xl border border-[#E5E5E5]">
                                    <div className="w-10 h-10 rounded-xl bg-white border border-[#E5E5E5] flex items-center justify-center text-blue-600">
                                      <benefit.icon className="w-5 h-5" />
                                    </div>
                                    <span className="font-bold text-sm">{benefit.text}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                            <div className="flex-1 bg-blue-50 rounded-3xl p-8 aspect-square flex items-center justify-center relative overflow-hidden">
                              <div className="absolute inset-0 bg-gradient-to-br from-blue-100/50 to-transparent" />
                              <motion.div 
                                animate={{ y: [0, -10, 0] }}
                                transition={{ repeat: Infinity, duration: 3 }}
                                className="w-48 h-48 bg-white rounded-3xl shadow-2xl flex items-center justify-center relative z-10"
                              >
                                {(() => {
                                  const ProviderIcon = INTEGRATION_PROVIDERS.find(p => p.id === selectedProviderForWizard)?.icon || Database;
                                  return <ProviderIcon className="w-24 h-24 text-blue-600" />;
                                })()}
                              </motion.div>
                              <div className="absolute bottom-8 left-8 right-8 h-4 bg-white/50 rounded-full overflow-hidden">
                                <motion.div 
                                  animate={{ x: ['-100%', '100%'] }}
                                  transition={{ repeat: Infinity, duration: 2 }}
                                  className="w-1/2 h-full bg-blue-600"
                                />
                              </div>
                            </div>
                          </motion.div>
                        )}

                        {wizardStep === 3 && selectedProviderForWizard && (
                          <motion.div 
                            key="step3"
                            initial={{ x: 20, opacity: 0 }}
                            animate={{ x: 0, opacity: 1 }}
                            exit={{ x: -20, opacity: 0 }}
                            className="space-y-8"
                          >
                            <div className="flex flex-col md:flex-row gap-12">
                              <div className="flex-1 space-y-6">
                                <div>
                                  <h2 className="text-3xl font-black mb-4">{OAUTH_SETUP_INSTRUCTIONS[selectedProviderForWizard]?.title}</h2>
                                  <p className="text-[#737373]">Follow these steps to create an OAuth application in your {INTEGRATION_PROVIDERS.find(p => p.id === selectedProviderForWizard)?.name} account.</p>
                                </div>

                                <div className="space-y-4">
                                  {OAUTH_SETUP_INSTRUCTIONS[selectedProviderForWizard]?.steps.map((step, i) => (
                                    <div key={i} className="flex gap-4">
                                      <div className="w-6 h-6 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-xs font-bold shrink-0">
                                        {i + 1}
                                      </div>
                                      <p className="text-sm text-[#1A1A1A] leading-relaxed">{step}</p>
                                    </div>
                                  ))}
                                </div>

                                <div className="flex items-center gap-4 pt-4">
                                  <a 
                                    href={OAUTH_SETUP_INSTRUCTIONS[selectedProviderForWizard]?.dashboardUrl} 
                                    target="_blank" 
                                    rel="noopener noreferrer"
                                    className="px-4 py-2 bg-[#1A1A1A] text-white rounded-xl text-xs font-bold hover:bg-black transition-all flex items-center gap-2"
                                  >
                                    <ExternalLink className="w-3 h-3" />
                                    Open Developer Dashboard
                                  </a>
                                  <a 
                                    href={OAUTH_SETUP_INSTRUCTIONS[selectedProviderForWizard]?.docsUrl} 
                                    target="_blank" 
                                    rel="noopener noreferrer"
                                    className="text-xs font-bold text-blue-600 hover:underline"
                                  >
                                    View Documentation
                                  </a>
                                </div>
                              </div>

                              <div className="w-full md:w-80 space-y-6">
                                <div className="p-6 bg-[#FBFBFA] rounded-3xl border border-[#E5E5E5] space-y-4">
                                  <h3 className="text-xs font-black uppercase tracking-widest text-[#737373]">App Configuration</h3>
                                  
                                  <div className="space-y-2">
                                    <label className="text-[10px] font-bold text-[#737373] uppercase">Callback URL</label>
                                    <div className="flex items-center gap-2 p-2 bg-white border border-[#E5E5E5] rounded-lg">
                                      <input 
                                        readOnly 
                                        value={`${window.location.origin}/auth/callback`}
                                        className="flex-1 text-[10px] font-mono bg-transparent border-none focus:ring-0"
                                      />
                                      <button 
                                        onClick={() => navigator.clipboard.writeText(`${window.location.origin}/auth/callback`)}
                                        className="p-1 hover:bg-gray-100 rounded transition-colors"
                                      >
                                        <Database className="w-3 h-3 text-[#737373]" />
                                      </button>
                                    </div>
                                  </div>

                                  <div className="space-y-2">
                                    <label className="text-[10px] font-bold text-[#737373] uppercase">Required Scopes</label>
                                    <div className="flex flex-wrap gap-1">
                                      {OAUTH_SETUP_INSTRUCTIONS[selectedProviderForWizard]?.scopes.map(scope => (
                                        <span key={scope} className="px-2 py-1 bg-blue-50 text-blue-600 rounded text-[9px] font-bold font-mono">
                                          {scope}
                                        </span>
                                      ))}
                                    </div>
                                  </div>
                                </div>

                                <div className="space-y-4">
                                  <div className="space-y-2">
                                    <label className="text-xs font-bold">Client ID</label>
                                    <input 
                                      type="text" 
                                      placeholder="Paste Client ID here..."
                                      className="w-full px-4 py-3 bg-white border border-[#E5E5E5] rounded-xl text-sm focus:ring-2 focus:ring-blue-600 outline-none"
                                    />
                                  </div>
                                  <div className="space-y-2">
                                    <label className="text-xs font-bold">Client Secret</label>
                                    <input 
                                      type="password" 
                                      placeholder="Paste Client Secret here..."
                                      className="w-full px-4 py-3 bg-white border border-[#E5E5E5] rounded-xl text-sm focus:ring-2 focus:ring-blue-600 outline-none"
                                    />
                                  </div>
                                </div>
                              </div>
                            </div>
                          </motion.div>
                        )}

                        {wizardStep === 4 && selectedProviderForWizard && (
                          <motion.div 
                            key="step4"
                            initial={{ x: 20, opacity: 0 }}
                            animate={{ x: 0, opacity: 1 }}
                            exit={{ x: -20, opacity: 0 }}
                            className="text-center max-w-xl mx-auto space-y-12"
                          >
                            <div>
                              <h2 className="text-3xl font-black mb-4">Authenticate {INTEGRATION_PROVIDERS.find(p => p.id === selectedProviderForWizard)?.name}</h2>
                              <p className="text-[#737373]">Connect your account to allow Product OS to sync data.</p>
                            </div>

                            <div className="p-12 bg-[#FBFBFA] rounded-3xl border-2 border-dashed border-[#E5E5E5] space-y-8">
                              <div className="flex justify-center">
                                {(() => {
                                  const provider = INTEGRATION_PROVIDERS.find(p => p.id === selectedProviderForWizard);
                                  return (
                                    <div className={`w-20 h-20 rounded-3xl flex items-center justify-center shadow-xl ${provider?.bg} ${provider?.color}`}>
                                      {provider && <provider.icon className="w-10 h-10" />}
                                    </div>
                                  );
                                })()}
                              </div>

                              <div className="space-y-4">
                                {selectedProviderForWizard === 'monday' && (
                                  <>
                                    <div className="flex flex-col gap-2 text-left">
                                      <label className="text-[10px] font-bold text-[#737373] uppercase">Monday.com API token (required)</label>
                                      <div className="flex gap-2">
                                        <input
                                          type="password"
                                          placeholder="Paste your API token from Monday.com..."
                                          value={mondayApiKey}
                                          onChange={(e) => { setMondayApiKey(e.target.value); setMondayTestStatus('idle'); setMondayConnectError(null); }}
                                          className="flex-1 px-4 py-3 bg-white border border-[#E5E5E5] rounded-xl text-sm focus:ring-2 focus:ring-blue-600 outline-none"
                                        />
                                        <button
                                          type="button"
                                          onClick={async () => {
                                            const key = mondayApiKey.trim();
                                            if (!key) return;
                                            setMondayTestStatus('testing');
                                            setMondayConnectError(null);
                                            try {
                                              const res = await fetch(`${RESEARCH_API_URL}/integrations/monday/test`, {
                                                method: 'POST',
                                                headers: { 'Content-Type': 'application/json' },
                                                body: JSON.stringify({ api_key: key })
                                              });
                                              const data = await res.json().catch(() => ({}));
                                              if (res.ok && data.ok) setMondayTestStatus('ok');
                                              else setMondayTestStatus('error');
                                            } catch (e) {
                                              setMondayTestStatus('error');
                                              setMondayConnectError(
                                                (e as Error)?.message?.includes('Failed to fetch') || (e as Error)?.message?.includes('Connection refused')
                                                  ? 'Cannot reach the Research Agent API. Start it with: python -m research_agent serve'
                                                  : null
                                              );
                                            }
                                          }}
                                          disabled={!mondayApiKey.trim() || mondayTestStatus === 'testing'}
                                          className="px-4 py-3 bg-[#F5F5F4] text-[#1A1A1A] rounded-xl text-xs font-bold hover:bg-[#E5E5E5] transition-all flex items-center gap-2 shrink-0"
                                        >
                                          {mondayTestStatus === 'testing' ? <Loader2 className="w-3 h-3 animate-spin" /> : mondayTestStatus === 'ok' ? <CheckCircle2 className="w-3 h-3 text-emerald-600" /> : null}
                                          Test
                                        </button>
                                      </div>
                                      {mondayTestStatus === 'ok' && <p className="text-xs text-emerald-600 font-medium">Connection successful.</p>}
                                      {mondayTestStatus === 'error' && !mondayConnectError && <p className="text-xs text-red-600 font-medium">Connection failed. Check token and permissions.</p>}
                                      <a href="https://support.monday.com/hc/en-us/articles/360005562273-How-do-I-get-my-API-token-" target="_blank" rel="noopener noreferrer" className="text-[10px] font-bold text-blue-600 hover:underline">
                                        Get your API token in Monday.com →
                                      </a>
                                    </div>
                                    {mondayConnectError && <p className="text-sm text-red-600 font-medium">{mondayConnectError}</p>}
                                    <button
                                      onClick={async () => {
                                        const key = mondayApiKey.trim();
                                        if (!key) {
                                          setMondayConnectError('Enter your Monday.com API token above.');
                                          return;
                                        }
                                        setIsConnecting(true);
                                        setMondayConnectError(null);
                                        try {
                                          const testRes = await fetch(`${RESEARCH_API_URL}/integrations/monday/test`, {
                                            method: 'POST',
                                            headers: { 'Content-Type': 'application/json' },
                                            body: JSON.stringify({ api_key: key })
                                          });
                                          if (!testRes.ok) {
                                            const err = await testRes.json().catch(() => ({}));
                                            throw new Error(err.detail || 'Connection test failed.');
                                          }
                                          const putRes = await fetch(`${RESEARCH_API_URL}/integrations/monday`, {
                                            method: 'PUT',
                                            headers: { 'Content-Type': 'application/json' },
                                            body: JSON.stringify({ enabled: true, api_key: key, board_ids: [] })
                                          });
                                          if (!putRes.ok) {
                                            const err = await putRes.json().catch(() => ({}));
                                            throw new Error(err.detail || 'Failed to save integration.');
                                          }
                                          confetti({ particleCount: 150, spread: 70, origin: { y: 0.6 }, colors: ['#2563eb', '#10b981', '#f59e0b'] });
                                          setConfig(prev => prev ? { ...prev, integrations: { ...prev.integrations, monday: true } } : null);
                                          setContextItems([]);
                                          setSelectedServiceForMapping('monday');
                                          setIsWizardOpen(false);
                                          setMondayApiKey('');
                                          setMondayTestStatus('idle');
                                          setTimeout(() => mappingsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
                                        } catch (e) {
                                          setMondayConnectError(e instanceof Error ? e.message : 'Connection failed.');
                                        } finally {
                                          setIsConnecting(false);
                                        }
                                      }}
                                      disabled={isConnecting}
                                      className="w-full py-4 bg-[#1A1A1A] text-white rounded-2xl font-bold text-lg hover:bg-black transition-all flex items-center justify-center gap-3 shadow-xl"
                                    >
                                      {isConnecting ? <><Loader2 className="w-6 h-6 animate-spin" /> Connecting...</> : <>Connect with Monday.com</>}
                                    </button>
                                  </>
                                )}
                                {selectedProviderForWizard !== 'monday' && (
                                  <button
                                    onClick={() => {
                                      setIsConnecting(true);
                                      setTimeout(() => {
                                        setIsConnecting(false);
                                        confetti({ particleCount: 150, spread: 70, origin: { y: 0.6 }, colors: ['#2563eb', '#10b981', '#f59e0b'] });
                                        if (config) {
                                          const newConfig = { ...config };
                                          newConfig.integrations[selectedProviderForWizard!] = true;
                                          setConfig(newConfig);
                                          setSelectedServiceForMapping(selectedProviderForWizard!);
                                          setIsWizardOpen(false);
                                          setTimeout(() => mappingsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
                                        }
                                      }, 2000);
                                    }}
                                    disabled={isConnecting}
                                    className="w-full py-4 bg-[#1A1A1A] text-white rounded-2xl font-bold text-lg hover:bg-black transition-all flex items-center justify-center gap-3 shadow-xl"
                                  >
                                    {isConnecting ? <><Loader2 className="w-6 h-6 animate-spin" /> Connecting...</> : <>Connect with {INTEGRATION_PROVIDERS.find(p => p.id === selectedProviderForWizard)?.name}</>}
                                  </button>
                                )}
                              </div>
                            </div>

                            <p className="text-[10px] text-[#737373] leading-relaxed">
                              By connecting, you agree to our Terms of Service and Privacy Policy. 
                              Product OS will only access the data required for synchronization.
                            </p>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>

                    {/* Wizard Footer */}
                    <div className="px-8 py-6 border-t border-[#E5E5E5] flex items-center justify-between bg-[#FBFBFA]">
                      <button 
                        onClick={() => setWizardStep(prev => Math.max(1, prev - 1))}
                        disabled={wizardStep === 1}
                        className="flex items-center gap-2 text-sm font-bold text-[#737373] hover:text-[#1A1A1A] disabled:opacity-30 transition-all"
                      >
                        <ArrowLeft className="w-4 h-4" />
                        Back
                      </button>
                      <div className="flex items-center gap-4">
                        <button 
                          onClick={() => setIsWizardOpen(false)}
                          className="text-sm font-bold text-[#737373] hover:text-[#1A1A1A] transition-all"
                        >
                          Skip for now
                        </button>
                        {wizardStep < 4 ? (
                          <button 
                            onClick={() => setWizardStep(prev => prev + 1)}
                            disabled={!selectedProviderForWizard}
                            className="px-8 py-3 bg-blue-600 text-white rounded-xl font-bold text-sm hover:bg-blue-700 transition-all disabled:opacity-50 shadow-lg shadow-blue-100"
                          >
                            Continue
                          </button>
                        ) : null}
                      </div>
                    </div>
                  </motion.div>
                </div>
              )}
            </AnimatePresence>
          </div>
        )}
      </main>
    </div>
  );
}
