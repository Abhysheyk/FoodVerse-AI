import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { json, mockApi, renderApp } from "./helpers";
import { USER } from "./planner-fixtures";

const signedIn = {
  "POST /auth/refresh": () => json(200, {
    access_token: "access-1", token_type: "bearer", expires_in: 900, user: USER,
  }),
};

const EMPTY_TARGET = {
  calories_min: null, calories_max: null, protein_g_min: null,
  carbs_g_min: null, fat_g_min: null, fiber_g_min: null, notes: null,
};

function tracking(daysWithData: number, kcal = 1500) {
  const today = new Date();
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(today);
    d.setDate(d.getDate() - (6 - i));
    const iso = d.toISOString().slice(0, 10);
    const data = i < daysWithData;
    return {
      date: iso, meals_logged: data ? 2 : 0,
      kcal_low: data ? kcal : 0, kcal_high: data ? kcal : 0, complete: data,
    };
  });
  return {
    range: { from: days[0].date, to: days[6].date },
    target: null, target_kcal: null, days,
    days_with_data: daysWithData,
    chart_available: daysWithData >= 3,
    note: "Only consumed meals are shown.",
  };
}

describe("nutrition tracking page", () => {
  it("shows a chart only when 3+ days have data", async () => {
    mockApi({
      ...signedIn,
      "GET /users/me/nutrition-target": () => json(200, EMPTY_TARGET),
      "GET /users/me/nutrition-target/tracking*": () => json(200, tracking(2)),
    });
    renderApp("/nutrition");
    expect(await screen.findByText(/Charts appear once at least 3 days/)).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /Calories consumed/ })).not.toBeInTheDocument();
  });

  it("renders the chart when 3+ days have data", async () => {
    mockApi({
      ...signedIn,
      "GET /users/me/nutrition-target": () => json(200, EMPTY_TARGET),
      "GET /users/me/nutrition-target/tracking*": () => json(200, tracking(4)),
    });
    renderApp("/nutrition");
    expect(await screen.findByRole("img", { name: /Calories consumed/ })).toBeInTheDocument();
  });

  it("shows a clear empty state when no meals are logged", async () => {
    mockApi({
      ...signedIn,
      "GET /users/me/nutrition-target": () => json(200, EMPTY_TARGET),
      "GET /users/me/nutrition-target/tracking*": () => json(200, tracking(0)),
    });
    renderApp("/nutrition");
    expect(await screen.findByText("No consumed meals in this range")).toBeInTheDocument();
  });

  it("saves a user-set target", async () => {
    const { calls } = mockApi({
      ...signedIn,
      "GET /users/me/nutrition-target": () => json(200, EMPTY_TARGET),
      "PUT /users/me/nutrition-target": ({ body }) => json(200, body),
      "GET /users/me/nutrition-target/tracking*": () => json(200, tracking(0)),
    });
    const user = userEvent.setup();
    renderApp("/nutrition");
    await user.click(await screen.findByRole("button", { name: "Set a target" }));
    await user.type(screen.getByLabelText("Calories (min)"), "1800");
    await user.type(screen.getByLabelText("Calories (max)"), "2200");
    await user.click(screen.getByRole("button", { name: "Save target" }));
    expect(await screen.findByText("Target saved.")).toBeInTheDocument();
    const put = calls.find((c) => c.key === "PUT /users/me/nutrition-target");
    expect(put?.body).toMatchObject({ calories_min: 1800, calories_max: 2200 });
  });

  it("clears a target", async () => {
    const { calls } = mockApi({
      ...signedIn,
      "GET /users/me/nutrition-target*": () => json(200, {
        ...EMPTY_TARGET, calories_min: 1800, calories_max: 2200,
      }),
      "DELETE /users/me/nutrition-target": () => new Response(null, { status: 204 }),
      "GET /users/me/nutrition-target/tracking*": () => json(200, tracking(0)),
    });
    const user = userEvent.setup();
    renderApp("/nutrition");
    await user.click(await screen.findByRole("button", { name: "Clear target" }));
    expect(calls.some((c) => c.key === "DELETE /users/me/nutrition-target")).toBe(true);
  });
});