/** Monday-anchored week helpers used by the planner and dashboard. */
export function mondayOf(d: Date = new Date()): Date {
  const copy = new Date(d);
  const dow = copy.getDay(); // 0=Sun..6=Sat
  const diff = dow === 0 ? -6 : 1 - dow;
  copy.setDate(copy.getDate() + diff);
  copy.setHours(0, 0, 0, 0);
  return copy;
}
export function toISODate(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
export function shiftDays(d: Date, days: number): Date {
  const copy = new Date(d);
  copy.setDate(copy.getDate() + days);
  return copy;
}
export function formatWeek(weekStart: Date): string {
  const end = shiftDays(weekStart, 6);
  const fmt = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });
  return `${fmt.format(weekStart)} – ${fmt.format(end)}`;
}
export function dayLabel(iso: string): string {
  return new Intl.DateTimeFormat(undefined, { weekday: "long", month: "short", day: "numeric" })
    .format(new Date(iso + "T12:00:00"));
}