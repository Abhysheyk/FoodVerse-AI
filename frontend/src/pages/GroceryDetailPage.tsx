import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { deleteGroceryList, getGroceryList, updateGroceryList } from "../api/endpoints";
import { ApiError } from "../api/client";
import type { GroceryItem, GroceryItemIn } from "../api/types";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { FormError, errorMessage } from "../components/FormError";
import { useToast } from "../components/Toast";
import { EmptyState, ErrorState, Loading, PageHeader } from "../components/ui";
import { useResource } from "../hooks/useResource";

interface Row {
  id?: string;
  name: string;
  quantity: number;
  unit: string;
  checked: boolean;
  notes: string | null;
}

function toRow(i: GroceryItem): Row {
  return { id: i.id, name: i.name, quantity: i.quantity, unit: i.unit, checked: i.checked, notes: i.notes };
}

export function GroceryDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const toast = useToast();
  const list = useResource(useCallback(() => getGroceryList(id), [id]));
  const [rows, setRows] = useState<Row[]>([]);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (list.data) {
      setRows(list.data.items.map(toRow));
      setDirty(false);
    }
  }, [list.data]);

  function edit(idx: number, patch: Partial<Row>) {
    setRows((cur) => cur.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
    setDirty(true);
  }

  function remove(idx: number) {
    setRows((cur) => cur.filter((_, i) => i !== idx));
    setDirty(true);
  }

  async function save() {
    if (!list.data) return;
    if (rows.length === 0) return setError("A grocery list needs at least one item.");
    for (const [i, r] of rows.entries()) {
      if (!r.name.trim()) return setError(`Row ${i + 1} needs a name.`);
      if (!(r.quantity > 0)) return setError(`Row ${i + 1} needs a positive quantity.`);
      if (!r.unit.trim()) return setError(`Row ${i + 1} needs a unit.`);
    }
    setSaving(true);
    setError(null);
    try {
      const payload: GroceryItemIn[] = rows.map((r) => ({
        name: r.name.trim(),
        quantity: r.quantity,
        unit: r.unit,
        checked: r.checked,
        notes: r.notes,
      }));
      await updateGroceryList(id, {
        title: list.data.title,
        items: payload,
        expected_revision: list.data.revision,
      });
      toast.success("Grocery list saved.");
      list.reload();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function onDelete() {
    try {
      await deleteGroceryList(id);
      toast.success("Grocery list deleted.");
      navigate("/grocery");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setConfirmDelete(false);
    }
  }

  if (list.error instanceof ApiError && list.error.status === 404) {
    return <EmptyState title="Grocery list not found"
      action={<Link to="/grocery">Back to lists</Link>} />;
  }
  if (list.error) return <ErrorState error={list.error} onRetry={list.reload} />;
  if (!list.data) return <Loading />;
  const checkedCount = rows.filter((r) => r.checked).length;

  return (
    <>
      <PageHeader
        title={list.data.title}
        description={<>{rows.length} item{rows.length === 1 ? "" : "s"} · {checkedCount} checked</>}
        actions={<>
          <Link className="button-link secondary" to="/grocery">Back</Link>
          <button type="button" className="secondary" onClick={() => setConfirmDelete(true)}>Delete</button>
        </>} />

      <FormError message={error} />

      <ul className="history-list">
        {rows.map((r, i) => (
          <li key={r.id ?? i}>
            <div className="row" style={{ flex: 1, gap: ".5rem" }}>
              <label className="visually-hidden" htmlFor={`row-${i}-checked`}>
                {r.name} purchased
              </label>
              <input id={`row-${i}-checked`} type="checkbox" checked={r.checked}
                onChange={(e) => edit(i, { checked: e.target.checked })} />
              <label className="visually-hidden" htmlFor={`row-${i}-name`}>Item name</label>
              <input id={`row-${i}-name`} value={r.name}
                onChange={(e) => edit(i, { name: e.target.value })}
                style={{ flex: 2 }} />
              <label className="visually-hidden" htmlFor={`row-${i}-qty`}>Quantity</label>
              <input id={`row-${i}-qty`} type="number" min={0.01} step="0.01" value={r.quantity}
                onChange={(e) => edit(i, { quantity: Number(e.target.value) })}
                style={{ maxWidth: 100 }} />
              <label className="visually-hidden" htmlFor={`row-${i}-unit`}>Unit</label>
              <input id={`row-${i}-unit`} value={r.unit} maxLength={16}
                onChange={(e) => edit(i, { unit: e.target.value })}
                style={{ maxWidth: 80 }} />
            </div>
            <button type="button" className="secondary small" onClick={() => remove(i)}
              aria-label={`Remove ${r.name}`}>Remove</button>
          </li>
        ))}
      </ul>

      <div className="row wrap">
        <button type="button" onClick={save} disabled={!dirty || saving}>
          {saving ? "Saving…" : "Save list"}
        </button>
      </div>

      <ConfirmDialog open={confirmDelete} title="Delete this grocery list?"
        message={`“${list.data.title}” will be removed.`}
        confirmLabel="Delete" onConfirm={onDelete} onCancel={() => setConfirmDelete(false)} />
    </>
  );
}