import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MEDIA } from "./food-fixtures";
import {
  DETAIL, FCAPS_NO_VISION, NOTICE, SUMMARY, audit, fpage, freshRoutes,
} from "./freshness-fixtures";
import { errorBody, json, mockApi, renderApp, stubUploadXhr } from "./helpers";

const png = () => new File([new Uint8Array([137, 80, 78, 71])], "berries.png", { type: "image/png" });

async function fillFood(user: ReturnType<typeof userEvent.setup>) {
  await user.type(await screen.findByLabelText("What food is it?"), "Strawberries");
  await user.selectOptions(screen.getByLabelText("Type of food"), "fruit");
}

describe("new freshness check", () => {
  beforeEach(stubUploadXhr);

  it("shows the not-a-verdict notice and requires a food name and type", async () => {
    const { calls } = mockApi(freshRoutes());
    const user = userEvent.setup();
    renderApp("/freshness");
    expect(await screen.findByText(NOTICE)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Get guidance without analysing the photo" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter what food this is.");
    await user.type(screen.getByLabelText("What food is it?"), "Rice");
    await user.click(screen.getByRole("button", { name: "Get guidance without analysing the photo" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose the type of food.");
    expect(calls.some((c) => c.key === "POST /freshness/assessments")).toBe(false);
  });

  it("works with the AI offline: guidance-only, no upload, analyse disabled", async () => {
    const { calls } = mockApi(freshRoutes({
      "GET /freshness/capabilities": () => json(200, FCAPS_NO_VISION),
      "POST /freshness/assessments": () => json(201, DETAIL),
      "GET /freshness/assessments/f1": () => json(200, DETAIL),
      "GET /media/m1/content": () => new Response(new Uint8Array([1]), { headers: { "Content-Type": "image/png" } }),
    }));
    const user = userEvent.setup();
    renderApp("/freshness");
    expect(await screen.findByText(/Photo analysis is not available/)).toHaveTextContent("OLLAMA_ENABLED is not set.");
    expect(screen.getByRole("button", { name: "Analyse photo" })).toBeDisabled();
    await fillFood(user);
    await user.click(screen.getByRole("button", { name: "Get guidance without analysing the photo" }));
    expect(await screen.findByRole("heading", { name: "Guidance" })).toBeInTheDocument();
    const post = calls.find((c) => c.key === "POST /freshness/assessments")!;
    expect(post.body).toMatchObject({ analyze_image: false, media_id: null, food_name: "Strawberries", food_category: "fruit" });
    expect((post.body as { assessed_on: string }).assessed_on).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(calls.some((c) => c.key === "POST /media")).toBe(false);
    expect(post.headers.get("X-Requested-With")).toBe("FoodVerseWeb");
  });

  it("uploads the photo, sends the confirmed food and storage details, then opens the result", async () => {
    const { calls } = mockApi(freshRoutes({
      "POST /media": () => json(201, MEDIA),
      "POST /freshness/assessments": () => json(201, DETAIL),
      "GET /freshness/assessments/f1": () => json(200, DETAIL),
      "GET /media/m1/content": () => new Response(new Uint8Array([1]), { headers: { "Content-Type": "image/png" } }),
    }));
    const user = userEvent.setup();
    renderApp("/freshness");
    await fillFood(user);
    await user.selectOptions(screen.getByLabelText("Where was it kept?"), "fridge");
    await user.type(screen.getByLabelText("How long has it been stored?"), "3");
    await user.selectOptions(screen.getByLabelText("Storage time unit"), "days");
    await user.upload(screen.getByLabelText("Choose a photo"), png());
    await user.click(screen.getByRole("button", { name: "Analyse photo" }));
    expect(await screen.findByRole("heading", { name: "What the image showed" })).toBeInTheDocument();
    const post = calls.find((c) => c.key === "POST /freshness/assessments")!;
    expect(post.body).toMatchObject({
      analyze_image: true, media_id: MEDIA.id, storage_condition: "fridge",
      storage_duration: { amount: 3, unit: "days" },
    });
  });

  it("rejects a non-image file without any request", async () => {
    const { calls } = mockApi(freshRoutes());
    const user = userEvent.setup({ applyAccept: false });
    renderApp("/freshness");
    await user.upload(await screen.findByLabelText("Choose a photo"), new File(["x"], "a.txt", { type: "text/plain" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose a JPEG, PNG or WebP image.");
    expect(calls.some((c) => c.key === "POST /media")).toBe(false);
  });

  it("on a provider error shows the message and retries as guidance-only without re-uploading", async () => {
    let n = 0;
    const { calls } = mockApi(freshRoutes({
      "POST /media": () => json(201, MEDIA),
      "POST /freshness/assessments": ({ body }) => {
        n += 1;
        if ((body as { analyze_image: boolean }).analyze_image) return json(503, errorBody("ai_unavailable", "The vision model is not reachable."));
        return json(201, { ...DETAIL, result: audit({ findings: { ...audit().findings, analysed: false, observations: [] } }) });
      },
      "GET /freshness/assessments/f1": () => json(200, DETAIL),
      "GET /media/m1/content": () => new Response(new Uint8Array([1]), { headers: { "Content-Type": "image/png" } }),
    }));
    const user = userEvent.setup();
    renderApp("/freshness");
    await fillFood(user);
    await user.upload(screen.getByLabelText("Choose a photo"), png());
    await user.click(screen.getByRole("button", { name: "Analyse photo" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The vision model is not reachable.");
    expect(screen.getByText(/could not be analysed right now/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Get guidance without analysing the photo" }));
    await screen.findByRole("heading", { name: "Guidance" });
    expect(n).toBe(2);
    expect(calls.filter((c) => c.key === "POST /media")).toHaveLength(1);
    const retry = calls.filter((c) => c.key === "POST /freshness/assessments")[1];
    expect(retry.body).toMatchObject({ analyze_image: false, media_id: MEDIA.id });
  });

  it("can cancel while waiting and says a finished check may still be saved", async () => {
    mockApi(freshRoutes({
      "POST /media": () => json(201, MEDIA),
      "POST /freshness/assessments": () => new Promise<Response>(() => {}),
    }));
    const user = userEvent.setup();
    renderApp("/freshness");
    await fillFood(user);
    await user.upload(screen.getByLabelText("Choose a photo"), png());
    await user.click(screen.getByRole("button", { name: "Analyse photo" }));
    await user.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/past checks/);
  });
});

describe("freshness detail", () => {
  const routes = (d: unknown = DETAIL, over = {}) => freshRoutes({
    "GET /freshness/assessments/f1": () => json(200, d),
    "GET /media/m1/content": () => new Response(new Uint8Array([1]), { headers: { "Content-Type": "image/png" } }),
    ...over,
  });

  it("separates observation from guidance and never calls anything safe or fresh", async () => {
    mockApi(routes());
    renderApp("/freshness/f1");
    expect(await screen.findByText("Visible concern observed")).toBeInTheDocument();
    const seen = screen.getByRole("heading", { name: "What the image showed" }).closest("section")!;
    const advice = screen.getByRole("heading", { name: "Guidance" }).closest("section")!;
    expect(within(seen).getByText(/Reported by the AI model/)).toBeInTheDocument();
    expect(within(seen).getByText("Grey fuzzy patch")).toBeInTheDocument();
    expect(within(seen).queryByText("Discarding is recommended.")).not.toBeInTheDocument();
    expect(within(advice).getByText(/Not written by the AI model/)).toBeInTheDocument();
    expect(within(advice).getByText("Discarding is recommended.")).toBeInTheDocument();
    expect(within(advice).getByText("Microbes cannot always be seen.")).toBeInTheDocument();
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\bfresh\b|\d+\s?%|score:/i);
    expect(document.querySelector(".badge-ok")).toBeNull();
  });

  it("shows the no-obvious-concern label as neutral, with the caveat", async () => {
    const d = {
      ...DETAIL, label: "no_obvious_visible_concern",
      result: audit({
        findings: { ...audit().findings, observations: [] },
        assessment: { label: "no_obvious_visible_concern", label_text: "No obvious visible concern in this image", inconclusive_reasons: [] },
        advice: { ...audit().advice, level: "general_caution", headline: "Appearance alone cannot show that food is safe." },
      }),
    };
    mockApi(routes(d));
    renderApp("/freshness/f1");
    const badge = await screen.findByText("No obvious visible concern in this image");
    expect(badge.className).not.toMatch(/ok|success|green/);
    expect(screen.getByText("Appearance alone cannot show that food is safe.")).toBeInTheDocument();
  });

  it("explains inconclusive results and shows retake tips and withheld-text notice", async () => {
    const d = {
      ...DETAIL, label: "inconclusive",
      result: audit({
        findings: { ...audit().findings, image_quality: "unusable", observations: [], withheld_text_count: 2 },
        assessment: { label: "inconclusive", label_text: "Inconclusive", inconclusive_reasons: [{ code: "unusable", text: "The image was too unclear to assess." }] },
        advice: { ...audit().advice, level: "use_caution", retake_tips: ["Use bright, even light."] },
      }),
    };
    mockApi(routes(d));
    renderApp("/freshness/f1");
    expect(await screen.findByText("The image was too unclear to assess.")).toBeInTheDocument();
    expect(screen.getByText("Use bright, even light.")).toBeInTheDocument();
    expect(screen.getByText(/2 model comments were withheld/)).toBeInTheDocument();
  });

  it("says nothing was observed when the photo was not analysed", async () => {
    const d = { ...DETAIL, image_analysed: false, media_id: null, result: audit({
      findings: { ...audit().findings, analysed: false, observations: [], image_quality: null },
      provider: null,
    }) };
    mockApi(routes(d));
    renderApp("/freshness/f1");
    expect(await screen.findByText(/No image analysis was run/)).toBeInTheDocument();
    expect(screen.getByText(/No AI model was used/)).toBeInTheDocument();
  });

  it("deletes after confirmation", async () => {
    const { calls } = mockApi(routes(DETAIL, {
      "DELETE /freshness/assessments/f1": () => new Response(null, { status: 204 }),
      "GET /freshness/assessments?page=1&page_size=10": () => json(200, fpage([])),
    }));
    const user = userEvent.setup();
    renderApp("/freshness/f1");
    await user.click(await screen.findByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(calls.some((c) => c.key === "DELETE /freshness/assessments/f1")).toBe(true));
    expect(await screen.findByText("No freshness checks yet")).toBeInTheDocument();
  });

  it("shows a not-found state", async () => {
    mockApi(freshRoutes({ "GET /freshness/assessments/zzz": () => json(404, errorBody("not_found", "Not found")) }));
    renderApp("/freshness/zzz");
    expect(await screen.findByText("Check not found")).toBeInTheDocument();
  });
});

describe("freshness history", () => {
  it("shows an empty state", async () => {
    mockApi(freshRoutes({ "GET /freshness/assessments?page=1&page_size=10": () => json(200, fpage([])) }));
    renderApp("/freshness/history");
    expect(await screen.findByText("No freshness checks yet")).toBeInTheDocument();
  });

  it("lists checks with labels, links to detail and filters by result", async () => {
    const { calls } = mockApi(freshRoutes({
      "GET /freshness/assessments?page=1&page_size=10": () => json(200, fpage([SUMMARY])),
      "GET /freshness/assessments?page=1&page_size=10&label=inconclusive": () => json(200, fpage([])),
    }));
    const user = userEvent.setup();
    renderApp("/freshness/history");
    const link = await screen.findByRole("link", { name: "Strawberries" });
    expect(link).toHaveAttribute("href", "/freshness/f1");
    expect(within(screen.getByRole("list")).getByText("Visible concern observed")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Result"), "inconclusive");
    expect(await screen.findByText("No checks with that result")).toBeInTheDocument();
    expect(calls.some((c) => c.key.endsWith("label=inconclusive"))).toBe(true);
  });

  it("deletes a row after confirmation", async () => {
    let gone = false;
    const { calls } = mockApi(freshRoutes({
      "GET /freshness/assessments?page=1&page_size=10": () => json(200, fpage(gone ? [] : [SUMMARY])),
      "DELETE /freshness/assessments/f1": () => { gone = true; return new Response(null, { status: 204 }); },
    }));
    const user = userEvent.setup();
    renderApp("/freshness/history");
    await user.click(await screen.findByRole("button", { name: "Delete check for Strawberries" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("No freshness checks yet")).toBeInTheDocument();
    expect(calls.some((c) => c.key === "DELETE /freshness/assessments/f1")).toBe(true);
  });
});
