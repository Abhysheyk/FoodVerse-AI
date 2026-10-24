import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { ToastProvider, useToast } from "../components/Toast";

function Harness({ onConfirm }: { onConfirm: () => Promise<void> | void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>Open</button>
      <ConfirmDialog open={open} title="Delete?" message="Really?" confirmLabel="Delete"
        onConfirm={async () => { await onConfirm(); setOpen(false); }} onCancel={() => setOpen(false)} />
    </>
  );
}

describe("ConfirmDialog keyboard behaviour", () => {
  it("focuses the safe button, traps Tab, closes on Escape and restores focus", async () => {
    const user = userEvent.setup();
    render(<Harness onConfirm={() => {}} />);
    const opener = screen.getByRole("button", { name: "Open" });
    await user.click(opener);

    const dialog = screen.getByRole("dialog", { name: "Delete?" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    const cancel = screen.getByRole("button", { name: "Cancel" });
    const confirm = screen.getByRole("button", { name: "Delete" });
    expect(cancel).toHaveFocus(); // destructive action is never the default

    await user.tab();
    expect(confirm).toHaveFocus();
    await user.tab(); // wraps instead of escaping to the page behind
    expect(cancel).toHaveFocus();
    await user.tab({ shift: true });
    expect(confirm).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("disables both buttons while the action is running", async () => {
    let finish: () => void = () => {};
    const user = userEvent.setup();
    render(<Harness onConfirm={() => new Promise<void>((r) => (finish = r))} />);
    await user.click(screen.getByRole("button", { name: "Open" }));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(screen.getByRole("button", { name: "Working…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    await act(async () => finish());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

function ToastButtons() {
  const toast = useToast();
  return (
    <>
      <button onClick={() => toast.success("Saved!")}>ok</button>
      <button onClick={() => toast.error("Broke!")}>bad</button>
    </>
  );
}

describe("notifications", () => {
  it("success toasts fade on their own; error toasts stay until dismissed", () => {
    vi.useFakeTimers();
    try {
      render(<ToastProvider><ToastButtons /></ToastProvider>);
      fireEvent.click(screen.getByText("ok"));
      fireEvent.click(screen.getByText("bad"));
      expect(screen.getByRole("status")).toHaveTextContent("Saved!");
      expect(screen.getByRole("alert")).toHaveTextContent("Broke!");

      act(() => { vi.advanceTimersByTime(6000); });
      expect(screen.queryByText("Saved!")).not.toBeInTheDocument();
      expect(screen.getByText("Broke!")).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: "Dismiss notification" }));
      expect(screen.queryByText("Broke!")).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});
