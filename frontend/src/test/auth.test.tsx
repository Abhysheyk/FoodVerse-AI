import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { request, setAccessToken } from "../api/client";
import { authBody, dashboardRoutes, errorBody, json, mockApi, renderApp } from "./helpers";

const anonymous = { "POST /auth/refresh": () => json(401, errorBody("invalid_refresh", "Session expired.")) };

describe("session restore and route protection", () => {
  it("redirects anonymous visitors to the login page", async () => {
    mockApi(anonymous);
    renderApp("/preferences");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("restores a session from the refresh cookie and shows the dashboard", async () => {
    mockApi({
      "POST /auth/refresh": () => json(200, authBody()),
      ...dashboardRoutes(),
    });
    renderApp("/");
    expect(await screen.findByRole("heading", { name: /Welcome, Asha/ })).toBeInTheDocument();
    expect(await screen.findByText(/Paid or external AI fallback: none/)).toBeInTheDocument();
  });
});

describe("login", () => {
  it("signs in, shows the dashboard, and never writes tokens to web storage", async () => {
    const { calls } = mockApi({
      ...anonymous,
      "POST /auth/login": () => json(200, authBody("secret-access-token")),
      ...dashboardRoutes(),
    });
    const user = userEvent.setup();
    renderApp("/login");
    await user.type(await screen.findByLabelText("Email"), "asha@example.com");
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("heading", { name: /Welcome, Asha/ })).toBeInTheDocument();
    const login = calls.find((c) => c.key === "POST /auth/login");
    expect(login?.body).toEqual({ email: "asha@example.com", password: "correct horse battery" });
    expect(login?.headers.get("X-Requested-With")).toBe("FoodVerseWeb");

    const stored = JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage });
    expect(stored).not.toContain("secret-access-token");
    expect(localStorage.length + sessionStorage.length).toBe(0);

    // The in-memory token is sent on the next authenticated call.
    const status = calls.find((c) => c.key === "GET /ai/status");
    expect(status?.headers.get("Authorization")).toBe("Bearer secret-access-token");
  });

  it("shows the server's error for wrong credentials and stays on the page", async () => {
    mockApi({
      ...anonymous,
      "POST /auth/login": () => json(401, errorBody("invalid_credentials", "Incorrect email or password.")),
    });
    const user = userEvent.setup();
    renderApp("/login");
    await user.type(await screen.findByLabelText("Email"), "asha@example.com");
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password.");
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
  });

  it("explains a network failure instead of crashing", async () => {
    mockApi({
      ...anonymous,
      "POST /auth/login": () => {
        throw new TypeError("Failed to fetch");
      },
    });
    const user = userEvent.setup();
    renderApp("/login");
    await user.type(await screen.findByLabelText("Email"), "asha@example.com");
    await user.type(screen.getByLabelText("Password"), "whatever-pass");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Could not reach the server/);
  });
});

describe("registration", () => {
  it("rejects a short password client-side without calling the API", async () => {
    const { calls } = mockApi(anonymous);
    const user = userEvent.setup();
    renderApp("/register");
    await user.type(await screen.findByLabelText("Display name"), "Asha");
    await user.type(screen.getByLabelText("Email"), "asha@example.com");
    await user.type(screen.getByLabelText("Password"), "short");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("at least 10 characters");
    expect(calls.some((c) => c.key === "POST /auth/register")).toBe(false);
  });

  it("shows a duplicate-email error from the server", async () => {
    mockApi({
      ...anonymous,
      "POST /auth/register": () => json(409, errorBody("email_taken", "An account with this email already exists.")),
    });
    const user = userEvent.setup();
    renderApp("/register");
    await user.type(await screen.findByLabelText("Display name"), "Asha");
    await user.type(screen.getByLabelText("Email"), "asha@example.com");
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already exists");
  });

  it("registers and lands on the dashboard", async () => {
    const { calls } = mockApi({
      ...anonymous,
      "POST /auth/register": () => json(201, authBody()),
      ...dashboardRoutes(),
    });
    const user = userEvent.setup();
    renderApp("/register");
    await user.type(await screen.findByLabelText("Display name"), "  Asha ");
    await user.type(screen.getByLabelText("Email"), "asha@example.com");
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("heading", { name: /Welcome, Asha/ })).toBeInTheDocument();
    expect(calls.find((c) => c.key === "POST /auth/register")?.body).toMatchObject({ display_name: "Asha" });
  });
});

describe("logout", () => {
  it("calls the logout endpoint and returns to the login page", async () => {
    const { calls } = mockApi({
      "POST /auth/refresh": () => json(200, authBody()),
      ...dashboardRoutes(),
      "POST /auth/logout": () => new Response(null, { status: 204 }),
    });
    const user = userEvent.setup();
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    const logout = calls.find((c) => c.key === "POST /auth/logout");
    expect(logout?.headers.get("X-Requested-With")).toBe("FoodVerseWeb");
  });

  it("still signs out locally if the network call fails", async () => {
    mockApi({
      "POST /auth/refresh": () => json(200, authBody()),
      ...dashboardRoutes(),
      "POST /auth/logout": () => {
        throw new TypeError("offline");
      },
    });
    const user = userEvent.setup();
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });
});

describe("api client token refresh", () => {
  it("refreshes once on 401 and retries the request with the new token", async () => {
    let first = true;
    const { calls } = mockApi({
      "GET /users/me/preferences": ({ headers }) => {
        if (first) {
          first = false;
          return json(401, errorBody("invalid_token", "Invalid or expired token."));
        }
        expect(headers.get("Authorization")).toBe("Bearer access-2");
        return json(200, { ok: true });
      },
      "POST /auth/refresh": () => json(200, authBody("access-2")),
    });
    setAccessToken("access-1");
    await expect(request("/users/me/preferences")).resolves.toEqual({ ok: true });
    expect(calls.map((c) => c.key)).toEqual([
      "GET /users/me/preferences",
      "POST /auth/refresh",
      "GET /users/me/preferences",
    ]);
  });

  it("signals session loss when refresh fails", async () => {
    mockApi({
      "GET /ai/status": () => json(401, errorBody("not_authenticated", "Authentication required.")),
      "POST /auth/refresh": () => json(401, errorBody("invalid_refresh", "Session expired.")),
    });
    const { setSessionLostHandler } = await import("../api/client");
    const lost = vi.fn();
    setSessionLostHandler(lost);
    await expect(request("/ai/status")).rejects.toMatchObject({ status: 401 });
    await waitFor(() => expect(lost).toHaveBeenCalledOnce());
  });
});
