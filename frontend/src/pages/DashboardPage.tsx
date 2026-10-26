import { useCallback } from "react";
import { Link } from "react-router-dom";
import { getAIStatus, getDashboardSummary, getModules } from "../api/endpoints";
import type { AIStatus } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { HistoryList } from "../components/HistoryList";
import { ModuleCard } from "../components/ModuleCard";
import { Card, EmptyState, ErrorState, Loading, PageHeader } from "../components/ui";
import { useResource } from "../hooks/useResource";
import { formatBytes } from "../lib/format";

function modelLine(label: string, m: AIStatus["ollama"]["text_model"]): string {
  if (!m.configured) return `${label}: not configured`;
  if (m.installed === null) return `${label}: ${m.name} (installation unknown)`;
  return `${label}: ${m.name} (${m.installed ? "installed" : "not installed"})`;
}

function Stat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="stat">
      <dt>{label}</dt>
      <dd>{value}</dd>
      <p className="muted small-text">{hint}</p>
    </div>
  );
}

export function DashboardPage() {
  const { state } = useAuth();
  const summary = useResource(useCallback(() => getDashboardSummary(), []));
  const modules = useResource(useCallback(() => getModules(), []));
  const ai = useResource(useCallback(() => getAIStatus(), []));
  const s = summary.data;
  const ollama = ai.data?.ollama;

  return (
    <>
      <PageHeader
        title={`Welcome, ${state.user?.display_name ?? ""}`}
        description="Your food intelligence workspace. Everything below reflects your own data."
      />

      <section aria-label="Your numbers">
        {summary.error ? (
          <ErrorState error={summary.error} onRetry={summary.reload} />
        ) : !s ? (
          <Loading label="Loading your summary…" />
        ) : (
          <dl className="stats">
            <Stat label="Photos in library" value={String(s.media.count)}
              hint={s.media.count === 0 ? "Nothing uploaded yet" : "Stored privately for you"} />
            <Stat label="Storage used" value={formatBytes(s.media.total_bytes)}
              hint={`of ${formatBytes(s.media.quota_bytes)}`} />
            <Stat label="Analyses" value={String(s.history.total)}
              hint={s.history.total === 0 ? "None yet" : "Across all modules"} />
          </dl>
        )}
      </section>

      <Card title="Modules" headingId="modules-heading">
        {modules.error ? (
          <ErrorState error={modules.error} onRetry={modules.reload} />
        ) : !modules.data ? (
          <Loading />
        ) : (
          <div className="module-grid">
            {modules.data.map((m) => (
              <ModuleCard key={m.key} module={m} count={s?.history.by_module[m.key]} />
            ))}
          </div>
        )}
      </Card>

      <Card title="Recent activity" headingId="recent-heading">
        {summary.error ? null : !s ? (
          <Loading />
        ) : s.recent.length === 0 ? (
          <EmptyState
            title="No analyses yet"
            description="When analysis modules are released, your results will appear here."
            action={<Link to="/media" className="button-link">Add photos to your library</Link>}
          />
        ) : (
          <>
            <HistoryList items={s.recent} modules={modules.data ?? []} />
            <p><Link to="/history">View all history</Link></p>
          </>
        )}
      </Card>

      <p className="small-text">
        Also: <Link to="/modules">All modules</Link> · <Link to="/media">Media library</Link>
      </p>

      <Card title="Local AI status" headingId="ai-heading">
        {ai.error ? <ErrorState error={ai.error} onRetry={ai.reload} /> : null}
        {!ai.data && !ai.error ? <Loading label="Checking…" /> : null}
        {ollama && (
          <ul className="plain-list">
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
      </Card>
    </>
  );
}
