import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  HISTORY_ITEM, MODULES, authBody, dashboardRoutes, emptySummary, errorBody, json, mockApi, renderApp,
} from "./helpers";

const signedIn = { "POST /auth/refresh": () => json(200, authBody()) };

describe("dashboard data loading", () => {
  it("shows real numbers and activity from the API", async () => {
    mockApi({
      ...signedIn,
      ...dashboardRoutes({
        "GET /dashboard/summary": () =>
          json(200, {
            media: { count: 3, total_bytes: 2621440, quota_bytes: 524288000, max_upload_bytes: 8388608 },
            history: { total: 2, by_module: { freshness: 2 } },
            recent: [HISTORY_ITEM, { ...HISTORY_ITEM, id: "h2", title: "Banana check" }],
          }),
      }),
    });
    renderApp("/");

    const stats = await screen.findByRole("region", { name: "Your numbers" });
    expect(await within(stats).findByText("3")).toBeInTheDocument();
    expect(within(stats).getByText("2.5 MB")).toBeInTheDocument();
    expect(within(stats).getByText("of 500 MB")).toBeInTheDocument();
    expect(within(stats).getByText("2")).toBeInTheDocument();
    expect(await screen.findByText("Tomato check")).toBeInTheDocument();
    expect(screen.getByText("Banana check")).toBeInTheDocument();
    expect(screen.getByText("2 in your history")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View all history" })).toHaveAttribute("href", "/history");
  });

  it("shows honest empty states instead of invented statistics", async () => {
    mockApi({ ...signedIn, ...dashboardRoutes() });
    renderApp("/");

    expect(await screen.findByText("Nothing uploaded yet")).toBeInTheDocument();
    expect(screen.getByText("None yet")).toBeInTheDocument();
    expect(screen.getByText("No analyses yet")).toBeInTheDocument();
    expect(screen.queryByText(/in your history/)).not.toBeInTheDocument();
    // Every module is honestly labelled; nothing offers to run an analysis.
    expect(await screen.findAllByText("Not available yet")).toHaveLength(MODULES.length);
    expect(screen.queryByRole("button", { name: /analy[sz]e|scan|start/i })).not.toBeInTheDocument();
  });

  it("shows a loading state while the summary is in flight", async () => {
    let release: (r: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => (release = resolve));
    mockApi({ ...signedIn, ...dashboardRoutes({ "GET /dashboard/summary": () => pending }) });
    renderApp("/");

    expect(await screen.findByText("Loading your summary…")).toBeInTheDocument();
    release(json(200, emptySummary));
    expect(await screen.findByText("Nothing uploaded yet")).toBeInTheDocument();
    expect(screen.queryByText("Loading your summary…")).not.toBeInTheDocument();
  });

  it("shows an error state with retry, and recovers", async () => {
    let fail = true;
    mockApi({
      ...signedIn,
      ...dashboardRoutes({
        "GET /dashboard/summary": () =>
          fail ? json(500, errorBody("internal_error", "An unexpected error occurred.")) : json(200, emptySummary),
      }),
    });
    const user = userEvent.setup();
    renderApp("/");

    const alerts = await screen.findAllByRole("alert");
    expect(alerts.some((a) => a.textContent?.includes("An unexpected error occurred."))).toBe(true);
    fail = false;
    await user.click(screen.getAllByRole("button", { name: "Try again" })[0]);
    expect(await screen.findByText("Nothing uploaded yet")).toBeInTheDocument();
  });

  it("reports local AI status without implying a paid fallback", async () => {
    mockApi({ ...signedIn, ...dashboardRoutes() });
    renderApp("/");
    expect(await screen.findByText(/Ollama: disabled/)).toBeInTheDocument();
    expect(screen.getByText("Paid or external AI fallback: none")).toBeInTheDocument();
  });
});

describe("navigation and modules", () => {
  it("offers every section, marks the current page, and has a skip link", async () => {
    mockApi({ ...signedIn, ...dashboardRoutes() });
    renderApp("/");
    const nav = await screen.findByRole("navigation", { name: "Main" });
    for (const name of ["Dashboard", "Modules", "History", "Media", "Settings"]) {
      expect(within(nav).getByRole("link", { name })).toBeInTheDocument();
    }
    expect(within(nav).getByRole("link", { name: "Dashboard" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveAttribute("href", "#main");
  });

  it("lists all five modules as not yet available", async () => {
    mockApi({ ...signedIn, ...dashboardRoutes() });
    const user = userEvent.setup();
    renderApp("/");
    await user.click(await screen.findByRole("link", { name: "Modules" }));
    expect(await screen.findByRole("heading", { name: "Modules", level: 1 })).toBeInTheDocument();
    for (const m of MODULES) expect(await screen.findByRole("link", { name: m.title })).toBeInTheDocument();
    expect(screen.getAllByText("Not available yet")).toHaveLength(5);
  });

  it("a module page explains the module is not available and shows its (empty) history", async () => {
    mockApi({
      ...signedIn,
      ...dashboardRoutes({ "GET /history?page=1&page_size=5&module=freshness": () => json(200, { items: [], total: 0, page: 1, page_size: 5, pages: 0 }) }),
    });
    renderApp("/modules/freshness");
    expect(await screen.findByRole("heading", { name: "Freshness check" })).toBeInTheDocument();
    expect(await screen.findByText(/not part of the current release/)).toBeInTheDocument();
    expect(await screen.findByText("No entries yet")).toBeInTheDocument();
  });

  it("handles an unknown module", async () => {
    const { calls } = mockApi({ ...signedIn, ...dashboardRoutes() });
    renderApp("/modules/nope");
    expect(await screen.findByText("Module not found")).toBeInTheDocument();
    expect(calls.some((c) => c.key.startsWith("GET /history"))).toBe(false);
  });
});
