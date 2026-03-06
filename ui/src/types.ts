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

export type MondayDirection = 'two_way' | 'monday_to_os';
export type JiraDirection = 'two_way' | 'jira_to_os';

export interface JiraEntityMappingConfig {
  entity_type: string;
  project_key: string;
  issue_type_names: string[];
  board_id?: number | null;
  sprint_id?: number | null;
  backlog_only?: boolean;
  direction: JiraDirection;
  field_mappings: Record<string, string>;
}

export interface JiraFieldInfo {
  id: string;
  name: string;
  custom?: boolean;
  schema_type?: string | null;
}

export interface JiraIssueTypeInfo {
  id?: string | null;
  name: string;
}

export interface JiraProjectInfo {
  id: string;
  key: string;
  name: string;
}

export interface JiraBoardInfo {
  id: number;
  name: string;
  type?: string | null;
}

export interface JiraSchemaResponse {
  projects: JiraProjectInfo[];
  boards: JiraBoardInfo[];
  issue_types: JiraIssueTypeInfo[];
  fields: JiraFieldInfo[];
}

export interface JiraIntegrationConfigResponse {
  source: 'jira';
  enabled: boolean;
  access_token_set: boolean;
  cloud_id: string | null;
  site_url: string | null;
  client_id: string | null;
  client_secret_set: boolean;
  entity_configs: Record<string, JiraEntityMappingConfig>;
  sync_interval_seconds: number;
  updated_at: string | null;
}

export interface MondayEntityMappingConfig {
  entity_type: string;
  board_ids: string[];
  direction: MondayDirection;
  field_mappings: Record<string, string>;
}

export interface MondayBoardColumn {
  id: string;
  title: string;
  type?: string;
}

export interface MondayBoardSchema {
  id: string;
  name: string;
  columns: MondayBoardColumn[];
}

export interface MondayIntegrationConfigResponse {
  source: 'monday';
  enabled: boolean;
  api_key_set: boolean;
  board_ids: string[];
  entity_mappings: Record<string, string>;
  entity_configs: Record<string, MondayEntityMappingConfig>;
  sync_interval_seconds: number;
  /** Tenant subdomain for item URLs, e.g. "my-team" → https://my-team.monday.com */
  subdomain: string | null;
  updated_at: string | null;
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
    typed_id?: string;
    index?: number;
    entity_type?: string;
    entity_id?: string;
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
