export interface Advisor {
  id: string;
  name: string;
  title: string;
  category: string;
  era: string;
  avatar: string;
  shortBio: string;
  style: string;
  kb_status?: string;
  kb_doc_count?: number;
  is_published?: boolean;
  visibility?: string;
  creator_id?: string;
}

export interface Council {
  id: string;
  advisors: Advisor[];
  title: string;
  created_at: string;
}

export interface Message {
  id: string;
  role: "user" | "advisor" | "system";
  advisorId?: string;
  advisorName?: string;
  content: string;
  timestamp: number;
  isStreaming?: boolean;
  sequence?: number;
  metadata?: Record<string, any>;
}

export interface BudgetInfo {
  session_id: string;
  max_budget: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  total_cost_cny: number;
  remaining_budget: number;
  budget_percent: number;
  over_budget: boolean;
}

export interface SessionDetail {
  id: string;
  title: string;
  advisor_ids: string[];
  message_count: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  messages?: Array<{
    id: string;
    sequence: number;
    role: string;
    advisor_id?: string;
    advisor_name: string;
    content: string;
    created_at: string;
    metadata?: Record<string, any>;
  }>;
}
