"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function SettingsPage() {
  const [data, setData] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    void api.settings().then(setData).catch(() => setData(null));
  }, []);

  return (
    <div className="page-shell">
      <div className="auth-card" style={{ width: "min(760px, 100%)" }}>
        <h1>Settings</h1>
        <pre>{JSON.stringify(data, null, 2)}</pre>
      </div>
    </div>
  );
}
