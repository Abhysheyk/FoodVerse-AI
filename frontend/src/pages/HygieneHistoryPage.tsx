import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { listHygieneInspections } from "../api/endpoints";
import type { HygieneLocationType, HygieneStatus } from "../api/types";
import { Badge, EmptyState, ErrorState, Loading, PageHeader, Pagination } from "../components/ui";
import { useResource } from "../hooks/useResource";
import { formatDate } from "../lib/format";
import { SEVERITY_TONE, STATUS_TONE } from "../lib/hygiene";

const STATUS_OPTIONS: { value: HygieneStatus | ""; label: string }[] = [
  { value: "", label: "All statuses" },
  { value: "draft", label: "Draft" },
  { value: "in_review", label: "In review" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
];

const LOCATION_OPTIONS: { value: HygieneLocationType | ""; label: string }[] = [
  { value: "", label: "All location types" },
  { value: "restaurant_kitchen", label: "Restaurant kitchen" },
  { value: "cafe", label: "Café" },
  { value: "food_truck", label: "Food truck" },
  { value: "home_kitchen", label: "Home kitchen" },
  { value: "institutional", label: "Institutional / commercial" },
  { value: "other", label: "Other" },
];

export function HygieneHistoryPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<HygieneStatus | "">("");
  const [locationType, setLocationType] = useState<HygieneLocationType | "">("");
  const list = useResource(useCallback(
    () => listHygieneInspections(page, status || null, locationType || null), [page, status, locationType]
  ));
  const data = list.data;
  return (
    <>
      <PageHeader title="Past inspections"
        description="Each report describes one set of photos on one day. It is not an official inspection."
        actions={<Link className="button-link" to="/hygiene">New inspection</Link>} />
      <div className="toolbar">
        <label htmlFor="h-status">Status</label>
        <select id="h-status" value={status} onChange={(e) => { setStatus(e.target.value as HygieneStatus | ""); setPage(1); }}>
          {STATUS_OPTIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        <label htmlFor="h-loc">Location type</label>
        <select id="h-loc" value={locationType} onChange={(e) => { setLocationType(e.target.value as HygieneLocationType | ""); setPage(1); }}>
          {LOCATION_OPTIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
      </div>
      {list.error ? <ErrorState error={list.error} onRetry={list.reload} />
        : !data ? <Loading />
        : data.items.length === 0 ? <EmptyState title="No inspections yet" description="Create one and it will be listed here." />
        : (
          <>
            <ul className="history-list">
              {data.items.map((h) => (
                <li key={h.id}>
                  <div className="history-main">
                    <p className="history-title"><Link to={`/hygiene/${h.id}`}>{h.location_name}</Link></p>
                    <p className="muted small-text">
                      {h.location_type_label}{h.area ? ` · ${h.area}` : ""} · <time dateTime={h.created_at}>{formatDate(h.created_at)}</time>
                      {" · "}{h.photo_count} photo{h.photo_count === 1 ? "" : "s"}
                    </p>
                  </div>
                  <div className="history-side">
                    <Badge tone={STATUS_TONE[h.status]}>{h.status_label}</Badge>
                    {h.highest_severity && <Badge tone={SEVERITY_TONE[h.highest_severity]}>Highest: {h.highest_severity}</Badge>}
                  </div>
                </li>
              ))}
            </ul>
            <Pagination page={data.page} pages={data.pages} onChange={setPage} />
          </>
        )}
    </>
  );
}