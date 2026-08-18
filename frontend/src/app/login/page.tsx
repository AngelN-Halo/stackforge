"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export default function LoginPage() {
  const [email, setEmail] = useState("admin@stackforge.local");
  const [password, setPassword] = useState("changeme123");
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    try {
      await api.login(email, password);
      window.location.href = "/";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    }
  }

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <h1>Sign in</h1>
        <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="Email" />
        <input value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Password" type="password" />
        <button onClick={submit}>Login</button>
        {error ? <p>{error}</p> : null}
      </div>
    </div>
  );
}
