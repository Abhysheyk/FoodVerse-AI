import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import { setAccessToken, setSessionLostHandler } from "../api/client";

afterEach(() => {
  cleanup();
  setAccessToken(null);
  setSessionLostHandler(null);
  vi.unstubAllGlobals();
});
