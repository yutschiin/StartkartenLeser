import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { useState } from "react";
import App, { CameraView, ReviewView, SharedEvidence } from "../src/App";
import { ApiClient, ApiError, CARD_KEY, SESSION_KEY } from "../src/api";
import { BrowserCamera } from "../src/camera";
import { translate } from "../src/localization";
import { NotificationProvider } from "../src/Notifications";
import { installSpaceButtonActivation } from "../src/keyboard";
import type { Card, Session } from "../src/types";

const session: Session = {
  id: "session-1",
  number: 2,
  distance_m: 50,
  stroke: "ruecken",
  gender: "female",
  revision: 1,
};
const card: Card = {
  id: "card-1",
  session_id: session.id,
  sequence: 1,
  state: "needs_review",
  revision: 1,
  fields: {},
  checkboxes: {},
};
const backendTexts = {
  "session.create": "Neue Sitzung",
  "session.delete": "Sitzung löschen",
  "card.row": "Karte {number} — {status}",
  "field.name": "Name",
  "status.needs_review": "Prüfung ausstehend",
};
const t = (key: string, values?: Record<string, string | number>) =>
  translate(backendTexts, key, values);

describe("committed enabled-state focus", () => {
  it.each([" ", "{Enter}"])("activates Retake with %s while autosave is in flight", async (key) => {
    const user = userEvent.setup();
    const api = new ApiClient("test-token");
    let finishSave: ((updated: Card) => void) | undefined;
    const save = vi.spyOn(api, "patchCard").mockImplementation(() =>
      new Promise<Card>((resolve) => { finishSave = resolve; }),
    );
    const onRetake = vi.fn();
    const uninstall = installSpaceButtonActivation();
    function ReviewHarness() {
      const [current, setCurrent] = useState(card);
      return <ReviewView
        api={api} card={current} pendingImage={null} pending={false}
        sessions={[session]} localImageBlob={null} t={t}
        onDirtyChange={vi.fn()} onCardUpdate={setCurrent}
        onApproved={vi.fn()} onBack={vi.fn()} onRetake={onRetake}
        onRetryCapture={vi.fn()} onMove={vi.fn()} onDelete={vi.fn()}
      />;
    }
    try {
      render(<ReviewHarness />);
      await user.tab();
      await user.type(screen.getByRole("textbox", { name: "Name" }), "Saved");
      await user.tab({ shift: true });
      await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
      const retake = screen.getByRole("button", { name: "Bild erneut aufnehmen" });
      expect(retake).toBeEnabled();
      expect(retake).toHaveFocus();
      await user.keyboard(key);
      expect(onRetake).not.toHaveBeenCalled();
      await act(async () => finishSave?.({ ...card, revision: 2 }));
      await waitFor(() => expect(onRetake).toHaveBeenCalledWith(expect.objectContaining({ revision: 2 })));
    } finally {
      uninstall();
    }
  });

  it("focuses capture after readiness and a busy commit, and on the next camera mount", async () => {
    let ready: (() => void) | undefined;
    vi.spyOn(BrowserCamera.prototype, "start").mockImplementation(
      () => new Promise<void>((resolve) => { ready = resolve; }),
    );
    vi.spyOn(BrowserCamera.prototype, "stop").mockImplementation(() => undefined);
    const props = {
      api: null,
      session,
      replace: null,
      busy: true,
      error: "",
      t,
      onCapture: vi.fn().mockResolvedValue(undefined),
      onCancel: vi.fn(),
    };
    const view = render(<CameraView {...props} />);
    const shutter = screen.getByRole("button", { name: "Bild aufnehmen" });
    expect(shutter).toBeDisabled();

    await act(async () => ready?.());
    expect(shutter).toBeDisabled();
    expect(shutter).not.toHaveFocus();
    view.rerender(<CameraView {...props} busy={false} />);
    expect(shutter).toBeEnabled();
    expect(shutter).toHaveFocus();

    view.unmount();
    render(<CameraView {...props} busy={false} />);
    const nextShutter = screen.getByRole("button", { name: "Bild aufnehmen" });
    await act(async () => ready?.());
    expect(nextShutter).toBeEnabled();
    expect(nextShutter).toHaveFocus();
  });

  it("focuses Retake once persistence enables review and uses native next-field order", async () => {
    const props = {
      api: null,
      card,
      pendingImage: null,
      pending: true,
      sessions: [session],
      localImageBlob: null,
      t,
      onDirtyChange: vi.fn(),
      onCardUpdate: vi.fn(),
      onApproved: vi.fn().mockResolvedValue(undefined),
      onBack: vi.fn().mockResolvedValue(undefined),
      onRetake: vi.fn(),
      onRetryCapture: vi.fn(),
      onMove: vi.fn().mockResolvedValue(undefined),
      onDelete: vi.fn(),
    };
    const view = render(<ReviewView {...props} />);
    const retake = screen.getByRole("button", { name: "Bild erneut aufnehmen" });
    expect(retake).toBeDisabled();

    view.rerender(<ReviewView {...props} pending={false} />);
    await waitFor(() => expect(retake).toHaveFocus());
    const name = screen.getByRole("textbox", { name: "Name" });
    const controls = Array.from(document.querySelectorAll("button,input"));
    expect(controls.indexOf(name)).toBe(controls.indexOf(retake) + 1);
    expect(screen.getByRole("heading", { name: "Startkarte", level: 1 })).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("{status}");
    const user = userEvent.setup();
    const year = screen.getByRole("textbox", { name: "Jahrgang" });
    const female = screen.getByRole("radio", { name: "Mädchen" });
    const male = screen.getByRole("radio", { name: "Junge" });
    const course = screen.getByRole("textbox", { name: "Strecke" });
    year.focus();
    for (const control of [female, male, course]) {
      await user.tab();
      expect(control).toHaveFocus();
    }
    for (const control of [male, female, year]) {
      await user.tab({ shift: true });
      expect(control).toHaveFocus();
    }
  });
});

