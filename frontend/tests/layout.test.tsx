import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";
import { NotificationProvider } from "../src/Notifications";
import { ApiClient, ApiError, SESSION_KEY, TOKEN_KEY } from "../src/api";
import type { Card, Session } from "../src/types";

const session: Session = {
  id: "event-1", number: 1, distance_m: 25, stroke: "freistil",
  gender: "female", revision: 1, card_count: 2, created_at: "2026-11-11T12:00:00Z",
};
const defaultStrokes = [
  { value: "freistil", label: "Freistil" },
  { value: "brust", label: "Brust" },
  { value: "ruecken", label: "Rücken" },
  { value: "schmetterling", label: "Schmetterling" },
  { value: "lagen", label: "Lagen" },
  { value: "flossenschwimmen_mit_brett", label: "Flossenschwimmen mit Brett" },
  { value: "freistil_mit_flossen", label: "Freistil mit Flossen" },
];
const card: Card = {
  id: "card-1", session_id: session.id, sequence: 3, state: "needs_review", revision: 1,
  fields: { name: { value: "Mustermann" }, first_name: { value: "Erika" },
    year: { value: "2010" }, heat: { value: "2" }, lane: { value: "4" },
    time: { value: "00:32,10" }, timekeeper: { value: "Schmidt" } },
  checkboxes: { female: { state: "checked" }, male: { state: "unchecked" } },
};

