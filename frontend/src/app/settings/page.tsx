"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Role, User } from "@/lib/types";

const ROLES: Role[] = ["admin", "builder", "viewer"];
const MIN_PASSWORD_LENGTH = 12;

const ROLE_HELP: Record<Role, string> = {
  admin: "Full access: every project, platform settings, and user administration.",
  builder: "Creates and edits their own projects. Cannot see other people's work.",
  viewer: "Read-only. Cannot create projects.",
};

export default function SettingsPage() {
  const [me, setMe] = useState<User | null>(null);
  const [users, setUsers] = useState<User[] | null>(null);
  const [platform, setPlatform] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordDone, setPasswordDone] = useState(false);

  const [newEmail, setNewEmail] = useState("");
  const [newUserPassword, setNewUserPassword] = useState("");
  const [newRole, setNewRole] = useState<Role>("builder");
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [userError, setUserError] = useState<string | null>(null);

  const isAdmin = me?.role === "admin";

  const loadUsers = useCallback(async () => {
    setUsers(await api.listUsers());
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const account = await api.me();
        setMe(account);
        if (account.role === "admin") {
          await Promise.all([
            loadUsers(),
            api.settings().then(setPlatform).catch(() => setPlatform(null)),
          ]);
        }
      } catch {
        window.location.href = "/login";
        return;
      } finally {
        setLoading(false);
      }
    })();
  }, [loadUsers]);

  async function submitPassword() {
    setPasswordBusy(true);
    setPasswordError(null);
    setPasswordDone(false);
    try {
      await api.changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setPasswordDone(true);
    } catch (err) {
      setPasswordError(err instanceof Error ? err.message : "Could not change the password");
    } finally {
      setPasswordBusy(false);
    }
  }

  async function submitUser() {
    setCreateBusy(true);
    setCreateError(null);
    try {
      await api.createUser(newEmail.trim(), newUserPassword, newRole);
      setNewEmail("");
      setNewUserPassword("");
      setNewRole("builder");
      await loadUsers();
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Could not create the user");
    } finally {
      setCreateBusy(false);
    }
  }

  async function changeUser(user: User, changes: { role?: Role; is_active?: boolean }) {
    setUserError(null);
    try {
      await api.updateUser(user.id, changes);
      await loadUsers();
    } catch (err) {
      setUserError(err instanceof Error ? err.message : "Could not update the user");
    }
  }

  if (loading) {
    return (
      <div className="auth-shell">
        <p className="meta">Loading settings…</p>
      </div>
    );
  }

  return (
    <div className="settings-shell">
      <Link className="brand-link" href="/">
        ← StackForge
      </Link>
      <h1>Settings</h1>

      <section className="panel">
        <div className="panel-heading">
          <h2>Your account</h2>
        </div>
        <p className="meta">
          {me?.email} · {me?.role}
        </p>
        <p className="meta">{me ? ROLE_HELP[me.role] : null}</p>

        <h3 className="section-title">Change your password</h3>
        {passwordError ? <div className="action-error">{passwordError}</div> : null}
        {passwordDone ? <p className="meta">Password updated. It applies the next time you sign in.</p> : null}
        <div className="settings-form">
          <input
            type="password"
            placeholder="Current password"
            autoComplete="current-password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
          />
          <input
            type="password"
            placeholder={`New password (at least ${MIN_PASSWORD_LENGTH} characters)`}
            autoComplete="new-password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
          />
          <button
            type="button"
            onClick={submitPassword}
            disabled={passwordBusy || !currentPassword || newPassword.length < MIN_PASSWORD_LENGTH}
          >
            {passwordBusy ? "Saving…" : "Change password"}
          </button>
        </div>
      </section>

      {isAdmin ? (
        <section className="panel">
          <div className="panel-heading">
            <h2>Users</h2>
            <span className="meta">{users?.length ?? 0} total</span>
          </div>
          {userError ? <div className="action-error">{userError}</div> : null}
          <p className="meta">
            Access is revoked by deactivating an account, not deleting it — projects belong to their
            owner. Nobody can set another person&apos;s password; each user changes their own above.
          </p>

          <div className="user-table">
            {(users ?? []).map((user) => (
              <div className="user-row" key={user.id}>
                <div>
                  <strong>{user.email}</strong>
                  {user.id === me?.id ? <span className="meta"> · you</span> : null}
                  <div className="meta">{user.is_active ? "active" : "deactivated"}</div>
                </div>
                <select
                  value={user.role}
                  onChange={(event) => changeUser(user, { role: event.target.value as Role })}
                >
                  {ROLES.map((role) => (
                    <option key={role} value={role}>
                      {role}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className={user.is_active ? "danger-button" : "icon-button"}
                  onClick={() => changeUser(user, { is_active: !user.is_active })}
                >
                  {user.is_active ? "Deactivate" : "Reactivate"}
                </button>
              </div>
            ))}
          </div>

          <h3 className="section-title">Add a user</h3>
          {createError ? <div className="action-error">{createError}</div> : null}
          <div className="settings-form">
            <input
              placeholder="Email"
              value={newEmail}
              onChange={(event) => setNewEmail(event.target.value)}
            />
            <input
              type="password"
              placeholder={`Initial password (at least ${MIN_PASSWORD_LENGTH} characters)`}
              autoComplete="new-password"
              value={newUserPassword}
              onChange={(event) => setNewUserPassword(event.target.value)}
            />
            <select value={newRole} onChange={(event) => setNewRole(event.target.value as Role)}>
              {ROLES.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
            <p className="meta">{ROLE_HELP[newRole]}</p>
            <button
              type="button"
              onClick={submitUser}
              disabled={createBusy || !newEmail.trim() || newUserPassword.length < MIN_PASSWORD_LENGTH}
            >
              {createBusy ? "Creating…" : "Create user"}
            </button>
          </div>
        </section>
      ) : null}

      {isAdmin ? (
        <section className="panel">
          <div className="panel-heading">
            <h2>Platform</h2>
          </div>
          <p className="meta">Read-only view of the server environment.</p>
          <pre>{JSON.stringify(platform, null, 2)}</pre>
        </section>
      ) : null}
    </div>
  );
}