describe("review notifications", () => {
  it("shows recognition completion outside the form and hides it after five seconds", async () => {
    vi.useFakeTimers();
    const api = new ApiClient("test-token");
    vi.spyOn(api, "recognize").mockResolvedValue({
      ...card,
      recognition: { status: "completed", error_key: null },
    });
    const reviewT = (key: string, values?: Record<string, string | number>) =>
      key === "review.recognitionComplete" ? "Texterkennung abgeschlossen" : t(key, values);

    try {
      render(
        <NotificationProvider>
          <ReviewView
            api={api} card={card} pendingImage={null} pending={false}
            sessions={[session]} localImageBlob={null} t={reviewT}
            onDirtyChange={vi.fn()} onCardUpdate={vi.fn()}
            onApproved={vi.fn()} onBack={vi.fn()} onRetake={vi.fn()}
            onRetryCapture={vi.fn()} onMove={vi.fn()} onDelete={vi.fn()}
          />
        </NotificationProvider>,
      );
      fireEvent.click(screen.getByRole("button", { name: "Texterkennung starten" }));
      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
        await Promise.resolve();
      });

      const message = screen.getByText("Texterkennung abgeschlossen");
      expect(message.closest(".review-form")).toBeNull();
      expect(message.closest('[role="status"]')).toBeInTheDocument();
      act(() => vi.advanceTimersByTime(5000));
      act(() => vi.advanceTimersByTime(300));
      expect(screen.queryByText("Texterkennung abgeschlossen")).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
      vi.restoreAllMocks();
    }
  });
});

describe("backend catalog collisions", () => {
  it("keeps Wettkampf actions and frontend placeholder sets separate", () => {
    expect(t("frontend.session.create")).toBe("Neuer Wettkampf");
    expect(t("frontend.session.delete")).toBe("Wettkampf löschen");
    expect(t("frontend.card.row", { number: 3, state: "Geprüft" })).toBe("Karte 3 · Geprüft");
    expect(t("field.name")).toBe(backendTexts["field.name"]);
  });

  it("hides empty shared evidence and displays unchanged raw text with localized provenance", () => {
    const view = render(<SharedEvidence candidates={{}} t={t} />);
    expect(view.container).toBeEmptyDOMElement();
    view.rerender(<SharedEvidence candidates={{
      course_position: { raw_text: " 50m\nRü cken ", provenance: "ocr" },
    }} t={t} />);
    expect(view.container.querySelector("dd")?.textContent).toBe(" 50m\nRü cken ");
    expect(screen.getByText("Herkunft: Texterkennung")).toBeInTheDocument();
    expect(view.container.textContent).not.toContain("raw_text");
  });
});

