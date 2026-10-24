import { Link } from "react-router-dom";
import type { ModuleInfo } from "../api/types";
import { Badge } from "./ui";

export function ModuleCard({ module, count }: { module: ModuleInfo; count?: number }) {
  return (
    <article className="module-card">
      <div className="module-card-head">
        <h3>
          <Link to={`/modules/${module.key}`} className="stretched">{module.title}</Link>
        </h3>
        {module.available ? <Badge tone="ok">Available</Badge> : <Badge>Not available yet</Badge>}
      </div>
      <p className="muted">{module.description}</p>
      {count !== undefined && count > 0 && <p className="muted small-text">{count} in your history</p>}
    </article>
  );
}
