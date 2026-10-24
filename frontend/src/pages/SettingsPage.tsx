import { useState } from "react";
import type { FormEvent } from "react";
import { changePassword, updateProfile } from "../api/endpoints";
import { useAuth } from "../auth/AuthContext";
import { FormError, errorMessage } from "../components/FormError";
import { PreferencesForm } from "../components/PreferencesForm";
import { useToast } from "../components/Toast";
import { Card, PageHeader } from "../components/ui";

function ProfileForm() {
  const { state, updateUser } = useAuth();
  const toast = useToast();
  const [name, setName] = useState(state.user?.display_name ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      updateUser(await updateProfile(name));
      toast.success("Profile updated.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Profile" headingId="profile-heading">
      <form onSubmit={onSubmit} noValidate>
        <label htmlFor="display-name">Display name</label>
        <input id="display-name" value={name} maxLength={80} required autoComplete="name"
          onChange={(e) => setName(e.target.value)} />
        <label htmlFor="account-email">Email</label>
        <input id="account-email" value={state.user?.email ?? ""} readOnly aria-describedby="email-hint" />
        <p id="email-hint" className="hint">Your email is your sign-in and cannot be changed here.</p>
        <FormError message={error} />
        <button type="submit" disabled={busy || !name.trim()}>{busy ? "Saving…" : "Save profile"}</button>
      </form>
    </Card>
  );
}

function PasswordForm() {
  const { logout } = useAuth();
  const toast = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (next.length < 10) return setError("New password must be at least 10 characters.");
    if (next !== confirm) return setError("The new passwords do not match.");
    setBusy(true);
    try {
      await changePassword(current, next);
      toast.success("Password changed. Please sign in again.");
      await logout(); // every session was revoked server-side
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <Card title="Change password" headingId="password-heading">
      <form onSubmit={onSubmit} noValidate>
        <label htmlFor="current-password">Current password</label>
        <input id="current-password" type="password" autoComplete="current-password" value={current}
          onChange={(e) => setCurrent(e.target.value)} />
        <label htmlFor="new-password">New password</label>
        <input id="new-password" type="password" autoComplete="new-password" value={next}
          aria-describedby="new-pw-hint" onChange={(e) => setNext(e.target.value)} />
        <p id="new-pw-hint" className="hint">At least 10 characters. You will be signed out on all devices.</p>
        <label htmlFor="confirm-password">Confirm new password</label>
        <input id="confirm-password" type="password" autoComplete="new-password" value={confirm}
          onChange={(e) => setConfirm(e.target.value)} />
        <FormError message={error} />
        <button type="submit" disabled={busy || !current || !next}>{busy ? "Changing…" : "Change password"}</button>
      </form>
    </Card>
  );
}

export function SettingsPage() {
  return (
    <>
      <PageHeader title="Settings" description="Your profile, food preferences and security." />
      <ProfileForm />
      <PreferencesForm />
      <PasswordForm />
    </>
  );
}