describe("persisted retake cancellation", () => {
  it("restores complete saved values and uses the latest revision for replacement", async () => {
    sessionStorage.setItem("startkartenleser.apiToken", "test-token");
    sessionStorage.setItem(SESSION_KEY, session.id);
    sessionStorage.setItem(CARD_KEY, card.id);
    let stored = structuredClone(card);
    vi.spyOn(ApiClient.prototype, "bootstrap").mockResolvedValue({
      sessions: [session], texts: backendTexts,
    });
    vi.spyOn(ApiClient.prototype, "getSession").mockImplementation(async () => ({
      session, cards: [stored],
    }));
    vi.spyOn(ApiClient.prototype, "getCard").mockImplementation(async () => stored);
    vi.spyOn(ApiClient.prototype, "image").mockResolvedValue(new Blob(["image"]));
    vi.spyOn(ApiClient.prototype, "patchCard").mockImplementation(async (_id, payload) => {
      expect(payload.revision).toBe(stored.revision);
      stored = {
        ...stored,
        revision: stored.revision + 1,
        checkboxes: {
          ...stored.checkboxes,
          ...Object.fromEntries(Object.entries(payload.checkboxes ?? {}).map(
            ([key, state]) => [key, { state, confirmed: true }],
          )),
        },
        fields: {
          ...stored.fields,
          ...Object.fromEntries(Object.entries(payload.fields ?? {}).map(
            ([key, value]) => [key, { value, confirmed: true }],
          )),
        },
      };
      return stored;
    });
    const capture = vi.spyOn(ApiClient.prototype, "capture").mockImplementation(async (payload) => {
      expect(payload.replace_card_id).toBe(card.id);
      expect(payload.revision).toBe(stored.revision);
      stored = { ...stored, revision: stored.revision + 1, fields: {} };
      return stored;
    });
    vi.spyOn(BrowserCamera.prototype, "start").mockResolvedValue();
    vi.spyOn(BrowserCamera.prototype, "stop").mockImplementation(() => undefined);
    vi.spyOn(BrowserCamera.prototype, "capture").mockResolvedValue(
      new Blob(["new image"], { type: "image/png" }),
    );
    const originalCreate = URL.createObjectURL;
    const originalRevoke = URL.revokeObjectURL;
    URL.createObjectURL = vi.fn(() => "blob:test-image");
    URL.revokeObjectURL = vi.fn();
    const user = userEvent.setup();
    try {
      render(<App />);
      const name = await screen.findByRole("textbox", { name: "Name" });
      await user.type(name, "RetakeKeep");
      await user.tab();
      await waitFor(() => expect(stored.fields.name?.value).toBe("RetakeKeep"));
      await waitFor(() => expect(screen.getByText("Gespeichert")).toBeInTheDocument());
      const header = within(screen.getByRole("banner"));
      expect(header.getByRole("heading", { name: "Startkarte", level: 1 })).toBeInTheDocument();
      const back = screen.getByRole("button", { name: "Zurück zur Kartenliste" });
      expect(header.queryByRole("button", { name: "Zurück zur Kartenliste" })).not.toBeInTheDocument();
      expect(back.closest(".sub-header")).toBeInTheDocument();
      expect(back.closest("main")).toBeNull();
      expect(header.getByText("Gespeichert")).toBeInTheDocument();
      expect(header.getByText("Gespeichert").closest(".MuiChip-root")).not.toBeNull();
      expect(header.getByRole("heading", { level: 1 }).closest(".toolbar-single-line")).not.toBeNull();
      const vorname = screen.getByRole("textbox", { name: "Vorname" });
      await user.type(vorname, "Anna");
      expect(header.getByText("Nicht gespeichert")).toBeInTheDocument();
      await user.tab();
      await user.click(name);
      expect((name as HTMLInputElement).selectionStart).toBe(0);
      expect((name as HTMLInputElement).selectionEnd).toBe("RetakeKeep".length);
      await user.tab();
      expect((vorname as HTMLInputElement).selectionStart).toBe(0);
      expect((vorname as HTMLInputElement).selectionEnd).toBe("Anna".length);
      expect(header.getByText(/Wettkampf 2/)).toBeInTheDocument();
      expect(header.queryByText("StartkartenLeser", { exact: true })).not.toBeInTheDocument();
      expect(header.getByRole("button", { name: "Texterkennung starten" })).toBeInTheDocument();
      expect(header.getByRole("button", { name: "Karte löschen" })).toBeInTheDocument();
      expect(screen.queryByText(t("review.help"))).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Kartendetails" })).not.toBeInTheDocument();
      const gender = screen.getByRole("radiogroup", { name: "Geschlecht" });
      await user.click(within(gender).getByRole("radio", { name: "Junge" }));
      await user.tab();
      await waitFor(() => {
        expect(stored.checkboxes.male?.state).toBe("checked");
        expect(stored.checkboxes.female?.state).toBe("unchecked");
      });
      await user.tab({ shift: true });
      await user.keyboard("{ArrowLeft}");
      await user.tab();
      await waitFor(() => {
        expect(stored.checkboxes.female?.state).toBe("checked");
        expect(stored.checkboxes.male?.state).toBe("unchecked");
      });
      await user.tab({ shift: true });
      expect(within(gender).getByRole("radio", { name: "Mädchen" })).toHaveFocus();
      await user.keyboard("{Enter}");
      expect(within(gender).getByRole("radio", { name: "Junge" })).toHaveFocus();
      await user.keyboard("{Enter}");
      expect(screen.getByRole("textbox", { name: "Strecke" })).toHaveFocus();
      await waitFor(() => expect(header.getByText("Gespeichert")).toBeInTheDocument());
      const savedRevision = stored.revision;

      await user.click(screen.getByRole("button", { name: "Bild erneut aufnehmen" }));
      await user.click(await screen.findByRole("button", { name: "Bild ersetzen" }));
      await waitFor(() => expect(screen.getByRole("button", { name: "Bild ersetzen" })).toHaveFocus());
      await user.keyboard("{Escape}");
      expect(await screen.findByRole("textbox", { name: "Name" })).toHaveValue("RetakeKeep");
      expect(stored.revision).toBe(savedRevision);

      await user.click(screen.getByRole("button", { name: "Bild erneut aufnehmen" }));
      await user.click(await screen.findByRole("button", { name: "Bild ersetzen" }));
      await waitFor(() => expect(screen.getByRole("button", { name: "Bild ersetzen" })).toHaveFocus());
      await user.click(screen.getByRole("button", { name: "Bild ersetzen" }));
      await waitFor(() => expect(capture).toHaveBeenCalledTimes(1));
      expect(await screen.findByRole("textbox", { name: "Name" })).toHaveValue("");
      expect(stored.id).toBe(card.id);
      expect(stored.sequence).toBe(card.sequence);
      expect(stored.revision).toBe(savedRevision + 1);
    } finally {
      sessionStorage.clear();
      URL.createObjectURL = originalCreate;
      URL.revokeObjectURL = originalRevoke;
      vi.restoreAllMocks();
    }
  }, 20_000);
});

