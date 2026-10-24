import type { HistoryItem, ModuleInfo } from "../api/types";
import { formatDate } from "../lib/format";
import { Badge } from "./ui";

export function HistoryList({
  items,
  modules,
  onDelete,
}: {
  items: HistoryItem[];
  modules: ModuleInfo[];
  onDelete?: (item: HistoryItem) => void;
}) {
  const title = (key: string) => modules.find((m) => m.key === key)?.title ?? key;
  return (
    <ul className="history-list">
      {items.map((item) => (
        <li key={item.id}>
          <div className="history-main">
            <p className="history-title">{item.title}</p>
            <p className="muted small-text">
              {title(item.module)} · <time dateTime={item.created_at}>{formatDate(item.created_at)}</time>
            </p>
            {item.summary && <p className="history-summary">{item.summary}</p>}
          </div>
          <div className="history-side">
            <Badge tone={item.status === "completed" ? "ok" : item.status === "failed" ? "warn" : "neutral"}>
              {item.status}
            </Badge>
            {onDelete && (
              <button type="button" className="secondary small" onClick={() => onDelete(item)}
                aria-label={`Delete ${item.title}`}>
                Delete
              </button>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
