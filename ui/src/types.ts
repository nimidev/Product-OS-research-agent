export type EntityType = 'Feature' | 'Epic' | 'UserStory' | 'Requirement' | 'Decision' | 'Bug' | 'SupportTicket' | 'FeatureRequest' | 'ActionItem';

export interface Feature {
  id: string;
  title: string;
  status: string;
  priority: string;
  owner: string;
  description: string;
  tags?: string[];
}

export interface Epic {
  id: string;
  title: string;
  status: string;
  features: string[]; // IDs
}

export interface UserStory {
  id: string;
  title: string;
  status: string;
  acceptanceCriteria: string[];
  featureId: string;
}

export interface Requirement {
  id: string;
  title: string;
  description: string;
  sourceDocId: string;
}

export interface Decision {
  id: string;
  title: string;
  rationale: string;
  date: string;
  meetingId: string;
}

export interface Bug {
  id: string;
  title: string;
  severity: string;
  status: string;
  owner: string;
}

export interface SupportTicket {
  id: string;
  subject: string;
  customer: string;
  status: string;
}

export interface FeatureRequest {
  id: string;
  title: string;
  votes: number;
  status: string;
}

export interface ActionItem {
  id: string;
  description: string;
  assignee: string;
  dueDate: string;
  status: string;
}

export interface ContextItem {
  id: string;
  source_type: string;
  source_id: string;
  title: string;
  url: string;
  type?: EntityType;
  [key: string]: any;
}

export interface AppConfig {
  integrations: Record<string, boolean>;
  mappings: Record<string, Record<string, string>>;
}

export interface AgentResponse {
  mode: 'admin' | 'pm';
  answer: string;
  entities: any[];
  references: {
    source_type: string;
    source_id: string;
    title: string;
    url: string;
  }[];
  config?: AppConfig;
  suggestions?: string[];
}

export interface ChatSession {
  id: string;
  title: string;
  messages: { role: 'user' | 'assistant', content: string | AgentResponse }[];
  timestamp: number;
}
