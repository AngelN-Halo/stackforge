"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Link from "next/link";
import type { Project, User } from "@/lib/types";

export default function HomePage() {
  const [user, setUser] = useState<User | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("New StackForge app");
  const [description, setDescription] = useState("Build a modern internal tool");
  const [template, setTemplate] = useState("nextjs-app");

  useEffect(() => {
    void api.me().then(setUser).catch(() => setUser(null));
    void api.listProjects().then(setProjects).catch(() => setProjects([]));
  }, []);

  async function createProject() {
    const project = await api.createProject(name, description, template);
    window.location.href = `/project/${project.id}`;
  }

  if (!user) {
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <h1>StackForge</h1>
          <p>Sign in to build and preview internal apps.</p>
          <Link href="/login">Go to login</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="page-shell" style={{ alignItems: "start" }}>
      <div className="auth-card" style={{ width: "min(760px, 100%)" }}>
        <h1>StackForge Dashboard</h1>
        <p>Logged in as {user.email}</p>
        <div style={{ display: "grid", gap: 12 }}>
          <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Project name" />
          <input value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Description" />
          <select value={template} onChange={(event) => setTemplate(event.target.value)}>
            <option value="nextjs-app">Next.js app</option>
            <option value="react-vite">React/Vite app</option>
            <option value="static-html">Static HTML/CSS/JS app</option>
            <option value="fastapi-app">FastAPI app</option>
            <option value="node-express">Node/Express app</option>
            <option value="fullstack-nextjs">Full-stack Next.js + Postgres app</option>
          </select>
          <button onClick={createProject}>Create Project</button>
        </div>
        <div style={{ marginTop: 24 }}>
          <h2>Projects</h2>
          <div style={{ display: "grid", gap: 12 }}>
            {projects.map((project) => (
              <Link key={project.id} href={`/project/${project.id}`} style={{ display: "block", border: "1px solid var(--border)", borderRadius: 12, padding: 12 }}>
                <strong>{project.name}</strong>
                <div>{project.description}</div>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
