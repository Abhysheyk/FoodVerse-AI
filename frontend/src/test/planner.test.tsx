import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  BLANK, CAPS_OFFLINE, PLAN, plannerRoutes,
} from "./planner-fixtures";
import { errorBody, json, mockApi, renderApp } from "./helpers";

describe("planner page", () => {
  it("shows an empty state and a fallback message when generation is unconfigured", async () => {
    mockApi(plannerRoutes({ "GET /meal-plans/capabilities": () => json(200, CAPS_OFFLINE) }));
    renderApp("/planner");
    expect(await screen.findByText("No plans yet")).toBeInTheDocument();
    expect(await screen.findByText(/Meal plan generation is not configured/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate with AI" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Create blank plan" })).toBeEnabled();
  });

  it("creates a blank plan and navigates to it", async () => {
    const { calls } = mockApi(plannerRoutes({
      "POST /meal-plans/blank": () => json(201, BLANK),
      "GET /meal-plans/plan1": () => json(200, BLANK),
    }));
    const user = userEvent.setup();
    renderApp("/planner");
    await user.click(await screen.findByRole("button", { name: "Create blank plan" }));
    expect(await screen.findByRole("heading", { name: "Blank plan" })).toBeInTheDocument();
    const post = calls.find((c) => c.key === "POST /meal-plans/blank");
    expect(post?.body).toMatchObject({ week_start_date: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/) });
    expect(post?.headers.get("X-Requested-With")).toBe("FoodVerseWeb");
  });

  it("warns before sending the prompt externally", async () => {
    mockApi(plannerRoutes());
    renderApp("/planner");
    expect(await screen.findByText(/sent to an external AI service/)).toBeInTheDocument();
  });

  it("surfaces a constraint violation with a clear message and no plan row", async () => {
    mockApi(plannerRoutes({
      "POST /meal-plans/generate": () => json(422, errorBody(
        "meal_plan_constraint_violation",
        "The generated plan broke a hard constraint (allergy, exclusion or dietary pattern). Nothing was saved.",
      )),
    }));
    const user = userEvent.setup();
    renderApp("/planner");
    await user.click(await screen.findByRole("button", { name: "Generate with AI" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/broke a hard constraint/);
  });
});

describe("plan detail editing", () => {
  it("adds a meal through the editor dialog and saves the whole plan", async () => {
    let current = PLAN;
    const { calls } = mockApi(plannerRoutes({
      "GET /meal-plans/plan1": () => json(200, current),
      "PUT /meal-plans/plan1": ({ body }) => {
        const b = body as { days: unknown[] };
        current = { ...PLAN, revision: 2, plan: { schema_version: 1, days: b.days as never[], notes: null } };
        return json(200, current);
      },
    }));
    const user = userEvent.setup();
    renderApp("/planner/plan1");
    await screen.findByRole("heading", { name: "Test plan" });

    // Monday has 1 meal; add another.
    const monday = await screen.findByRole("heading", { level: 2, name: /^Monday/ });
    const card = monday.closest("section")!;
    await user.click(within(card).getByRole("button", { name: "Add meal" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Title"), "Rice bowl");
    await user.click(within(dialog).getByRole("button", { name: "Add ingredient" }));
    await user.type(within(dialog).getByLabelText("Ingredient name"), "rice");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));

    const put = calls.find((c) => c.key === "PUT /meal-plans/plan1");
    expect(put).toBeTruthy();
    const body = put!.body as { expected_revision: number; days: { meals: { title: string }[] }[] };
    expect(body.expected_revision).toBe(1);
    expect(body.days[0].meals.some((m) => m.title === "Rice bowl")).toBe(true);
  });

  it("shows a revision conflict", async () => {
    mockApi(plannerRoutes({
      "GET /meal-plans/plan1": () => json(200, PLAN),
      "PUT /meal-plans/plan1": () => json(409, errorBody(
        "meal_plan_revision_conflict",
        "This plan was changed somewhere else. Reload it and try again.",
      )),
    }));
    const user = userEvent.setup();
    renderApp("/planner/plan1");
    await screen.findByRole("heading", { name: "Test plan" });
    // Try to add a meal — this triggers a save.
    const card = (await screen.findByRole("heading", { level: 2, name: /^Monday/ }))
      .closest("section")!;
    await user.click(within(card).getByRole("button", { name: "Add meal" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Title"), "x");
    await user.click(within(dialog).getByRole("button", { name: "Add ingredient" }));
    await user.type(within(dialog).getByLabelText("Ingredient name"), "y");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/changed somewhere else/);
  });

  it("requests an estimate and displays partial-day warnings", async () => {
    const est = {
      ...PLAN, estimated_at: "2026-11-01T13:00:00Z",
      estimate: {
        method: "best_effort_ingredient_lookup",
        unit_basis: "per 100 g", generated_at: "2026-11-01T13:00:00Z",
        days: PLAN.plan.days.map((d) => ({
          day_date: d.day_date, kcal_low: 130, kcal_high: 130,
          complete: false, missing_ingredients: [],
          meals: [{ meal: "lunch", title: "x", kcal_low: 130, kcal_high: 130, complete: false, missing_ingredients: [], ingredient_estimates: [] }],
        })),
        warnings: ["some_ingredients_unestimated"],
        notes: "Estimates only.",
      },
    };
    mockApi(plannerRoutes({
      "GET /meal-plans/plan1": () => json(200, est),
      "POST /meal-plans/plan1/estimate": () => json(200, est),
    }));
    renderApp("/planner/plan1");
    const matches = await screen.findAllByText(/130 kcal/);
    expect(matches.length).toBeGreaterThan(0);
    expect(screen.getByText(/some_ingredients_unestimated/)).toBeInTheDocument();
  });

  it("deletes the plan after confirmation and returns to the list", async () => {
    const { calls } = mockApi(plannerRoutes({
      "GET /meal-plans/plan1": () => json(200, PLAN),
      "DELETE /meal-plans/plan1": () => new Response(null, { status: 204 }),
    }));
    const user = userEvent.setup();
    renderApp("/planner/plan1");
    await user.click(await screen.findByRole("button", { name: "Delete" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("No plans yet")).toBeInTheDocument();
    expect(calls.some((c) => c.key === "DELETE /meal-plans/plan1")).toBe(true);
  });
});