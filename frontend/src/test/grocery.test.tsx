import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GROCERY, PLAN, plannerRoutes } from "./planner-fixtures";
import { json, mockApi, renderApp } from "./helpers";

describe("grocery list", () => {
  it("lists an empty state", async () => {
    mockApi(plannerRoutes({
      "GET /grocery-lists?page=1&page_size=10": () =>
        json(200, { items: [], total: 0, page: 1, page_size: 10, pages: 0 }),
    }));
    renderApp("/grocery");
    expect(await screen.findByText("No grocery lists yet")).toBeInTheDocument();
  });

  it("edits quantity and saves through the API", async () => {
    const { calls } = mockApi(plannerRoutes({
      "GET /grocery-lists/gl1": () => json(200, GROCERY),
      "PUT /grocery-lists/gl1": ({ body }) => json(200, { ...GROCERY, revision: 2, ...(body as object) }),
    }));
    const user = userEvent.setup();
    renderApp("/grocery/gl1");
    const qty = await screen.findByLabelText("Quantity");
    await user.clear(qty);
    await user.type(qty, "750");
    await user.click(screen.getByRole("button", { name: "Save list" }));
    const put = calls.find((c) => c.key === "PUT /grocery-lists/gl1");
    expect(put?.body).toMatchObject({
      expected_revision: 1,
      items: [expect.objectContaining({ name: "rice", quantity: 750, unit: "g" })],
    });
  });

  it("checks off an item and saves", async () => {
    const { calls } = mockApi(plannerRoutes({
      "GET /grocery-lists/gl1": () => json(200, GROCERY),
      "PUT /grocery-lists/gl1": ({ body }) => json(200, { ...GROCERY, revision: 2, ...(body as object) }),
    }));
    const user = userEvent.setup();
    renderApp("/grocery/gl1");
    await user.click(await screen.findByLabelText("rice purchased"));
    await user.click(screen.getByRole("button", { name: "Save list" }));
    const put = calls.find((c) => c.key === "PUT /grocery-lists/gl1");
    expect((put!.body as { items: { checked: boolean }[] }).items[0].checked).toBe(true);
  });

  it("creates a grocery list from a plan", async () => {
    const { calls } = mockApi(plannerRoutes({
      "GET /meal-plans/plan1": () => json(200, PLAN),
      "POST /grocery-lists": () => json(201, GROCERY),
      "GET /grocery-lists/gl1": () => json(200, GROCERY),
    }));
    const user = userEvent.setup();
    renderApp("/planner/plan1");
    await user.click(await screen.findByRole("button", { name: "Create grocery list" }));
    expect(await screen.findByRole("heading", { name: GROCERY.title })).toBeInTheDocument();
    const post = calls.find((c) => c.key === "POST /grocery-lists");
    expect(post?.body).toEqual({ plan_id: "plan1", title: null });
  });
});

void within;