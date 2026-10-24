import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  MEDIA_ITEM, authBody, blob, dashboardRoutes, emptySummary, errorBody, json, mockApi, page, renderApp,
} from "./helpers";

const signedIn = { "POST /auth/refresh": () => json(200, authBody()) };
const summary = { "GET /dashboard/summary": () => json(200, { ...emptySummary, media: { ...emptySummary.media, count: 1, total_bytes: 204800 } }) };
const png = () => new File([new Uint8Array([137, 80, 78, 71])], "lunch.png", { type: "image/png" });

describe("media library", () => {
  it("lists photos with metadata and loads images through the authenticated API", async () => {
    const { calls } = mockApi({
      ...signedIn,
      ...summary,
      "GET /media?page=1&page_size=12": () => json(200, page([MEDIA_ITEM], { page_size: 12 })),
      "GET /media/m1/content": () => blob(),
    });
    renderApp("/media");
    expect(await screen.findByText("lunch.jpg")).toBeInTheDocument();
    expect(screen.getByText(/800×600 · 200 KB/)).toBeInTheDocument();
    const img = await screen.findByRole("img", { name: "lunch.jpg" });
    expect(img).toHaveAttribute("src", "blob:test-image");
    const content = calls.find((c) => c.key === "GET /media/m1/content");
    expect(content?.headers.get("Authorization")).toBe("Bearer access-1");
  });

  it("shows an empty state for a new library", async () => {
    mockApi({
      ...signedIn,
      "GET /dashboard/summary": () => json(200, emptySummary),
      "GET /media?page=1&page_size=12": () => json(200, page([], { page_size: 12 })),
    });
    renderApp("/media");
    expect(await screen.findByText("No photos yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload" })).toBeDisabled();
  });

  it("uploads a valid image as multipart, then refreshes the list and shows a notification", async () => {
    let uploaded = false;
    const { calls } = mockApi({
      ...signedIn,
      ...summary,
      "GET /media?page=1&page_size=12": () =>
        json(200, page(uploaded ? [MEDIA_ITEM] : [], { page_size: 12 })),
      "POST /media": () => {
        uploaded = true;
        return json(201, MEDIA_ITEM);
      },
      "GET /media/m1/content": () => blob(),
    });
    const user = userEvent.setup();
    renderApp("/media");
    await screen.findByText("No photos yet");

    await user.upload(screen.getByLabelText("Image file"), png());
    await user.click(screen.getByRole("button", { name: "Upload" }));

    expect(await screen.findByText("Photo uploaded.")).toBeInTheDocument();
    expect(await screen.findByText("lunch.jpg")).toBeInTheDocument();
    const post = calls.find((c) => c.key === "POST /media");
    expect((post?.body as FormData).get("file")).toBeInstanceOf(File);
    expect(post?.headers.get("X-Requested-With")).toBe("FoodVerseWeb");
    expect(post?.headers.get("Content-Type")).toBeNull(); // browser must set the multipart boundary
  });

  it("rejects an unsupported file type before uploading", async () => {
    const { calls } = mockApi({
      ...signedIn, ...summary,
      "GET /media?page=1&page_size=12": () => json(200, page([], { page_size: 12 })),
    });
    const user = userEvent.setup({ applyAccept: false });
    renderApp("/media");
    await screen.findByText("No photos yet");
    await user.upload(screen.getByLabelText("Image file"), new File(["hi"], "notes.txt", { type: "text/plain" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose a JPEG, PNG or WebP image.");
    expect(screen.getByRole("button", { name: "Upload" })).toBeDisabled();
    expect(calls.some((c) => c.key === "POST /media")).toBe(false);
  });

  it("rejects a file over the server's limit before uploading", async () => {
    const { calls } = mockApi({
      ...signedIn,
      "GET /dashboard/summary": () => json(200, { ...emptySummary, media: { ...emptySummary.media, max_upload_bytes: 1000 } }),
      "GET /media?page=1&page_size=12": () => json(200, page([], { page_size: 12 })),
    });
    const user = userEvent.setup();
    renderApp("/media");
    await screen.findByText("No photos yet");
    await waitFor(() => expect(screen.getByText(/up to 1000 B/)).toBeInTheDocument());
    await user.upload(screen.getByLabelText("Image file"), new File(["x".repeat(2000)], "big.png", { type: "image/png" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/The limit is 1000 B/);
    expect(calls.some((c) => c.key === "POST /media")).toBe(false);
  });

  it("shows the server's reason when an upload is rejected, and allows retrying", async () => {
    mockApi({
      ...signedIn, ...summary,
      "GET /media?page=1&page_size=12": () => json(200, page([], { page_size: 12 })),
      "POST /media": () => json(422, errorBody("invalid_image", "The file could not be decoded as a valid image.")),
    });
    const user = userEvent.setup();
    renderApp("/media");
    await screen.findByText("No photos yet");
    await user.upload(screen.getByLabelText("Image file"), png());
    await user.click(screen.getByRole("button", { name: "Upload" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be decoded");
    expect(screen.getByRole("button", { name: "Upload" })).toBeEnabled();
  });

  it("asks for confirmation before deleting, and cancelling deletes nothing", async () => {
    let items = [MEDIA_ITEM];
    const { calls } = mockApi({
      ...signedIn, ...summary,
      "GET /media?page=1&page_size=12": () => json(200, page(items, { page_size: 12 })),
      "GET /media/m1/content": () => blob(),
      "DELETE /media/m1": () => {
        items = [];
        return new Response(null, { status: 204 });
      },
    });
    const user = userEvent.setup();
    renderApp("/media");
    await user.click(await screen.findByRole("button", { name: "Delete lunch.jpg" }));

    const dialog = await screen.findByRole("dialog", { name: "Delete this photo?" });
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(calls.some((c) => c.key === "DELETE /media/m1")).toBe(false);

    await user.click(screen.getByRole("button", { name: "Delete lunch.jpg" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("Photo deleted.")).toBeInTheDocument();
    expect(await screen.findByText("No photos yet")).toBeInTheDocument();
    expect(calls.find((c) => c.key === "DELETE /media/m1")?.headers.get("X-Requested-With")).toBe("FoodVerseWeb");
  });

  it("surfaces a failed delete as an error notification", async () => {
    mockApi({
      ...signedIn, ...summary,
      "GET /media?page=1&page_size=12": () => json(200, page([MEDIA_ITEM], { page_size: 12 })),
      "GET /media/m1/content": () => blob(),
      "DELETE /media/m1": () => json(404, errorBody("media_not_found", "Media not found.")),
    });
    const user = userEvent.setup();
    renderApp("/media");
    await user.click(await screen.findByRole("button", { name: "Delete lunch.jpg" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("Media not found.")).toBeInTheDocument();
  });

  it("paginates", async () => {
    const { calls } = mockApi({
      ...signedIn, ...summary,
      "GET /media?page=1&page_size=12": () => json(200, page([MEDIA_ITEM], { page_size: 12, total: 13, pages: 2 })),
      "GET /media?page=2&page_size=12": () => json(200, page([{ ...MEDIA_ITEM, id: "m2", display_name: "dinner.jpg" }], { page: 2, page_size: 12, total: 13, pages: 2 })),
      "GET /media/m1/content": () => blob(),
      "GET /media/m2/content": () => blob(),
    });
    const user = userEvent.setup();
    renderApp("/media");
    await screen.findByText("Page 1 of 2");
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("dinner.jpg")).toBeInTheDocument();
    expect(calls.some((c) => c.key === "GET /media?page=2&page_size=12")).toBe(true);
  });

  it("shows an unavailable placeholder if an image cannot be loaded", async () => {
    mockApi({
      ...signedIn, ...summary,
      "GET /media?page=1&page_size=12": () => json(200, page([MEDIA_ITEM], { page_size: 12 })),
      "GET /media/m1/content": () => json(404, errorBody("media_not_found", "Media content is unavailable.")),
    });
    renderApp("/media");
    expect(await screen.findByRole("img", { name: /could not be loaded/ })).toBeInTheDocument();
  });
});

// Keep the shared dashboard routes import used even if a test above stops needing it.
void dashboardRoutes;
