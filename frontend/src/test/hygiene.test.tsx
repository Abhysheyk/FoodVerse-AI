import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MEDIA } from "./food-fixtures";
import type { HygieneDetail } from "../api/types";
import { DETAIL, LIST_PAGE, hygieneRoutes } from "./hygiene-fixtures";
import { errorBody, json, mockApi, renderApp, stubUploadXhr } from "./helpers";

const png = (n = "kitchen.png") => new File([new Uint8Array([137, 80, 78, 71])], n, { type: "image/png" });

describe("create inspection", () => {
  beforeEach(stubUploadXhr);

  it("requires a name and at least one photo", async () => {
    const { calls } = mockApi(hygieneRoutes());
    const user = userEvent.setup();
    renderApp("/hygiene");
    expect(await screen.findByRole("heading", { name: "Kitchen hygiene inspection" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Create draft inspection/ })).toBeDisabled();
    await user.upload(screen.getByLabelText("Add photos"), png());
    await user.type(screen.getByLabelText("Kitchen or location name"), "Main kitchen");
    await user.click(screen.getByRole("button", { name: /Create draft inspection/ }));
    await waitFor(() => expect(calls.some((c) => c.key === "POST /hygiene/inspections")).toBe(true));
    const create = calls.find((c) => c.key === "POST /hygiene/inspections")!.body as Record<string, unknown>;
    expect(create).toMatchObject({ location_name: "Main kitchen", media_ids: [MEDIA.id] });
    expect(calls.some((c) => c.key === "POST /media")).toBe(true);
  });

  it("shows the disclosure text before the user even starts", async () => {
    mockApi(hygieneRoutes());
    renderApp("/hygiene");
    expect(await screen.findByText(/never safety, compliance, or pathogen absence/i)).toBeInTheDocument();
  });

  it("rejects an unsupported photo without making any request", async () => {
    const { calls } = mockApi(hygieneRoutes());
    const user = userEvent.setup({ applyAccept: false });
    renderApp("/hygiene");
    await user.upload(await screen.findByLabelText("Add photos"), new File(["hi"], "a.txt", { type: "text/plain" }));
    expect(await screen.findByText(/Only JPEG, PNG and WebP/)).toBeInTheDocument();
    expect(calls.some((c) => c.key === "POST /media")).toBe(false);
  });
});

