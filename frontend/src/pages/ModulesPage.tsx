import { useCallback } from "react";
import { Link, useParams } from "react-router-dom";
import { getModules, listHistory } from "../api/endpoints";
import type { ModuleInfo, ModuleKey } from "../api/types";
import { HistoryList } from "../components/HistoryList";
import { ModuleCard } from "../components/ModuleCard";
import { Badge, Card, EmptyState, ErrorState, Loading, PageHeader } from "../components/ui";
import { useResource } from "../hooks/useResource";

export function ModulesPage() {
  const modules = useResource(useCallback(() => getModules(), []));
  return (
    <>
      <PageHeader title="Modules" description="The five areas FoodVerse AI is built around." />
      {modules.error ? (
        <ErrorState error={modules.error} onRetry={modules.reload} />
      ) : !modules.data ? (
        <Loading />
      ) : (
        <div className="module-grid">
          {modules.data.map((m) => <ModuleCard key={m.key} module={m} />)}
        </div>
      )}
    </>
  );
}

/** Only mounted once the module is known, so history is never fetched unfiltered. */
function ModuleHistory({ moduleKey, modules }: { moduleKey: ModuleKey; modules: ModuleInfo[] }) {
  const history = useResource(useCallback(() => listHistory(1, moduleKey, 5), [moduleKey]));
  return (
    <Card title="Your history for this module" headingId="module-history">
      {history.error ? (
        <ErrorState error={history.error} onRetry={history.reload} />
      ) : !history.data ? (
        <Loading />
      ) : history.data.items.length === 0 ? (
        <EmptyState title="No entries yet" />
      ) : (
        <HistoryList items={history.data.items} modules={modules} />
      )}
    </Card>
  );
}

export function ModuleDetailPage() {
  const { key } = useParams<{ key: string }>();
  const modules = useResource(useCallback(() => getModules(), []));
  const module = modules.data?.find((m) => m.key === key);

  if (modules.error) return <ErrorState error={modules.error} onRetry={modules.reload} />;
  if (!modules.data) return <Loading />;
  if (!module) {
    return (
      <EmptyState title="Module not found" description="That module does not exist."
        action={<Link to="/modules">Back to modules</Link>} />
    );
  }

  return (
    <>
      <PageHeader
        title={module.title}
        description={module.description}
        actions={module.available ? <Badge tone="ok">Available</Badge> : <Badge>Not available yet</Badge>}
      />
      {!module.available && (
        <div className="alert info" role="note">
          This module is not part of the current release, so there is nothing to run here yet.
          Nothing is simulated: results will only appear once the real feature ships.
        </div>
      )}
      <ModuleHistory moduleKey={module.key} modules={modules.data} />
      <p><Link to="/modules">← All modules</Link></p>
    </>
  );
}
