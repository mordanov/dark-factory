export type UserRole = "administrator" | "user";

export type TicketStatus = "OPEN" | "IN_PROGRESS" | "IN_REVIEW" | "DONE" | "CLOSED";

export type TicketType =
  | "bug" | "feature" | "improvement" | "investigation"
  | "discovery" | "reporting" | "testing" | "analysis" | "other";

export type TicketSpec =
  | "backend" | "frontend" | "architecture" | "testing"
  | "business_analysis" | "product_management" | "other";

export interface UserSummary {
  id: string;
  email: string;
  role: UserRole;
}

export interface ProjectTicketCounts {
  open: number;
  active: number;
  done: number;
}

export interface ProjectGroup {
  id: string;
  identifier: string;
  name: string;
  description: string | null;
  is_system: boolean;
  created_at: string;
  project_count: number;
}

export interface ProjectSummary {
  id: string;
  name: string;
  slug: string;
  code: string | null;
  group_id: string;
  group: ProjectGroup;
  created_at: string;
  ticket_counts: ProjectTicketCounts;
}

export interface AssigneeSummary {
  user_id: string;
  email: string;
  has_progress_update: boolean;
}

export interface TagResponse {
  id: string;
  name: string;
}

export interface TicketResponse {
  id: string;
  display_id: string | null;
  number: number | null;
  project_id: string;
  parent_ticket_id: string | null;
  title: string;
  description: string | null;
  status: TicketStatus;
  ticket_type: TicketType;
  ticket_spec: TicketSpec | null;
  urgent: boolean;
  blocker: boolean;
  bugfix: boolean;
  created_by: UserSummary;
  created_at: string;
  updated_at: string;
  assignees: AssigneeSummary[];
  follow_up_count?: number;
  tags: TagResponse[];
  tokens_spent: number;
}

export interface TicketListResponse {
  items: TicketResponse[];
  total: number;
}

export interface TicketCreate {
  title: string;
  description?: string | null;
  ticket_type: TicketType;
  ticket_spec: TicketSpec;
  urgent: boolean;
  blocker: boolean;
  bugfix: boolean;
  tags: string[];
}

export interface TicketUpdate {
  title?: string;
  description?: string | null;
  ticket_type?: TicketType;
  ticket_spec?: TicketSpec;
  urgent?: boolean;
  blocker?: boolean;
  bugfix?: boolean;
}

export interface AssignmentResponse {
  ticket_id: string;
  user_id: string;
  assigned_at: string;
}

export interface ProgressUpdateResponse {
  ticket_id: string;
  user_id: string;
  content: string;
  created_at: string;
  updated_at: string;
}

export interface ProgressListResponse {
  items: ProgressUpdateResponse[];
}

export interface TransitionBlockedError {
  detail: string;
  missing_updates: { user_id: string; email: string }[];
}

export interface TicketEventResponse {
  id: string;
  ticket_id: string;
  event_type: string;
  actor: UserSummary;
  prev_state: Record<string, unknown> | null;
  new_state: Record<string, unknown> | null;
  metadata: Record<string, unknown> | null;
  occurred_at: string;
}

export interface EventListResponse {
  items: TicketEventResponse[];
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  refresh_token?: string;
}

export interface AdminUserResponse {
  id: string;
  email: string;
  role: UserRole;
  created_at: string;
  blocked_at: string | null;
}

export interface AdminUserCreate {
  email: string;
  password: string;
  role: UserRole;
}

export interface AdminUserUpdate {
  email?: string;
  role?: UserRole;
}

export interface AdminUserListResponse {
  items: AdminUserResponse[];
  total: number;
}

export const WORKFLOW_TRANSITIONS: Record<TicketStatus, TicketStatus[]> = {
  OPEN: ["IN_PROGRESS"],
  IN_PROGRESS: ["IN_REVIEW"],
  IN_REVIEW: ["DONE", "IN_PROGRESS"],
  DONE: ["CLOSED", "IN_PROGRESS"],
  CLOSED: [],
};

export const TICKET_STATUS_LABELS: Record<TicketStatus, string> = {
  OPEN: "Open",
  IN_PROGRESS: "In Progress",
  IN_REVIEW: "In Review",
  DONE: "Done",
  CLOSED: "Closed",
};

export const TICKET_TYPE_LABELS: Record<TicketType, string> = {
  bug: "Bug",
  feature: "Feature",
  improvement: "Improvement",
  investigation: "Investigation",
  discovery: "Discovery",
  reporting: "Reporting",
  testing: "Testing",
  analysis: "Analysis",
  other: "Other",
};

export const TICKET_SPEC_LABELS: Record<TicketSpec, string> = {
  backend: "Backend",
  frontend: "Frontend",
  architecture: "Architecture",
  testing: "Testing",
  business_analysis: "Business Analysis",
  product_management: "Product Management",
  other: "Other",
};
