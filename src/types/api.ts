export type EmailDirection = 'inbound' | 'outbound';
export type EmailSource = 'manual' | 'eml' | 'csv' | 'json';
export type ProcessingStatus = 'pending' | 'processing' | 'completed' | 'failed';
export type EmailCategory = 'invoice' | 'order' | 'support' | 'spam' | 'newsletter' | 'marketing' | 'meeting' | 'hr' | 'finance' | 'legal' | 'other';
export type EmailPriority = 'low' | 'normal' | 'high' | 'critical';
export type EmailSentiment = 'positive' | 'neutral' | 'negative' | 'urgent';
export type UserRole = 'user' | 'admin';
export type ReplyTone = 'professional' | 'friendly' | 'concise' | 'empathetic' | 'firm';
export type ReplyStatus = 'draft' | 'approved' | 'rejected';
export type ActionStatus = 'pending' | 'completed' | 'dismissed';

export interface UserOut {
  id: number;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  is_verified: boolean;
  timezone: string;
  created_at: string;
  last_login_at: string | null;
  email_verified_at: string | null;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: UserOut;
}

export interface SignupRequest {
  email: string;
  password: string;
  full_name?: string;
  timezone?: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RefreshRequest {
  refresh_token: string;
}

export interface ProfileUpdateRequest {
  full_name?: string;
  timezone?: string;
}

export interface AuthMessage {
  message: string;
  dev_link?: string;
  dev_token?: string;
  details?: Array<{ field: string; message: string }>;
}

export interface EmailCreate {
  subject?: string;
  from_name?: string;
  from_address: string;
  to?: string[];
  cc?: string[];
  reply_to?: string;
  body_text: string;
  body_html?: string;
  received_at?: string;
  direction?: EmailDirection;
  message_id?: string;
  has_attachments?: boolean;
  attachment_names?: string[];
  process_with_ai?: boolean;
}

export interface EmailAnalysisOut {
  id: number;
  category: EmailCategory;
  category_confidence: number | null;
  intent: string;
  priority: EmailPriority;
  priority_reason: string;
  sentiment: EmailSentiment;
  sentiment_confidence: number | null;
  reply_required: boolean;
  action_required: boolean;
  summary_short: string;
  summary_detailed: string;
  key_points: string[];
  unresolved_issues: string[];
  provider: string;
  model: string;
  prompt_version: string;
  schema_version: string;
  latency_ms: number | null;
  analyzed_at: string;
}

export interface ExtractedEntityOut {
  id: number;
  field: string;
  value_text: string;
  value_normalized: string | null;
  raw_phrase: string | null;
  confidence: number | null;
  evidence: string | null;
}

export interface EmailListItem {
  id: number;
  thread_id: number | null;
  subject: string;
  preview: string;
  from_name: string;
  from_address: string;
  to: string[];
  received_at: string;
  direction: EmailDirection;
  is_read: boolean;
  is_starred: boolean;
  is_archived: boolean;
  is_deleted: boolean;
  has_attachments: boolean;
  source: EmailSource;
  processing_status: ProcessingStatus;
  category: string | null;
  priority: string | null;
  sentiment: string | null;
  reply_required: boolean | null;
  action_required: boolean | null;
  is_urgent: boolean;
}

export interface EmailDetail extends EmailListItem {
  body_text: string;
  body_html: string | null;
  cc: string[];
  reply_to: string | null;
  message_id: string | null;
  in_reply_to: string | null;
  attachment_names: string[];
  size_bytes: number;
  created_at: string;
  processed_at: string | null;
  processing_error: string | null;
  analysis: EmailAnalysisOut | null;
  extracted: ExtractedEntityOut[];
}

export interface ThreadMessage {
  id: number;
  subject: string;
  from_name: string;
  from_address: string;
  to: string[];
  received_at: string;
  direction: EmailDirection;
  body_text: string;
  is_read: boolean;
  processing_status: ProcessingStatus;
  category: string | null;
  summary_short: string | null;
}

export interface ThreadListItem {
  id: number;
  thread_key: string;
  subject: string;
  message_count: number;
  participant_count: number;
  last_message_at: string;
  has_unread: boolean;
  is_starred: boolean;
  preview: string;
}

export interface ThreadDetail {
  id: number;
  thread_key: string;
  subject: string;
  last_message_at: string;
  message_count: number;
  messages: ThreadMessage[];
}

export interface StateUpdateRequest {
  is_read?: boolean;
  is_starred?: boolean;
  is_archived?: boolean;
}

export interface EmailUpdateRequest {
  subject?: string;
  from_name?: string;
  body_text?: string;
}

export interface ImportRowError {
  row: number;
  field: string | null;
  message: string;
}

export interface ImportSummary {
  source: EmailSource;
  filename: string | null;
  received: number;
  created: number;
  duplicates: number;
  failed: number;
  errors: ImportRowError[];
  email_ids: number[];
}

export interface EmailFilterParams {
  q?: string;
  from_address?: string;
  subject?: string;
  category?: string[];
  priority?: string[];
  sentiment?: string[];
  date_from?: string;
  date_to?: string;
  unread?: boolean;
  starred?: boolean;
  archived?: boolean;
  deleted?: boolean;
  urgent?: boolean;
  reply_required?: boolean;
  action_required?: boolean;
  direction?: EmailDirection;
  processing_status?: ProcessingStatus;
  customer?: string;
  order_number?: string;
  has_attachments?: boolean;
  thread_id?: number;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
  page?: number;
  page_size?: number;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface OkResponse {
  message: string;
}

export interface SuggestedReplyOut {
  id: number;
  email_id: number;
  user_id: number;
  tone: ReplyTone;
  body: string;
  original_body: string | null;
  is_edited: boolean;
  status: ReplyStatus;
  created_at: string;
  updated_at: string | null;
  decided_at: string | null;
}

export interface ReplyGenerateRequest {
  tone: ReplyTone;
  instructions?: string;
  regenerate?: boolean;
}

export interface SuggestedReplyUpdate {
  body?: string;
  tone?: ReplyTone;
  status?: ReplyStatus;
}

export interface DashboardCounters {
  total: number;
  unread: number;
  starred: number;
  archived: number;
  urgent: number;
  reply_required: number;
  action_required: number;
}

export interface DashboardSummary {
  counters: DashboardCounters;
  recent_emails: RecentEmail[];
  recent_activity: RecentActivity[];
  deadlines: DeadlineItem[];
}

export interface RecentEmail {
  id: number;
  subject: string;
  from_name: string;
  from_address: string;
  received_at: string;
  is_read: boolean;
  is_starred: boolean;
  category: string | null;
  priority: string | null;
  is_urgent: boolean;
}

export interface RecentActivity {
  id: number;
  email_id: number;
  action: string;
  status: string;
  created_at: string;
}

export interface DeadlineItem {
  id: number;
  email_id: number;
  subject: string;
  due_at: string;
  is_overdue: boolean;
  entity_type: string;
}

export interface ActivityPoint {
  date: string;
  count: number;
}

export interface CategoryCount {
  category: string;
  count: number;
}

export interface SentimentCount {
  sentiment: string;
  count: number;
}

export interface PriorityCount {
  priority: string;
  count: number;
}

export interface AnalyticsReport {
  date_from: string;
  date_to: string;
  total_emails: number;
  by_category: CategoryCount[];
  by_sentiment: SentimentCount[];
  by_priority: PriorityCount[];
  activity_series: ActivityPoint[];
}

export interface AssistantConversationOut {
  id: number;
  title: string;
  message_count: number;
  last_message_at: string | null;
  created_at: string;
  messages: AssistantMessageOut[];
}

export interface AssistantMessageOut {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  filters: Record<string, unknown> | null;
  citations: number[];
  created_at: string;
}

export interface AssistantQuery {
  query: string;
}

export interface AssistantResult {
  id: number;
  subject: string;
  from_name: string;
  from_address: string;
  received_at: string;
  category: string | null;
  priority: string | null;
  snippet: string;
}

export interface AssistantAnswer {
  conversation_id: number | null;
  message: AssistantMessageOut;
  applied_filters: Record<string, unknown>;
  total_matches: number;
  results: AssistantResult[];
  answer: string;
  deterministic: boolean;
}

export interface NotificationOut {
  id: number;
  user_id: number;
  type: string;
  title: string;
  body: string;
  email_id: number | null;
  action_id: number | null;
  is_read: boolean;
  created_at: string;
  read_at: string | null;
}

export interface PaginatedNotifications {
  items: NotificationOut[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface UserPreferencesOut {
  default_reply_tone: ReplyTone;
  digest_enabled: boolean;
  timezone: string;
  notification_channels: Record<string, unknown>;
}

export interface ErrorResponse {
  error: {
    code: string;
    message: string;
    details?: Array<{ field: string; message: string }>;
    request_id: string;
  };
}