beforeEach(() => {
  sessionStorage.clear();
  sessionStorage.setItem(TOKEN_KEY, "test-token");
  vi.spyOn(ApiClient.prototype, "bootstrap").mockResolvedValue({ sessions: [session], strokes: defaultStrokes, texts: {} });
  vi.spyOn(ApiClient.prototype, "getSession").mockResolvedValue({ session, cards: [card] });
});
afterEach(() => {
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe("shared page layout", () => {
  it("shows known card counts in clickable overview rows and opens creation from the header", async () => {
    const user = userEvent.setup();
    const unknownCount = { ...session, id: "unknown", number: 2, card_count: undefined };
    vi.spyOn(ApiClient.prototype, "bootstrap").mockResolvedValue({ sessions: [session, unknownCount, { ...session, id: "empty", number: 3, card_count: 0 }], strokes: defaultStrokes, texts: {} });
    render(<App />);
    const row = await screen.findByRole("button", { name: /Wettkampf 1 · 25 m Freistil · Weiblich/ });
    expect(within(row).getByText("2 Karten")).toBeInTheDocument();
    expect(within(row).getByText(/11\.11\.2026/)).toBeInTheDocument();
    const unknownRow = screen.getByRole("button", { name: /Wettkampf 2 · 25 m Freistil · Weiblich/ });
    expect(within(unknownRow).queryByText(/Karten/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Wettkampf 3/ })).toHaveTextContent("0 Karten");
    const header = within(screen.getByRole("banner"));
    expect(header.getByRole("heading", { level: 1, name: "StartkartenLeser" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
    await user.click(header.getByRole("button", { name: "Wettkampf hinzufügen" }));
    const dialog = within(screen.getByRole("dialog", { name: "Wettkampf hinzufügen" }));
    expect(dialog.getByRole("spinbutton", { name: "Nummer" })).toBeInTheDocument();
    expect(dialog.getByRole("combobox", { name: "Lage" })).toBeInTheDocument();
    expect(dialog.queryByText(/Bild|Kamera|scannen/i)).not.toBeInTheDocument();
    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("creates a Wettkampf from the modal and opens its page", async () => {
    const user = userEvent.setup();
    const create = vi.spyOn(ApiClient.prototype, "createSession").mockResolvedValue(session);
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Wettkampf hinzufügen" }));
    const dialog = within(screen.getByRole("dialog"));
    await user.type(dialog.getByRole("spinbutton", { name: "Nummer" }), "1");
    await user.type(dialog.getByRole("spinbutton", { name: "Strecke (m)" }), "25");
    await user.click(dialog.getByRole("button", { name: "Wettkampf erstellen" }));
    await screen.findByRole("heading", { level: 1, name: "Wettkampf 1 · 25 m Freistil · Weiblich" });
    expect(create).toHaveBeenCalledWith({ number: 1, distance_m: 25, stroke: "freistil", gender: "female" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    const header = within(screen.getByRole("banner"));
    expect(header.getByRole("button", { name: "Karte scannen" })).toBeInTheDocument();
    expect(header.getByRole("button", { name: "CSV exportieren" })).toBeInTheDocument();
    expect(header.getByText("1 Karten · 0 freigegeben")).toBeInTheDocument();
    expect(header.queryByText("StartkartenLeser")).not.toBeInTheDocument();
    const back = screen.getByRole("button", { name: "Zurück zur Übersicht" });
    expect(back.closest(".sub-header")).toBeInTheDocument();
    expect(back.closest("main")).toBeNull();
    await user.click(back);
    const row = await screen.findByRole("button", { name: /Wettkampf 1/ });
    expect(within(row).getByText("2 Karten")).toBeInTheDocument();
  });

  it("uses configured Lagen from bootstrap without a management button", async () => {
    const user = userEvent.setup();
    vi.spyOn(ApiClient.prototype, "bootstrap").mockResolvedValue({
      sessions: [{ ...session, stroke: "kraul_spezial", stroke_label: "Kraul Spezial" }],
      strokes: [
        { value: "freistil", label: "Freistil" },
        { value: "kraul_spezial", label: "Kraul Spezial" },
      ],
      texts: {},
    });
    render(<App />);

    expect(await screen.findByRole("button", { name: /Wettkampf 1 · 25 m Kraul Spezial/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Lagen verwalten/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Wettkampf hinzufügen" }));
    const createDialog = within(screen.getByRole("dialog", { name: "Wettkampf hinzufügen" }));
    await user.click(createDialog.getByRole("combobox", { name: "Lage" }));
    expect(await screen.findByRole("option", { name: "Kraul Spezial" })).toBeInTheDocument();
  });

  it("accepts a one-off Lage typed into the autocomplete", async () => {
    const user = userEvent.setup();
    const create = vi.spyOn(ApiClient.prototype, "createSession").mockResolvedValue({
      ...session,
      stroke: "Speziallage",
      stroke_label: "Speziallage",
    });
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "Wettkampf hinzufügen" }));
    const dialog = within(screen.getByRole("dialog", { name: "Wettkampf hinzufügen" }));
    await user.type(dialog.getByRole("spinbutton", { name: "Nummer" }), "4");
    await user.type(dialog.getByRole("spinbutton", { name: "Strecke (m)" }), "25");
    await user.type(dialog.getByRole("combobox", { name: "Lage" }), "Speziallage");
    await user.click(dialog.getByRole("button", { name: "Wettkampf erstellen" }));

    await waitFor(() => expect(create).toHaveBeenCalledWith({
      number: 4, distance_m: 25, stroke: "Speziallage", gender: "female",
    }));
  });

  it("offers Mixed as a Wettkampfgruppe", async () => {
    const user = userEvent.setup();
    const create = vi.spyOn(ApiClient.prototype, "createSession").mockResolvedValue({
      ...session,
      gender: "mixed",
    });
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "Wettkampf hinzufügen" }));
    const dialog = within(screen.getByRole("dialog", { name: "Wettkampf hinzufügen" }));
    await user.click(dialog.getByRole("combobox", { name: "Wettkampfgruppe" }));
    await user.click(await screen.findByRole("option", { name: "Mixed" }));
    await user.type(dialog.getByRole("spinbutton", { name: "Nummer" }), "4");
    await user.type(dialog.getByRole("spinbutton", { name: "Strecke (m)" }), "25");
    await user.click(dialog.getByRole("button", { name: "Wettkampf erstellen" }));
    await waitFor(() => expect(create).toHaveBeenCalledWith({
      number: 4, distance_m: 25, stroke: "freistil", gender: "mixed",
    }));
  });

  it("shows creation failures inside the dialog without losing form values", async () => {
    const user = userEvent.setup();
    vi.spyOn(ApiClient.prototype, "createSession").mockRejectedValue(new ApiError("Anlegen fehlgeschlagen", 500));
    render(<NotificationProvider><App /></NotificationProvider>);
    await user.click(await screen.findByRole("button", { name: "Wettkampf hinzufügen" }));
    const dialog = within(screen.getByRole("dialog"));
    await user.type(dialog.getByRole("spinbutton", { name: "Nummer" }), "1");
    await user.type(dialog.getByRole("spinbutton", { name: "Strecke (m)" }), "25");
    await user.click(dialog.getByRole("button", { name: "Wettkampf erstellen" }));
    expect(dialog.getByRole("spinbutton", { name: "Nummer" })).toHaveValue(1);
    expect(dialog.queryByRole("alert")).not.toBeInTheDocument();
    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Anlegen fehlgeschlagen");
  });

  it("shows all tile details and opens review on tile click", async () => {
    const user = userEvent.setup();
    sessionStorage.setItem(SESSION_KEY, session.id);
    const getCard = vi.spyOn(ApiClient.prototype, "getCard").mockResolvedValue(card);
    vi.spyOn(ApiClient.prototype, "image").mockReturnValue(new Promise<Blob>(() => undefined));
    render(<App />);
    const tile = await screen.findByRole("button", { name: /Karte 3 · Prüfung ausstehend/ });
    const details = within(tile);
    for (const label of ["Name", "Vorname", "Jahrgang", "Geschlecht", "Lauf", "Bahn", "Erzielte Zeit", "Zeitnehmer"]) {
      expect(details.getByText(label)).toBeInTheDocument();
    }
    for (const value of ["Mustermann", "Erika", "2010", "Mädchen", "2", "4", "00:32,10", "Schmidt"]) {
      expect(details.getByText(value)).toBeInTheDocument();
    }
    expect(tile.querySelector(".status-icon.pending")).toBeInTheDocument();
    expect(details.queryByRole("button", { name: "Karte löschen" })).not.toBeInTheDocument();
    await user.click(tile);
    expect(await screen.findByRole("heading", { name: "Startkarte", level: 1 })).toBeInTheDocument();
    expect(getCard).toHaveBeenCalledWith(card.id);
    expect(screen.getByRole("button", { name: "Bild erneut aufnehmen" })).toHaveFocus();
  });

  it("keeps delete separate from opening a tile and displays empty details as dashes", async () => {
    const user = userEvent.setup();
    sessionStorage.setItem(SESSION_KEY, session.id);
    vi.spyOn(ApiClient.prototype, "getSession").mockResolvedValue({ session, cards: [{ ...card, fields: {}, checkboxes: {} }] });
    const getCard = vi.spyOn(ApiClient.prototype, "getCard");
    render(<App />);
    const tile = await screen.findByRole("button", { name: /Karte 3 · Prüfung ausstehend/ });
    expect(within(tile).getAllByText("–")).toHaveLength(8);
    await user.click(screen.getByRole("button", { name: "Karte löschen" }));
    expect(screen.getByRole("dialog", { name: "Karte löschen" })).toBeInTheDocument();
    expect(getCard).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { level: 1, name: /Wettkampf 1/, hidden: true })).toBeInTheDocument();
  });
});

describe("card review workflow", () => {
  const overlays = { width: 10, height: 10, error_key: null, overlays: [
    { region_key: "name", label_key: "field.name", source_corners: [[0, 0], [5, 0], [5, 5]] as [number, number][] },
  ] };

  function harness() {
    sessionStorage.setItem(SESSION_KEY, session.id);
    vi.spyOn(ApiClient.prototype, "getCard").mockResolvedValue(card);
    vi.spyOn(ApiClient.prototype, "image").mockResolvedValue(new Blob(["image"]));
    const originalCreate = URL.createObjectURL;
    const originalRevoke = URL.revokeObjectURL;
    URL.createObjectURL = vi.fn(() => "blob:test-image");
    URL.revokeObjectURL = vi.fn();
    return () => {
      URL.createObjectURL = originalCreate;
      URL.revokeObjectURL = originalRevoke;
    };
  }

  it("shows detection areas by default and indicates the toggle state", async () => {
    const restore = harness();
    const getOverlays = vi.spyOn(ApiClient.prototype, "overlays").mockResolvedValue(overlays);
    const user = userEvent.setup();
    try {
      render(<App />);
      await user.click(await screen.findByRole("button", { name: /Mustermann/ }));
      const header = within(screen.getByRole("banner"));
      const toggle = await header.findByRole("button", { name: "Erkennungsbereiche: an" });
      expect(toggle).toHaveAttribute("aria-pressed", "true");
      await waitFor(() => expect(getOverlays).toHaveBeenCalledWith(card.id));
      expect(await screen.findByRole("img", { name: "Startkartenbild mit Erkennungsbereichen" })).toBeInTheDocument();
      await user.click(toggle);
      const off = header.getByRole("button", { name: "Erkennungsbereiche: aus" });
      expect(off).toHaveAttribute("aria-pressed", "false");
      expect(screen.queryByRole("img", { name: "Startkartenbild mit Erkennungsbereichen" })).not.toBeInTheDocument();
    } finally {
      restore();
    }
  });

  it("runs recognition automatically after capture and locks entry meanwhile", async () => {
    const restore = harness();
    vi.spyOn(ApiClient.prototype, "overlays").mockResolvedValue(overlays);
    const captured = { ...card, id: "card-new", sequence: 4, fields: {}, checkboxes: {} };
    vi.spyOn(ApiClient.prototype, "capture").mockResolvedValue(captured);
    vi.spyOn(ApiClient.prototype, "getSession").mockResolvedValue({ session, cards: [card, captured] });
    let finish: ((value: Card) => void) | undefined;
    const recognize = vi.spyOn(ApiClient.prototype, "recognize").mockImplementation(
      () => new Promise((resolve) => { finish = resolve; }),
    );
    const { BrowserCamera } = await import("../src/camera");
    vi.spyOn(BrowserCamera.prototype, "start").mockResolvedValue();
    vi.spyOn(BrowserCamera.prototype, "stop").mockImplementation(() => undefined);
    vi.spyOn(BrowserCamera.prototype, "capture").mockResolvedValue(new Blob(["img"], { type: "image/png" }));
    const user = userEvent.setup();
    try {
      render(<App />);
      await user.click(await screen.findByRole("button", { name: "Karte scannen" }));
      await user.click(await screen.findByRole("button", { name: "Bild aufnehmen" }));
      await waitFor(() => expect(recognize).toHaveBeenCalledTimes(1));
      expect(recognize).toHaveBeenCalledWith("card-new", captured.revision);
      const busy = await screen.findByText(/Eingaben sind bis zum Abschluss gesperrt/);
      expect(busy.closest(".image-stage")).not.toBeNull();
      expect(busy.closest(".MuiAlert-root")).toBeNull();
      expect(screen.getByRole("textbox", { name: "Name" })).toBeDisabled();
      finish?.({ ...captured, revision: 2, fields: { name: { value: "Erkannt" } },
        recognition: { status: "completed", error_key: null } } as Card);
      await waitFor(() => expect(screen.getByRole("textbox", { name: "Name" })).toBeEnabled());
      expect(screen.getByRole("textbox", { name: "Name" })).toHaveValue("Erkannt");
      expect(screen.queryByText(/Eingaben sind bis zum Abschluss gesperrt/)).not.toBeInTheDocument();
      expect(recognize).toHaveBeenCalledTimes(1);
      expect(document.querySelector(".review-form .MuiAlert-root")).toBeNull();
    } finally {
      restore();
    }
  });

  it("does not run recognition when opening an existing card", async () => {
    const restore = harness();
    vi.spyOn(ApiClient.prototype, "overlays").mockResolvedValue(overlays);
    const recognize = vi.spyOn(ApiClient.prototype, "recognize");
    const user = userEvent.setup();
    try {
      render(<App />);
      await user.click(await screen.findByRole("button", { name: /Mustermann/ }));
      await screen.findByRole("textbox", { name: "Name" });
      expect(recognize).not.toHaveBeenCalled();
    } finally {
      restore();
    }
  });
});
