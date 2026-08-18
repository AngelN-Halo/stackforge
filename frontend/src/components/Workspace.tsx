"use client";

import Editor from "@monaco-editor/react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { Checkpoint, Project, User } from "@/lib/types";

type TreeNode = { type?: string; name: string; children?: TreeNode[] };

function flattenTree(node: TreeNode, prefix = ""): string[] {
  if (!prefix && !node.type && node.children?.length) {
    return node.children.flatMap((child) => flattenTree(child, ""));
  }
  const current = prefix ? `${prefix}/${node.name}` : node.name;
  if (node.type === "file" || !node.children?.length) return [current];
  return (node.children ?? []).flatMap((child) => flattenTree(child, current));
}

export function Workspace({ projectId }: { projectId: string }) {
  const [user, setUser] = useState<User | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [tree, setTree] = useState<TreeNode | null>(null);
  const [selectedPath, setSelectedPath] = useState<string>("");
  const [content, setContent] = useState<string>("");
  const [chat, setChat] = useState("");
  const [messages, setMessages] = useState<string[]>([]);
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([]);
  const [logs, setLogs] = useState("");
  const [newFilePath, setNewFilePath] = useState("");
  const [renamePath, setRenamePath] = useState("");
  const [fileFilter, setFileFilter] = useState("");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [actionError, setActionError] = useState<string | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewKey, setPreviewKey] = useState(0);
  const [deletingProject, setDeletingProject] = useState(false);
  const previewPanelRef = useRef<HTMLElement>(null);

  async function refresh() {
    setLoading(true);
    setActionError(null);
    try {
      const [me, p, t, cps, status, previewLogs] = await Promise.all([
        api.me(), api.getProject(projectId), api.getTree(projectId), api.checkpoints(projectId),
        api.previewStatus(projectId).catch(() => null), api.previewLogs(projectId).catch(() => ({ logs: "" })),
      ]);
      setUser(me); setProject(p); setTree(t as TreeNode); setCheckpoints(cps);
      if (previewLogs) setLogs(previewLogs.logs);
      if (!selectedPath) {
        const allFiles = flattenTree(t as TreeNode).filter((file) => file !== "stackforge.json" && !file.startsWith(".stackforge/"));
        if (allFiles.length > 0) await loadFile(allFiles[0]);
      }
      return status;
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not load project");
      return null;
    } finally {
      setLoading(false);
    }
  }

  async function loadFile(path: string) {
    const file = await api.readFile(projectId, path);
    setSelectedPath(path);
    setContent(file.content);
    setDirty(false);
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function save() {
    if (!selectedPath) return;
    setSaving(true);
    setActionError(null);
    try {
      await api.saveFile(projectId, selectedPath, content);
      setDirty(false);
      await refresh();
      setMessages((items) => [`Saved ${selectedPath}`, ...items]);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not save file");
    } finally {
      setSaving(false);
    }
  }

  async function createFile() {
    const path = newFilePath.trim();
    if (!path) return;
    setActionError(null);
    try {
      await api.saveFile(projectId, path, "");
      setNewFilePath("");
      await refresh();
      await loadFile(path);
      setMessages((items) => [`Created ${path}`, ...items]);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not create file");
    }
  }

  async function renameSelected() {
    if (!selectedPath || !renamePath.trim()) return;
    const path = renamePath.trim();
    setActionError(null);
    try {
      await api.renameFile(projectId, selectedPath, path);
      setRenamePath("");
      await refresh();
      await loadFile(path);
      setMessages((items) => [`Renamed to ${path}`, ...items]);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not rename file");
    }
  }

  async function deleteSelected() {
    if (!selectedPath) return;
    const path = selectedPath;
    setActionError(null);
    try {
      await api.deleteFile(projectId, path);
      setSelectedPath("");
      setContent("");
      setDirty(false);
      await refresh();
      setMessages((items) => [`Deleted ${path}`, ...items]);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not delete file");
    }
  }

  async function runGenerate() {
    if (!chat.trim()) return;
    setActionError(null);
    try {
      const result = await api.generate(projectId, chat, selectedPath ? [selectedPath] : []);
      setMessages((items) => [result.assistant_explanation, ...result.notes, ...items]);
      setChat("");
      await refresh();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "AI generation failed");
    }
  }

  useEffect(() => {
    function handleShortcut(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") { event.preventDefault(); void save(); }
    }
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  });

  async function buildPreview() {
    setPreviewBusy(true);
    setPreviewError(null);
    previewPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    try {
      if (dirty && selectedPath) {
        await api.saveFile(projectId, selectedPath, content);
        setDirty(false);
        await refresh();
      }
      await api.buildPreview(projectId);
      await refresh();
      setPreviewKey((value) => value + 1);
      setMessages((items) => ["Preview built successfully.", ...items]);
    } catch (error) {
      setPreviewError(error instanceof Error ? error.message : "Preview build failed");
    } finally {
      setPreviewBusy(false);
    }
  }

  async function restartPreview() {
    await api.restartPreview(projectId);
    await refresh();
  }

  async function stopPreview() {
    await api.stopPreview(projectId);
    await refresh();
  }

  async function restoreCheckpoint(checkpointId: string) {
    await api.restoreCheckpoint(projectId, checkpointId);
    await refresh();
  }

  async function deleteProject() {
    if (!project || deletingProject) return;
    const confirmed = window.confirm(
      `Delete “${project.name}”? This permanently removes its files, checkpoints, preview container, and database record.`,
    );
    if (!confirmed) return;
    setDeletingProject(true);
    try {
      await api.deleteProject(projectId);
      window.location.href = "/";
    } catch (error) {
      setMessages((items) => [error instanceof Error ? error.message : "Project deletion failed", ...items]);
      setDeletingProject(false);
    }
  }

  const files = useMemo(
    () => (tree ? flattenTree(tree).filter((file) => file !== "stackforge.json" && !file.startsWith(".stackforge/")) : []),
    [tree],
  );
  const previewSrc = project?.preview_url
    ? `${project.preview_url}${project.preview_url.includes("?") ? "&" : "?"}v=${previewKey}`
    : null;

  return (
    <div className="workspace">
      <aside className="sidebar">
        <Link className="brand-link" href="/" aria-label="Back to StackForge dashboard">
          <span aria-hidden="true">←</span> StackForge Home
        </Link>
        <div className="meta">{user?.email}</div>
        <div className="section-heading">
          <div className="section-title">Files</div>
          <button className="icon-button" onClick={() => void refresh()} title="Refresh project" aria-label="Refresh project">↻</button>
        </div>
        <div style={{ display: "grid", gap: 8, marginBottom: 12 }}>
          <input value={fileFilter} onChange={(event) => setFileFilter(event.target.value)} placeholder="Search files…" aria-label="Search files" />
          <input value={newFilePath} onChange={(event) => setNewFilePath(event.target.value)} placeholder="new file path" />
          <button onClick={createFile}>Create File</button>
          <input value={renamePath} onChange={(event) => setRenamePath(event.target.value)} placeholder="rename to" />
          <button onClick={renameSelected}>Rename Selected</button>
          <button onClick={deleteSelected}>Delete Selected</button>
        </div>
        <div className="file-list">
          {files.filter((file) => file.toLowerCase().includes(fileFilter.toLowerCase())).map((file) => (
            <button key={file} className={`file-item ${selectedPath === file ? "active" : ""}`} onClick={() => loadFile(file)}>
              {file}
            </button>
          ))}
          {!loading && files.length > 0 && files.filter((file) => file.toLowerCase().includes(fileFilter.toLowerCase())).length === 0 ? <div className="empty small">No matching files</div> : null}
        </div>
        <div className="section-title">Checkpoints</div>
        <div className="checkpoint-list">
          {checkpoints.map((checkpoint) => (
            <button key={checkpoint.id} className="checkpoint-item" onClick={() => restoreCheckpoint(checkpoint.id)}>
              v{checkpoint.version} {checkpoint.label}
            </button>
          ))}
        </div>
      </aside>

      <main className="main">
        <div className="topbar">
          <div>
            <h1>{project?.name ?? "Project"}</h1>
            <p>{project?.description}</p>
          </div>
          <div className="actions">
            <button onClick={save} disabled={saving || !selectedPath} title={dirty ? "Save unsaved changes" : "Save the current file"}>{saving ? "Saving…" : "Save File"}</button>
            <button onClick={buildPreview} disabled={previewBusy}>{previewBusy ? "Building…" : "Build Preview"}</button>
            <button onClick={restartPreview}>Restart Preview</button>
            <button onClick={stopPreview}>Stop Preview</button>
            <button className="danger-button" onClick={deleteProject} disabled={deletingProject}>
              {deletingProject ? "Deleting…" : "Delete Project"}
            </button>
          </div>
        </div>

        {actionError ? <div className="action-error" role="alert">{actionError}<button onClick={() => setActionError(null)} aria-label="Dismiss error">×</button></div> : null}
        {loading ? <div className="loading-bar" role="status">Loading project…</div> : null}

        <div className="panels">
          <section className="panel chat-panel">
            <h2>AI Chat</h2>
            <textarea value={chat} onChange={(event) => setChat(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) void runGenerate(); }} placeholder="Describe the change you want… (⌘/Ctrl + Enter to run)" />
            <button onClick={runGenerate} disabled={!chat.trim()}>Generate / Apply Changes</button>
            <div className="message-list">
              {messages.map((message, index) => (
                <div key={index} className="message">
                  {message}
                </div>
              ))}
            </div>
          </section>

          <section className="panel editor-panel">
            <h2>Editor</h2>
            <div className="path">{selectedPath || "No file selected"}</div>
            <div className="editor-shell">
              <Editor height="100%" defaultLanguage="typescript" value={content} onChange={(value) => { setContent(value ?? ""); setDirty(true); }} theme="vs-dark" options={{ minimap: { enabled: false }, fontSize: 14, wordWrap: "on", scrollBeyondLastLine: false }} />
            </div>
          </section>

          <section className="panel preview-panel" ref={previewPanelRef}>
            <div className="panel-heading">
              <div>
                <h2>Preview</h2>
                <div className="preview-status">Status: {previewBusy ? "building" : project?.deployment_state ?? "not built"}</div>
              </div>
              {project?.preview_url ? (
                <a className="preview-link" href={project.preview_url} target="_blank" rel="noreferrer">
                  Open preview ↗
                </a>
              ) : null}
            </div>
            {project?.preview_url ? <div className="preview-url">{project.preview_url}</div> : null}
            {previewError ? <div className="preview-error">{previewError}</div> : null}
            <div className="preview-box">
              {previewBusy ? (
                <div className="empty">Building the preview container…</div>
              ) : previewSrc && project?.deployment_state === "running" ? (
                <iframe key={previewKey} title={`${project?.name ?? "Project"} preview`} src={previewSrc} />
              ) : (
                <div className="empty">Build the project to start its live preview.</div>
              )}
            </div>
          </section>

          <section className="panel logs-panel">
            <h2>Logs</h2>
            <pre>{logs || "No logs yet"}</pre>
          </section>
        </div>
      </main>
    </div>
  );
}
