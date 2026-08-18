export type Role = "admin" | "builder" | "viewer";

export type User = {
  id: string;
  email: string;
  role: Role;
  is_active: boolean;
  created_at: string;
};

export type Project = {
  id: string;
  name: string;
  description: string;
  owner_id: string;
  status: string;
  generated_file_tree: Record<string, unknown>;
  current_version: number;
  preview_url: string | null;
  deployment_state: string;
  created_at: string;
  updated_at: string;
};

export type Checkpoint = {
  id: string;
  project_id: string;
  version: number;
  label: string;
  snapshot_path: string;
  created_by_id: string;
  created_at: string;
};

export type AIResponse = {
  assistant_explanation: string;
  files: Array<{ path: string; content?: string; action?: string }>;
  commands: string[];
  notes: string[];
};