describe("detail", () => {
  const routes = (over = {}) => hygieneRoutes({
    "GET /hygiene/inspections/i1": () => json(200, DETAIL),
    ...over,
  });

  it("shows findings with their source labels and disclosures", async () => {
    mockApi(routes());
    renderApp("/hygiene/i1");
    expect(await screen.findByRole("heading", { name: "Main kitchen" })).toBeInTheDocument();
    expect(screen.getByText("Greasy film on the cutting board")).toBeInTheDocument();
    expect(screen.getByText(/Model observation/)).toBeInTheDocument();
    expect(screen.getByText(/Clean and sanitize/)).toBeInTheDocument();
    expect(screen.getByText(/Photos cannot confirm absence of pathogens/)).toBeInTheDocument();
    expect(screen.getByText(/Pathogen presence cannot be established/)).toBeInTheDocument();
    expect(screen.queryByText(/compliant/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/hygiene score/i)).not.toBeInTheDocument();
  });

  it("can run analysis from a draft", async () => {
    const { calls } = mockApi(routes({
      "POST /hygiene/inspections/i1/analyze": () => json(200, DETAIL),
    }));
    const user = userEvent.setup();
    renderApp("/hygiene/i1");
    await user.click(await screen.findByRole("button", { name: "Run AI analysis" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Run analysis" }));
    expect(await screen.findByText("Analysis complete.")).toBeInTheDocument();
    expect(calls.some((c) => c.key === "POST /hygiene/inspections/i1/analyze")).toBe(true);
  });

  it("submits and approves", async () => {
    let state : HygieneDetail = DETAIL;
    const { calls } = mockApi(routes({
        "POST /hygiene/inspections/i1/submit": () => {
            state = { ...state, status: "in_review", status_label: "In review" };
            return json(200, state);
        },
    "POST /hygiene/inspections/i1/approve": () => {
      state = {
        ...state,
        status: "approved",
        status_label: "Approved",
        reviewed_at: "2026-10-27T11:00:00Z",
      };
      return json(200, state);
    },
    }));
    const user = userEvent.setup();
    renderApp("/hygiene/i1");
    await user.click(await screen.findByRole("button", { name: "Submit for review" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Submit" }));
    await screen.findByRole("button", { name: "Approve" });
    await user.click(screen.getByRole("button", { name: "Approve" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Approve" }));
    expect(await screen.findByText(/Approved.*read-only/)).toBeInTheDocument();
    expect(calls.some((c) => c.key === "POST /hygiene/inspections/i1/approve")).toBe(true);
  });

  it("opens the printable report in a new tab", async () => {
    const open = vi.spyOn(window, "open").mockReturnValue({} as Window);
    mockApi(routes({
      "GET /hygiene/inspections/i1/report": () => new Response(
        "<html><head><style>@media print{}</style></head><body>Hygiene inspection report</body></html>",
        { headers: { "Content-Type": "text/html" } },
      ),
    }));
    const user = userEvent.setup();
    renderApp("/hygiene/i1");
    await user.click(await screen.findByRole("button", { name: "Print / Save PDF" }));
    await waitFor(() => expect(open).toHaveBeenCalled());
    expect(String(open.mock.calls[0][0])).toMatch(/^blob:/);
    open.mockRestore();
  });

  it("surfaces a model error without losing the draft", async () => {
    mockApi(routes({
      "POST /hygiene/inspections/i1/analyze": () => json(504, errorBody("vision_timeout", "The vision model took too long.")),
    }));
    const user = userEvent.setup();
    renderApp("/hygiene/i1");
    await user.click(await screen.findByRole("button", { name: "Run AI analysis" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Run analysis" }));
    expect(await screen.findByText(/The vision model took too long/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run AI analysis" })).toBeInTheDocument();
  });

  it("deletes after confirmation", async () => {
    let deleted = false;
    mockApi(hygieneRoutes({
      "GET /hygiene/inspections/i1": () => json(200, DETAIL),
      "DELETE /hygiene/inspections/i1": () => { deleted = true; return new Response(null, { status: 204 }); },
      "GET /hygiene/inspections?page=1&page_size=10": () => json(200, LIST_PAGE(deleted ? [] : [DETAIL])),
    }));
    const user = userEvent.setup();
    renderApp("/hygiene/i1");
    await user.click(await screen.findByRole("button", { name: "Delete" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("No inspections yet")).toBeInTheDocument();
  });
});

describe("history", () => {
  it("lists and filters", async () => {
    const { calls } = mockApi(hygieneRoutes({
      "GET /hygiene/inspections?page=1&page_size=10": () => json(200, LIST_PAGE()),
      "GET /hygiene/inspections?page=1&page_size=10&status=approved": () => json(200, LIST_PAGE([])),
    }));
    const user = userEvent.setup();
    renderApp("/hygiene/history");
    const link = await screen.findByRole("link", { name: "Main kitchen" });
    expect(link).toHaveAttribute("href", "/hygiene/i1");
    await user.selectOptions(screen.getByLabelText("Status"), "approved");
    expect(await screen.findByText("No inspections yet")).toBeInTheDocument();
    expect(calls.some((c) => c.key.endsWith("status=approved"))).toBe(true);
  });

  it("shows an honest empty state", async () => {
    mockApi(hygieneRoutes({ "GET /hygiene/inspections?page=1&page_size=10": () => json(200, LIST_PAGE([])) }));
    renderApp("/hygiene/history");
    expect(await screen.findByText("No inspections yet")).toBeInTheDocument();
  });
});