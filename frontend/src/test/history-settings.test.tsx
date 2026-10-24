import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  HISTORY_ITEM, MODULES, authBody, dashboardRoutes, errorBody, json, mockApi, page, renderApp,
} from "./helpers";

const signedIn = { "POST /auth/refresh": () => json(200, authBody()) };
const H1 = "GET /history?page=1&page_size=10";

describe("history", () => {
  it("shows an empty state, not invented entries", async () => {
    mockApi({ ...signedIn, "GET /modules": () => json(200, MODULES), [H1]: () => json(200, page([])) });
    renderApp("/history");
    expect(await screen.findByText("No history yet")).toBeInTheDocument();
    expect(screen.getByText(/Nothing is added automatically/)).toBeInTheDocument();
    expect(await screen.findByText("0 entries")).toBeInTheDocument();
  });

  it("lists entries with module, date and status", async () => {
    mockApi({
      ...signedIn,
      "GET /modules": () => json(200, MODULES),
      [H1]: () => json(200, page([HISTORY_ITEM, { ...HISTORY_ITEM, id: "h2", title: "Pan check", status: "failed", summary: null }])),
    });
    renderApp("/history");
    expect(await screen.findByText("Tomato check")).toBeInTheDocument();
    expect(screen.getByText("Looks fresh")).toBeInTheDocument();
    expect(screen.getByText("completed")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
    expect(screen.getAllByText(/Freshness check/).length).toBeGreaterThan(0);
    expect(screen.getByText("2 entries")).toBeInTheDocument();
  });

  it("filters by module through the API", async () => {
    const { calls } = mockApi({
      ...signedIn,
      "GET /modules": () => json(200, MODULES),
      [H1]: () => json(200, page([HISTORY_ITEM])),
      "GET /history?page=1&page_size=10&module=hygiene": () => json(200, page([])),
    });
    const user = userEvent.setup();
    renderApp("/history");
    await screen.findByText("Tomato check");
    await user.selectOptions(await screen.findByLabelText("Module"), "hygiene");
    expect(await screen.findByText("No entries for this module")).toBeInTheDocument();
    expect(calls.some((c) => c.key.endsWith("module=hygiene"))).toBe(true);
  });

  it("deletes an entry only after confirmation", async () => {
    let items = [HISTORY_ITEM];
    const { calls } = mockApi({
      ...signedIn,
      "GET /modules": () => json(200, MODULES),
      [H1]: () => json(200, page(items)),
      "DELETE /history/h1": () => {
        items = [];
        return new Response(null, { status: 204 });
      },
    });
    const user = userEvent.setup();
    renderApp("/history");
    await user.click(await screen.findByRole("button", { name: "Delete Tomato check" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete this entry?" });
    expect(calls.some((c) => c.key === "DELETE /history/h1")).toBe(false);
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("History entry deleted.")).toBeInTheDocument();
    expect(await screen.findByText("No history yet")).toBeInTheDocument();
  });

  it("paginates", async () => {
    mockApi({
      ...signedIn,
      "GET /modules": () => json(200, MODULES),
      [H1]: () => json(200, page([HISTORY_ITEM], { total: 11, pages: 2 })),
      "GET /history?page=2&page_size=10": () =>
        json(200, page([{ ...HISTORY_ITEM, id: "h11", title: "Older check" }], { page: 2, total: 11, pages: 2 })),
    });
    const user = userEvent.setup();
    renderApp("/history");
    await screen.findByText("Page 1 of 2");
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("Older check")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("shows an error state with retry", async () => {
    let fail = true;
    mockApi({
      ...signedIn,
      "GET /modules": () => json(200, MODULES),
      [H1]: () => (fail ? json(500, errorBody("internal_error", "An unexpected error occurred.")) : json(200, page([]))),
    });
    const user = userEvent.setup();
    renderApp("/history");
    expect(await screen.findByRole("alert")).toHaveTextContent("An unexpected error occurred.");
    fail = false;
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No history yet")).toBeInTheDocument();
  });
});

const prefs = {
  "GET /meta/preference-options": () => json(200, { unit_systems: ["metric", "imperial"], dietary_preferences: ["vegan"], common_allergens: ["peanut"] }),
  "GET /users/me/preferences": () => json(200, { unit_system: "metric", dietary_preferences: [], allergies: [], updated_at: "x" }),
};

describe("settings", () => {
  it("updates the display name and reflects it across the app", async () => {
    const { calls } = mockApi({
      ...signedIn, ...prefs,
      "PATCH /users/me": ({ body }) => json(200, { ...authBody().user, display_name: (body as { display_name: string }).display_name }),
    });
    const user = userEvent.setup();
    renderApp("/settings");
    const input = await screen.findByLabelText("Display name");
    await user.clear(input);
    await user.type(input, "Asha K");
    await user.click(screen.getByRole("button", { name: "Save profile" }));
    expect(await screen.findByText("Profile updated.")).toBeInTheDocument();
    expect(calls.find((c) => c.key === "PATCH /users/me")?.body).toEqual({ display_name: "Asha K" });
    expect(screen.getAllByText("Asha K").length).toBeGreaterThan(0); // sidebar user name
  });

  it("shows the server's validation message for a bad name", async () => {
    mockApi({
      ...signedIn, ...prefs,
      "PATCH /users/me": () => json(422, errorBody("validation_error", "Request validation failed.", [{ field: "display_name", message: "Display name must not be blank." }])),
    });
    const user = userEvent.setup();
    renderApp("/settings");
    await user.type(await screen.findByLabelText("Display name"), "x");
    await user.click(screen.getByRole("button", { name: "Save profile" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Display name must not be blank.");
  });

  it("checks the new password client-side before calling the API", async () => {
    const { calls } = mockApi({ ...signedIn, ...prefs });
    const user = userEvent.setup();
    renderApp("/settings");
    await user.type(await screen.findByLabelText("Current password"), "old password here");
    await user.type(screen.getByLabelText("New password"), "a new passphrase");
    await user.type(screen.getByLabelText("Confirm new password"), "something different");
    await user.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("do not match");
    expect(calls.some((c) => c.key === "POST /users/me/password")).toBe(false);
  });

  it("changes the password, then signs the user out everywhere", async () => {
    const { calls } = mockApi({
      ...signedIn, ...prefs,
      "POST /users/me/password": () => new Response(null, { status: 204 }),
      "POST /auth/logout": () => new Response(null, { status: 204 }),
    });
    const user = userEvent.setup();
    renderApp("/settings");
    await user.type(await screen.findByLabelText("Current password"), "old password here");
    await user.type(screen.getByLabelText("New password"), "a new passphrase");
    await user.type(screen.getByLabelText("Confirm new password"), "a new passphrase");
    await user.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(calls.find((c) => c.key === "POST /users/me/password")?.body).toEqual({
      current_password: "old password here",
      new_password: "a new passphrase",
    });
  });

  it("shows the server's error for a wrong current password and stays signed in", async () => {
    mockApi({
      ...signedIn, ...prefs,
      "POST /users/me/password": () => json(401, errorBody("invalid_credentials", "Current password is incorrect.")),
    });
    const user = userEvent.setup();
    renderApp("/settings");
    await user.type(await screen.findByLabelText("Current password"), "wrong password");
    await user.type(screen.getByLabelText("New password"), "a new passphrase");
    await user.type(screen.getByLabelText("Confirm new password"), "a new passphrase");
    await user.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Current password is incorrect.");
    expect(screen.getByRole("heading", { name: "Settings" })).toBeInTheDocument();
  });
});

void dashboardRoutes;
