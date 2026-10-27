import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  CALC, CAPS_NO_VISION, CAPS_READY, MEAL, MEDIA, SCAN, SEARCH, foodRoutes,
} from "./food-fixtures";
import { errorBody, json, mockApi, renderApp, stubUploadXhr } from "./helpers";

const png = () => new File([new Uint8Array([137, 80, 78, 71])], "plate.png", { type: "image/png" });

/** Routes for the happy path from upload to saved meal. */
function happyRoutes(over = {}) {
  return foodRoutes({
    "POST /media": () => json(201, MEDIA),
    "POST /food/scan": () => json(200, SCAN),
    "GET /nutrition/search?q=Apple": () => json(200, SEARCH),
    "POST /food/calculate": () => json(200, CALC),
    "POST /meals": () => json(201, MEAL),
    "GET /meals/meal1": () => json(200, MEAL),
    "GET /media/m1/content": () => new Response(new Uint8Array([1]), { headers: { "Content-Type": "image/png" } }),
    ...over,
  });
}

async function analysePhoto(user: ReturnType<typeof userEvent.setup>) {
  await user.upload(await screen.findByLabelText("Choose a photo"), png());
  await user.click(screen.getByRole("button", { name: "Analyse photo" }));
}

describe("photo step", () => {
  beforeEach(stubUploadXhr);

  it("previews the chosen photo and lets the user replace or remove it", async () => {
    mockApi(foodRoutes());
    const user = userEvent.setup();
    renderApp("/food");
    expect(await screen.findByText("No photo selected.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyse photo" })).toBeDisabled();

    await user.upload(screen.getByLabelText("Choose a photo"), png());
    expect(screen.getByAltText("Preview of the selected photo")).toBeInTheDocument();
    expect(screen.getByText(/plate.png/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Replace photo" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Remove photo" }));
    expect(screen.queryByAltText("Preview of the selected photo")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyse photo" })).toBeDisabled();
  });

  it("offers a camera input that requests the rear camera where supported", async () => {
    mockApi(foodRoutes());
    renderApp("/food");
    const camera = await screen.findByLabelText("Take a photo");
    expect(camera).toHaveAttribute("capture", "environment");
    expect(camera).toHaveAttribute("accept", "image/*");
  });

  it("rejects unsupported and empty files without any request", async () => {
    const { calls } = mockApi(foodRoutes());
    const user = userEvent.setup({ applyAccept: false });
    renderApp("/food");
    const input = await screen.findByLabelText("Choose a photo");
    await user.upload(input, new File(["hi"], "notes.txt", { type: "text/plain" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose a JPEG, PNG or WebP image.");
    await user.upload(input, new File([], "empty.png", { type: "image/png" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That file is empty.");
    expect(calls.some((c) => c.key === "POST /media" || c.key === "POST /food/scan")).toBe(false);
  });

  it("explains when photo recognition is not set up and still allows manual entry", async () => {
    mockApi(foodRoutes({ "GET /food/capabilities": () => json(200, CAPS_NO_VISION) }));
    const user = userEvent.setup();
    renderApp("/food");
    expect(await screen.findByText(/Photo recognition is not available/)).toHaveTextContent("OLLAMA_ENABLED is not set.");
    await user.upload(screen.getByLabelText("Choose a photo"), png());
    expect(screen.getByRole("button", { name: "Analyse photo" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Enter foods without a photo" }));
    expect(await screen.findByRole("heading", { name: "Check your meal" })).toBeInTheDocument();
    expect(screen.getByLabelText("Food 1")).toHaveValue("");
  });

  it("warns before a photo is sent to an external provider", async () => {
    mockApi(foodRoutes({ "GET /food/capabilities": () => json(200, { ...CAPS_READY, vision: { ...CAPS_READY.vision, provider: "openai_compatible", external: true } }) }));
    renderApp("/food");
    expect(await screen.findByText(/sent to an external service/)).toBeInTheDocument();
  });

  it("shows determinate upload progress, then scan progress with a cancel button", async () => {
    let release: (r: Response) => void = () => {};
    const { calls } = mockApi(happyRoutes({ "POST /media": () => new Promise<Response>((r) => { release = r; }) }));
    const user = userEvent.setup();
    renderApp("/food");
    await analysePhoto(user);
    expect(await screen.findByText("Uploading… 50%")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Upload progress" })).toHaveAttribute("value", "0.5");
    release(json(201, MEDIA));
    expect(await screen.findByRole("heading", { name: "Check your meal" })).toBeInTheDocument();
    expect(calls.map((c) => c.key)).toEqual(expect.arrayContaining(["POST /media", "POST /food/scan"]));
    expect(calls.find((c) => c.key === "POST /food/scan")?.body).toEqual({ media_id: "m1" });
    expect(calls.find((c) => c.key === "POST /media")?.headers.get("Authorization")).toBe("Bearer access-1");
  });

  it("can cancel a slow analysis without showing an error", async () => {
    mockApi(happyRoutes({
      "POST /food/scan": () => new Promise<Response>(() => {}), // never answers
    }));
    const user = userEvent.setup();
    renderApp("/food");
    await analysePhoto(user);
    expect(await screen.findByText(/Analysing the photo/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(await screen.findByRole("button", { name: "Analyse photo" })).toBeEnabled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows the server's reason when the model fails and retries without re-uploading", async () => {
    let scans = 0;
    const { calls } = mockApi(happyRoutes({
      "POST /food/scan": () => {
        scans += 1;
        return scans === 1 ? json(504, errorBody("vision_timeout", "The vision model took too long.")) : json(200, SCAN);
      },
    }));
    const user = userEvent.setup();
    renderApp("/food");
    await analysePhoto(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("The vision model took too long.");
    await user.click(screen.getByRole("button", { name: "Try analysing again" }));
    expect(await screen.findByRole("heading", { name: "Check your meal" })).toBeInTheDocument();
    expect(calls.filter((c) => c.key === "POST /media")).toHaveLength(1); // the photo was uploaded once
    expect(calls.filter((c) => c.key === "POST /food/scan")).toHaveLength(2);
  });

  it("shows upload validation errors from the server", async () => {
    mockApi(happyRoutes({ "POST /media": () => json(422, errorBody("invalid_image", "The file could not be decoded as a valid image.")) }));
    const user = userEvent.setup();
    renderApp("/food");
    await analysePhoto(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be decoded");
    expect(screen.getByRole("button", { name: "Analyse photo" })).toBeEnabled();
  });
});

describe("confirm, calculate and save", () => {
  beforeEach(stubUploadXhr);

  it("labels model output as suggestions and lets the user rename, add and remove foods", async () => {
    mockApi(happyRoutes());
    const user = userEvent.setup();
    renderApp("/food");
    await analysePhoto(user);
    expect(await screen.findByText(/Check every item/)).toBeInTheDocument();
    expect(screen.getByText(/Model-generated suggestions/)).toBeInTheDocument();
    expect(screen.getByText(/the model was unsure/)).toBeInTheDocument();
    expect(screen.queryByText(/confidence/i)).not.toBeInTheDocument(); // no invented scores

    // the model's alternative is one click away
    await user.click(screen.getByRole("button", { name: "Pear" }));
    expect(screen.getByLabelText("Food 1")).toHaveValue("Pear");

    await user.clear(screen.getByLabelText("Food 2"));
    await user.type(screen.getByLabelText("Food 2"), "Brown rice");
    await user.click(screen.getByRole("button", { name: "Add a food" }));
    expect(screen.getByLabelText("Food 3")).toHaveValue("");
    await user.click(screen.getByRole("button", { name: "Remove food 3" }));
    expect(screen.queryByLabelText("Food 3")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Remove Pear" }));
    expect(screen.getAllByLabelText(/^Food \d$/)).toHaveLength(1);
  });

  it("finds nutrition data, takes a weight, calculates from the server and saves", async () => {
    const { calls } = mockApi(happyRoutes());
    const user = userEvent.setup();
    renderApp("/food");
    await analysePhoto(user);
    await screen.findByLabelText("Food 1");

    await user.click(screen.getByRole("button", { name: "Find nutrition data for Apple" }));
    await user.click(await screen.findByRole("button", { name: "Search" }));
    const option = await screen.findByText("Apples, raw, with skin");
    expect(option.closest("li")).toHaveTextContent("Per 100 g: 52 kcal, 0.26 g protein");
    await user.click(screen.getByRole("button", { name: "Use Apples, raw, with skin" }));
    expect(screen.getByText(/USDA FoodData Central/)).toBeInTheDocument();

    await user.type(screen.getAllByLabelText("Weight of Apple")[0], "150");
    expect(screen.queryByText("Meal total")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Calculate nutrition" }));

    const totals = await screen.findByRole("table", { name: "Meal total" });
    expect(within(totals).getByText("78 kcal")).toBeInTheDocument();
    expect(within(totals).getAllByText(/Partial: excludes Rice/).length).toBeGreaterThan(0);
    expect(within(totals).queryByText("Fibre")).not.toBeInTheDocument(); // extras appear only when a source supplied them
    expect(screen.getByText(/at least one food is missing data/)).toBeInTheDocument();
    expect(screen.getByText(/ID 171688/)).toBeInTheDocument();
    expect(screen.getByText(/per 100 g, as published by each source/)).toBeInTheDocument();
    expect(screen.getByText(/Not reported by source/)).toBeInTheDocument(); // apple fat, per item
    expect(within(totals).getByText("Not available")).toBeInTheDocument(); // total fat: no food reported it
    expect(screen.getByText(/No nutrition source was chosen/)).toBeInTheDocument();

    const calc = calls.find((c) => c.key === "POST /food/calculate")?.body as Record<string, unknown>;
    expect(calc.scan_ref).toBe("scan-ref-1");
    expect(calc.items).toEqual([
      { name: "Apple", observed_id: 0, food_ref: "food-ref-1", portion: { kind: "weight", amount: 150, unit: "g" } },
      { name: "Rice", observed_id: 1 },
    ]);
    expect(JSON.stringify(calc)).not.toMatch(/kcal|per_100g|energy/); // numbers never come from the browser

    await user.selectOptions(screen.getByLabelText("Meal"), "dinner");
    await user.type(screen.getByLabelText(/Notes/), "with tea");
    await user.click(screen.getByRole("button", { name: "Save meal" }));
    expect(await screen.findByRole("heading", { name: "Apple, Rice" })).toBeInTheDocument();
    expect(await screen.findByText("Meal saved.")).toBeInTheDocument();

    const save = calls.find((c) => c.key === "POST /meals")?.body as Record<string, unknown>;
    expect(save).toMatchObject({ category: "dinner", notes: "with tea", scan_ref: "scan-ref-1", media_id: "m1" });
    expect(typeof save.eaten_at).toBe("string");
    expect(JSON.stringify(save)).not.toMatch(/totals|energy_kcal/);
  });

  it("hides stale results as soon as anything is edited", async () => {
    mockApi(happyRoutes());
    const user = userEvent.setup();
    renderApp("/food");
    await analysePhoto(user);
    await screen.findByLabelText("Food 1");
    await user.click(screen.getByRole("button", { name: "Calculate nutrition" }));
    await screen.findByRole("table", { name: "Meal total" });
    expect(screen.getByRole("button", { name: "Save meal" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Food 1"), "s");
    expect(screen.queryByRole("table", { name: "Meal total" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save meal" })).not.toBeInTheDocument();
  });

  it("blocks an invalid portion locally with a clear message", async () => {
    const { calls } = mockApi(happyRoutes());
    const user = userEvent.setup();
    renderApp("/food");
    await analysePhoto(user);
    await screen.findByLabelText("Food 1");
    await user.type(screen.getAllByLabelText("Weight of Apple")[0], "abc");
    await user.click(screen.getByRole("button", { name: "Calculate nutrition" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Apple: Enter a weight greater than zero.");
    expect(calls.some((c) => c.key === "POST /food/calculate")).toBe(false);
  });

  it("supports an estimated range and sends it as a range", async () => {
    const { calls } = mockApi(happyRoutes());
    const user = userEvent.setup();
    renderApp("/food");
    await analysePhoto(user);
    await screen.findByLabelText("Food 1");
    await user.selectOptions(screen.getAllByLabelText("Portion type")[0], "range");
    expect(screen.getByText(/shown as a range and marked as an estimate/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Smallest likely weight of Apple"), "100");
    await user.type(screen.getByLabelText("Largest likely weight of Apple"), "200");
    await user.click(screen.getByRole("button", { name: "Calculate nutrition" }));
    await screen.findByRole("table", { name: "Meal total" });
    const body = calls.find((c) => c.key === "POST /food/calculate")?.body as { items: { portion: unknown }[] };
    expect(body.items[0].portion).toEqual({ kind: "range", min_amount: 100, max_amount: 200, unit: "g" });
  });

  it("disables servings unless the data source gives a serving weight", async () => {
    mockApi(happyRoutes());
    const user = userEvent.setup();
    renderApp("/food");
    await analysePhoto(user);
    await screen.findByLabelText("Food 1");
    const option = screen.getAllByRole("option", { name: /Servings/ })[0];
    expect(option).toBeDisabled();
    expect(option).toHaveTextContent("needs a serving size from the data source");
  });

  it("shows a reason, not a number, when no nutrition source is reachable", async () => {
    mockApi(happyRoutes({
      "GET /nutrition/search?q=Apple": () => json(200, {
        query: "Apple", results: [],
        sources: [{ source: "usda_fdc", label: "USDA FoodData Central", status: "rate_limited", message: "USDA is rate limiting this key." }],
      }),
    }));
    const user = userEvent.setup();
    renderApp("/food");
    await analysePhoto(user);
    await screen.findByLabelText("Food 1");
    await user.click(screen.getByRole("button", { name: "Find nutrition data for Apple" }));
    await user.click(await screen.findByRole("button", { name: "Search" }));
    expect(await screen.findByText(/USDA is rate limiting this key/)).toBeInTheDocument();
    expect(screen.getByText(/Nothing is guessed/)).toBeInTheDocument();
  });

  it("shows the server's message when saving fails and keeps the form", async () => {
    mockApi(happyRoutes({ "POST /meals": () => json(422, errorBody("invalid_reference", "This reference is invalid or has expired.")) }));
    const user = userEvent.setup();
    renderApp("/food");
    await analysePhoto(user);
    await screen.findByLabelText("Food 1");
    await user.click(screen.getByRole("button", { name: "Calculate nutrition" }));
    await user.click(await screen.findByRole("button", { name: "Save meal" }));
    expect(await screen.findByText(/invalid or has expired/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save meal" })).toBeEnabled();
  });

  it("warns when no nutrition source is configured on the server", async () => {
    mockApi(happyRoutes({
      "GET /food/capabilities": () => json(200, { ...CAPS_READY, nutrition: { ...CAPS_READY.nutrition, any_configured: false } }),
    }));
    const user = userEvent.setup();
    renderApp("/food");
    await analysePhoto(user);
    expect(await screen.findByText(/No nutrition data source is set up/)).toBeInTheDocument();
  });

  it("asks before discarding work when starting over", async () => {
    mockApi(happyRoutes());
    const user = userEvent.setup();
    renderApp("/food");
    await analysePhoto(user);
    await screen.findByLabelText("Food 1");
    await user.click(screen.getByRole("button", { name: "Start over" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.getByLabelText("Food 1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start over" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Start over" }));
    expect(await screen.findByRole("button", { name: "Analyse photo" })).toBeInTheDocument();
  });

  it("an empty scan result is stated plainly", async () => {
    mockApi(happyRoutes({ "POST /food/scan": () => json(200, { ...SCAN, items: [] }) }));
    const user = userEvent.setup();
    renderApp("/food");
    await analysePhoto(user);
    expect(await screen.findByText(/did not find any food in this photo/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Calculate nutrition" })).toBeDisabled();
  });
});

describe("module entry points", () => {
  it("links an available module to its working page", async () => {
    mockApi({
      ...foodRoutes(),
      "GET /modules": () => json(200, [{ key: "food_recognition", title: "Food recognition", description: "d", available: true }]),
    });
    renderApp("/modules");
    const link = await screen.findByRole("link", { name: "Food recognition" });
    expect(link).toHaveAttribute("href", "/food");
  });
});

