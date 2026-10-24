import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { authBody, errorBody, json, mockApi, renderApp } from "./helpers";

const options = {
  unit_systems: ["metric", "imperial"],
  dietary_preferences: ["vegetarian", "vegan", "gluten_free"],
  common_allergens: ["peanut", "milk"],
};
const prefs = { unit_system: "metric", dietary_preferences: [], allergies: [], updated_at: "x" };

describe("preferences page", () => {
  it("loads preferences and saves changes through the API", async () => {
    const { calls } = mockApi({
      "POST /auth/refresh": () => json(200, authBody()),
      "GET /meta/preference-options": () => json(200, options),
      "GET /users/me/preferences": () => json(200, prefs),
      "PUT /users/me/preferences": ({ body }) =>
        json(200, { ...(body as object), updated_at: "y" }),
    });
    const user = userEvent.setup();
    renderApp("/preferences");

    await user.click(await screen.findByLabelText("Imperial"));
    await user.click(screen.getByLabelText("Vegan"));
    await user.type(screen.getByLabelText("Add an allergy"), "  Tree   Nut ");
    await user.click(screen.getByRole("button", { name: "Add" }));
    await user.click(screen.getByRole("button", { name: "peanut" })); // suggestion chip
    await user.click(screen.getByRole("button", { name: "Save preferences" }));

    expect(await screen.findByText("Preferences saved.")).toBeInTheDocument();
    const put = calls.find((c) => c.key === "PUT /users/me/preferences");
    expect(put?.body).toEqual({
      unit_system: "imperial",
      dietary_preferences: ["vegan"],
      allergies: ["tree nut", "peanut"],
    });
    expect(put?.headers.get("Authorization")).toBe("Bearer access-1");
  });

  it("shows server-side validation errors", async () => {
    mockApi({
      "POST /auth/refresh": () => json(200, authBody()),
      "GET /meta/preference-options": () => json(200, options),
      "GET /users/me/preferences": () => json(200, prefs),
      "PUT /users/me/preferences": () =>
        json(422, errorBody("validation_error", "Request validation failed.", [
          { field: "allergies.0", message: "Value error, bad allergy" },
        ])),
    });
    const user = userEvent.setup();
    renderApp("/preferences");
    await user.click(await screen.findByRole("button", { name: "Save preferences" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("allergies.0: Value error, bad allergy");
  });
});
