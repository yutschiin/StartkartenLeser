import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NotificationProvider, useNotify } from "../src/Notifications";

const retry = vi.fn();

function Harness() {
  const notify = useNotify();
  return <>
    <button onClick={() => notify("success", "Saved")}>Notify</button>
    <button onClick={() => notify("info", "Next message")}>Next</button>
    <button onClick={() => { notify("warning", "Warning"); notify("error", "Failed"); }}>Burst</button>
    <button onClick={() => notify("warning", "Warning")}>Warn</button>
    <button onClick={() => notify("error", "Failed")}>Fail</button>
    <button onClick={() => notify("info", "Short message", { timeoutMs: 1000 })}>Short</button>
    <button onClick={() => notify("error", "Save failed", { key: "save", timeoutMs: null, action: { label: "Retry", onClick: retry } })}>Sticky</button>
    <button onClick={() => notify.dismiss("save")}>Dismiss</button>
  </>;
}

function advance(ms: number) {
  act(() => vi.advanceTimersByTime(ms));
}

describe("notifications", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("shows a message and auto-hides after its custom timeout", () => {
    render(<NotificationProvider><Harness /></NotificationProvider>);
    fireEvent.click(screen.getByText("Short"));
    expect(screen.getByRole("status")).toHaveTextContent("Short message");
    advance(999);
    expect(screen.getByRole("status")).toBeVisible();
    advance(1);
    advance(300);
    expect(screen.queryByText("Short message")).not.toBeInTheDocument();
  });

  it.each([
    ["Notify", "Saved", "status", 5000],
    ["Next", "Next message", "status", 5000],
    ["Warn", "Warning", "alert", 8000],
    ["Fail", "Failed", "alert", 10000],
  ] as const)("uses the role and default timeout for %s", (button, message, role, timeout) => {
    render(<NotificationProvider><Harness /></NotificationProvider>);
    fireEvent.click(screen.getByText(button));
    expect(screen.getByRole(role)).toHaveTextContent(message);
    expect(screen.getByRole(role)).toHaveAttribute("aria-live", role === "status" ? "polite" : "assertive");
    advance(timeout - 1);
    expect(screen.getByRole(role)).toBeVisible();
    advance(1);
    advance(300);
    expect(screen.queryByText(message)).not.toBeInTheDocument();
  });

  it("shows queued messages only after the previous transition exits", () => {
    render(<NotificationProvider><Harness /></NotificationProvider>);
    fireEvent.click(screen.getByText("Notify"));
    fireEvent.click(screen.getByText("Next"));
    expect(screen.getByText("Saved")).toBeInTheDocument();
    expect(screen.queryByText("Next message")).not.toBeInTheDocument();
    advance(300);
    expect(screen.queryByText("Saved")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Next message");
  });

  it("preserves every message in a burst, including the newest", () => {
    render(<NotificationProvider><Harness /></NotificationProvider>);
    fireEvent.click(screen.getByText("Notify"));
    fireEvent.click(screen.getByText("Burst"));
    advance(300);
    expect(screen.getByText("Warning")).toBeInTheDocument();
    expect(screen.queryByText("Failed")).not.toBeInTheDocument();
    advance(300);
    expect(screen.queryByText("Warning")).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Failed");
  });

  it("can be dismissed with the close button", () => {
    render(<NotificationProvider><Harness /></NotificationProvider>);
    fireEvent.click(screen.getByText("Notify"));
    fireEvent.click(within(screen.getByRole("status")).getByRole("button", { name: /close/i }));
    advance(300);
    expect(screen.queryByText("Saved")).not.toBeInTheDocument();
  });

  it("keeps a persistent message with an action until it is dismissed by key", () => {
    render(<NotificationProvider><Harness /></NotificationProvider>);
    fireEvent.click(screen.getByText("Sticky"));
    advance(60000);
    expect(screen.getByRole("alert")).toHaveTextContent("Save failed");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(retry).toHaveBeenCalledTimes(1);
    advance(300);
    expect(screen.queryByText("Save failed")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Sticky"));
    expect(screen.getByRole("alert")).toBeVisible();
    fireEvent.click(screen.getByText("Dismiss"));
    advance(300);
    expect(screen.queryByText("Save failed")).not.toBeInTheDocument();
  });

  it("is a safe no-op without a provider", () => {
    render(<Harness />);
    expect(() => fireEvent.click(screen.getByText("Notify"))).not.toThrow();
    expect(screen.queryByText("Saved")).not.toBeInTheDocument();
  });
});
