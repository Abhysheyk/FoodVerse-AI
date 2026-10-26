import { Link } from "react-router-dom";
import type { ModuleInfo } from "../api/types";
import { Badge } from "./ui";

/** Where an implemented module lives. Unimplemented modules keep their "not available" page. */
const MODULE_HOME: Partial<Record<ModuleInfo["key"], string>> = { food_recognition: "/food" };

export function ModuleCard({ module, count }: { module: ModuleInfo; count?: number }) {
  return (
    <article className="module-card">
      <div className="module-card-head">
        <h3>
          <Link to={MODULE_HOME[module.key] ?? `/modules/${module.key}`} className="stretched">{module.title}</Link>
        </h3>
        {module.available ? <Badge tone="ok">Available</Badge> : <Badge>Not available yet</Badge>}
      </div>
      <p className="muted">{module.description}</p>
      {count !== undefined && count > 0 && <p className="muted small-text">{count} in your history</p>}
    </article>
  );
}
