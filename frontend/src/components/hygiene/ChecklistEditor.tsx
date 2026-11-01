import type { ChecklistItem } from "../../api/types";

export function ChecklistEditor({
  value, disabled, onChange,
}: {
  value: ChecklistItem[];
  disabled: boolean;
  onChange: (next: ChecklistItem[]) => void;
}) {
  return (
    <table className="nutrient-table">
      <thead><tr><th scope="col">✔</th><th scope="col">Item</th><th scope="col">Note</th></tr></thead>
      <tbody>
        {value.map((item, i) => (
          <tr key={item.item_id}>
            <td>
              <input
                type="checkbox" checked={item.checked} disabled={disabled}
                onChange={(e) => {
                  const next = [...value]; next[i] = { ...item, checked: e.target.checked }; onChange(next);
                }}
                aria-label={item.label}
              />
            </td>
            <td>{item.label}</td>
            <td>
              <input
                type="text" value={item.note ?? ""} maxLength={300} disabled={disabled}
                onChange={(e) => {
                  const next = [...value]; next[i] = { ...item, note: e.target.value || null }; onChange(next);
                }}
                aria-label={`Note for ${item.label}`}
              />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}