describe("launch token hashchange", () => {
  it("reauthenticates a reused tab with the new fragment token", async () => {
    sessionStorage.setItem("startkartenleser.apiToken", "old-token");
    sessionStorage.setItem(SESSION_KEY, session.id);
    const authTokens: string[] = [];
    vi.spyOn(ApiClient.prototype, "bootstrap").mockImplementation(async function (this: ApiClient) {
      const token = (this as unknown as { token: string }).token;
      authTokens.push(token);
      if (token === "old-token") throw new ApiError("Ungültiges Token", 403);
      return { sessions: [session], texts: backendTexts };
    });
    const getSession = vi.spyOn(ApiClient.prototype, "getSession").mockImplementation(
      async () => ({ session, cards: [] }),
    );
    try {
      render(<NotificationProvider><App /></NotificationProvider>);
      expect(await screen.findByText("Ungültiges Token")).toBeInTheDocument();
      expect(getSession).not.toHaveBeenCalled();

      await act(async () => {
        window.history.replaceState(null, "", "/#new-token");
        window.dispatchEvent(new HashChangeEvent("hashchange"));
      });

      await waitFor(() => expect(getSession).toHaveBeenCalledTimes(1));
      expect(authTokens).toEqual(["old-token", "new-token"]);
      expect(sessionStorage.getItem("startkartenleser.apiToken")).toBe("new-token");
      expect(window.location.hash).toBe("");
      expect(document.querySelector(".global-alert")).toBeNull();

      await act(async () => {
        window.history.replaceState(null, "", "/#new-token");
        window.dispatchEvent(new HashChangeEvent("hashchange"));
      });
      expect(window.location.hash).toBe("");
      expect(authTokens).toEqual(["old-token", "new-token"]);
    } finally {
      sessionStorage.clear();
      window.history.replaceState(null, "", "/");
      vi.restoreAllMocks();
    }
  });
});
