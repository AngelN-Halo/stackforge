import type { AIResponse, Checkpoint, Project, Role, User } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json() as Promise<T>;
}

export const api = {
  async login(email: string, password: string) {
    return request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },
  logout() {
    return request<{ status: string }>("/auth/logout", { method: "POST" });
  },
  me() {
    return request<User>("/auth/me");
  },
  settings() {
    return request<Record<string, unknown>>("/settings");
  },
  changePassword(currentPassword: string, newPassword: string) {
    return request<{ status: string }>("/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
  },
  listUsers() {
    return request<User[]>("/users");
  },
  createUser(email: string, password: string, role: Role) {
    return request<User>("/users", {
      method: "POST",
      body: JSON.stringify({ email, password, role }),
    });
  },
  updateUser(id: string, changes: { role?: Role; is_active?: boolean }) {
    return request<User>(`/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    });
  },
  listProjects() {
    return request<Project[]>("/projects");
  },
  createProject(name: string, description: string, template: string) {
    return request<Project>("/projects", {
      method: "POST",
      body: JSON.stringify({ name, description, template }),
    });
  },
  getProject(id: string) {
    return request<Project>(`/projects/${id}`);
  },
  deleteProject(id: string) {
    return request<{ status: string }>(`/projects/${id}`, { method: "DELETE" });
  },
  getTree(id: string) {
    return request<Record<string, unknown>>(`/projects/${id}/files/tree`);
  },
  readFile(id: string, path: string) {
    return request<{ path: string; content: string }>(`/projects/${id}/files?path=${encodeURIComponent(path)}`);
  },
  saveFile(id: string, path: string, content: string) {
    return request<{ status: string }>(`/projects/${id}/files`, {
      method: "POST",
      body: JSON.stringify({ path, content }),
    });
  },
  renameFile(id: string, oldPath: string, newPath: string) {
    return request<{ status: string }>(`/projects/${id}/files/rename`, {
      method: "POST",
      body: JSON.stringify({ old_path: oldPath, new_path: newPath }),
    });
  },
  deleteFile(id: string, path: string) {
    return request<{ status: string }>(`/projects/${id}/files/delete`, {
      method: "POST",
      body: JSON.stringify({ path }),
    });
  },
  generate(id: string, message: string, fileContext: string[]) {
    return request<AIResponse>(`/projects/${id}/generate`, {
      method: "POST",
      body: JSON.stringify({ message, file_context: fileContext }),
    });
  },
  checkpoints(id: string) {
    return request<Checkpoint[]>(`/projects/${id}/checkpoints`);
  },
  restoreCheckpoint(projectId: string, checkpointId: string) {
    return request<{ status: string }>(`/projects/${projectId}/checkpoints/${checkpointId}/restore`, {
      method: "POST",
    });
  },
  buildPreview(id: string, port = 3001) {
    return request(`/projects/${id}/preview/build`, {
      method: "POST",
      body: JSON.stringify({ port }),
    });
  },
  restartPreview(id: string, port = 3001) {
    return request(`/projects/${id}/preview/restart`, {
      method: "POST",
      body: JSON.stringify({ port }),
    });
  },
  stopPreview(id: string) {
    return request<{ status: string }>(`/projects/${id}/preview/stop`, { method: "POST" });
  },
  previewStatus(id: string) {
    return request<Record<string, unknown>>(`/projects/${id}/preview/status`);
  },
  previewLogs(id: string) {
    return request<{ logs: string }>(`/projects/${id}/preview/logs`);
  },
};
