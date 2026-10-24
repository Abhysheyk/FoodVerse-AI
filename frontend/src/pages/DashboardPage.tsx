import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getAIStatus } from "../api/endpoints";
import type { AIStatus } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { errorMessage } from "../components/FormError";

function modelLine(label: string, m: AIStatus["ollama"]["text_model"]): string {
  if (!m.configured) return `${label}: not configured`;
  if (m.installed === null) return `${label}: ${m.name} (installation unknown)`;
  return `${label}: ${m.name} (${m.installed ? "installed" : "not installed"})`;
}

export function DashboardPage() {
  const { state } = useAuth();
  const [status, setStatus] = useState<AIStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getAIStatus()
      .then((s) => !cancelled && setStatus(s))
      .catch((e) => !cancelled && setError(errorMessage(e)));
    return () => {
      cancelled = true;
    };
  }, []);

  const ollama = status?.ollama;
  return (
    <>
      <h1>Welcome, {state.user?.display_name}</h1>
      <p>
        Your account is ready. Food recognition, freshness, hygiene, cooking and meal-planning
        modules are not part of this release yet. Set your dietary preferences and allergies in{" "}
        <Link to="/preferences">Preferences</Link> so future features can respect them.
      </p>

      <section className="card" aria-labelledby="ai-heading">
        <h2 id="ai-heading">Local AI status</h2>
        {error && <p className="alert error" role="alert">{error}</p>}
        {!status && !error && <p role="status">Checking…</p>}
        {ollama && (
          <ul>
            <li>
              Ollama:{" "}
              {!ollama.enabled
                ? "disabled (set OLLAMA_ENABLED=true on the server to use a local model)"
                : ollama.reachable
                  ? "reachable"
                  : "not reachable"}
            </li>
            {ollama.error && <li>{ollama.error}</li>}
            <li>{modelLine("Text model", ollama.text_model)}</li>
            <li>{modelLine("Vision model", ollama.vision_model)}</li>
            <li>Paid or external AI fallback: none</li>
          </ul>
        )}
      </section>
    </>
  );
}
