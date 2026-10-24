import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { FormError, errorMessage } from "../components/FormError";

export function RegisterPage() {
  const { register } = useAuth();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 10) {
      setError("Password must be at least 10 characters.");
      return;
    }
    setBusy(true);
    try {
      await register(displayName.trim(), email, password);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <main className="auth-card">
      <h1>Create your account</h1>
      <form onSubmit={handleSubmit} noValidate>
        <label htmlFor="name">Display name</label>
        <input id="name" autoComplete="name" required maxLength={80} value={displayName}
          onChange={(e) => setDisplayName(e.target.value)} />
        <label htmlFor="email">Email</label>
        <input id="email" type="email" autoComplete="email" required value={email}
          onChange={(e) => setEmail(e.target.value)} />
        <label htmlFor="password">Password</label>
        <input id="password" type="password" autoComplete="new-password" required minLength={10}
          maxLength={128} aria-describedby="pw-hint" value={password}
          onChange={(e) => setPassword(e.target.value)} />
        <p id="pw-hint" className="hint">At least 10 characters. A long passphrase works well.</p>
        <FormError message={error} />
        <button type="submit" disabled={busy}>{busy ? "Creating account…" : "Create account"}</button>
      </form>
      <p>Already registered? <Link to="/login">Sign in</Link></p>
    </main>
  );
}
