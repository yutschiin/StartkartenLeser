import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReviewView } from "../src/App";
import { ApiClient } from "../src/api";
import { NotificationProvider } from "../src/Notifications";
import { translate } from "../src/localization";
import type { Card, Session } from "../src/types";

const session: Session = {
  id: "session-1",
  number: 2,
  distance_m: 100,
  stroke: "brust",
  gender: "male",
  revision: 1,
};

const initialCard: Card = {
  id: "card-1",
  session_id: session.id,
  sequence: 1,
  state: "needs_review",
  revision: 1,
  fields: {
    name: { value: "Muster" },
    course: { value: "100" },
    position: { value: "Brust" },
  },
  checkboxes: {
    female: { state: "unchecked" },
    male: { state: "checked" },
  },
  reference_check: {
    run_id: "run-1",
    warnings: {
      course: { expected: "100", detected: "50" },
      position: { expected: "Brust", detected: null },
      gender: { expected: "male", detected: "female" },
    },
  },
};

const t = (key: string, values?: Record<string, string | number>) =>
  translate({}, key, values);

function renderReview(card = initialCard, api: ApiClient | null = null, onCardUpdate = vi.fn()) {
  return render(
    <NotificationProvider>
      <ReviewView
        api={api}
        card={card}
        pendingImage={null}
        pending={false}
        sessions={[session]}
        localImageBlob={null}
        t={t}
        onDirtyChange={vi.fn()}
        onCardUpdate={onCardUpdate}
        onApproved={vi.fn()}
        onBack={vi.fn()}
        onRetake={vi.fn()}
        onRetryCapture={vi.fn()}
        onMove={vi.fn()}
        onDelete={vi.fn()}
      />
    </NotificationProvider>,
  );
}

afterEach(() => {
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe("recognition reference warnings", () => {
  it("uses supplied reference values and exposes mismatch and unreadable tooltips", async () => {
    const user = userEvent.setup();
    renderReview();

    expect(screen.getByRole("textbox", { name: "Strecke" })).toHaveValue("100");
    expect(screen.getByRole("textbox", { name: "Lage" })).toHaveValue("Brust");
    expect(screen.getByRole("radio", { name: "Junge" })).toBeChecked();
    expect(screen.getByRole("button", {
      name: "Wettkampf erwartet: 100. Auf der Karte erkannt: 50.",
    })).toBeInTheDocument();

    const positionWarning = screen.getByRole("button", {
      name: "Wettkampf erwartet: Brust. Auf der Karte erkannt: nicht lesbar.",
    });
    await user.hover(positionWarning);
    expect(await screen.findByRole("tooltip")).toHaveTextContent(
      "Wettkampf erwartet: Brust. Auf der Karte erkannt: nicht lesbar.",
    );
    expect(screen.getByRole("button", {
      name: "Wettkampf erwartet: Männlich. Auf der Karte erkannt: Weiblich.",
    })).toBeInTheDocument();
  });

  it("waits for field blur and does not dismiss gender when focus moves within the group", async () => {
    const user = userEvent.setup();
    renderReview();

    const courseWarning = screen.getByRole("button", {
      name: "Wettkampf erwartet: 100. Auf der Karte erkannt: 50.",
    });
    const course = screen.getByRole("textbox", { name: "Strecke" });
    await user.click(course);
    expect(courseWarning).toBeInTheDocument();
    await user.click(screen.getByRole("textbox", { name: "Name" }));
    expect(screen.queryByRole("button", { name: /erkannt: 50/ })).not.toBeInTheDocument();

    const gender = screen.getByRole("radiogroup", { name: "Geschlecht" });
    await user.click(screen.getByRole("radio", { name: "Mädchen" }));
    await user.click(screen.getByRole("radio", { name: "Junge" }));
    expect(screen.getByRole("button", {
      name: "Wettkampf erwartet: Männlich. Auf der Karte erkannt: Weiblich.",
    })).toBeInTheDocument();
    await user.click(screen.getByRole("textbox", { name: "Name" }));
    expect(screen.queryByRole("button", { name: /Männlich.*Weiblich/ })).not.toBeInTheDocument();
    expect(gender).toBeInTheDocument();
  });

  it("keeps acknowledgements across saves and reopening in the same browser session", async () => {
    const user = userEvent.setup();
    const api = new ApiClient("test-token");
    let savedCard = initialCard;
    vi.spyOn(api, "patchCard").mockImplementation(async (_id, payload) => {
      savedCard = {
        ...savedCard,
        revision: savedCard.revision + 1,
        fields: {
          ...savedCard.fields,
          ...Object.fromEntries(Object.entries(payload.fields ?? {}).map(([key, value]) => [key, { value }])),
        },
      };
      return savedCard;
    });

    function Harness() {
      const [current, setCurrent] = useState(initialCard);
      return (
        <NotificationProvider>
          <ReviewView
            api={api} card={current} pendingImage={null} pending={false}
            sessions={[session]} localImageBlob={null} t={t}
            onDirtyChange={vi.fn()}
            onCardUpdate={(updated) => { savedCard = updated; setCurrent(updated); }}
            onApproved={vi.fn()} onBack={vi.fn()} onRetake={vi.fn()}
            onRetryCapture={vi.fn()} onMove={vi.fn()} onDelete={vi.fn()}
          />
        </NotificationProvider>
      );
    }

    const view = render(<Harness />);
    await user.click(screen.getByRole("textbox", { name: "Strecke" }));
    await user.click(screen.getByRole("textbox", { name: "Name" }));
    expect(screen.queryByRole("button", { name: /erkannt: 50/ })).not.toBeInTheDocument();
    await user.clear(screen.getByRole("textbox", { name: "Strecke" }));
    await user.type(screen.getByRole("textbox", { name: "Strecke" }), "100 m");
    await user.click(screen.getByRole("textbox", { name: "Name" }));
    await waitFor(() => expect(api.patchCard).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /erkannt: 50/ })).not.toBeInTheDocument();

    view.unmount();
    renderReview(savedCard, api);
    expect(screen.queryByRole("button", { name: /erkannt: 50/ })).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Strecke" })).toHaveValue("100 m");
  });

  it("applies OCR reference fields and marks and shows warnings for a fresh run", async () => {
    const user = userEvent.setup();
    const api = new ApiClient("test-token");
    let finishRecognition: ((result: Card & {
      recognition: { status: "completed"; error_key: null };
    }) => void) | undefined;
    vi.spyOn(api, "recognize").mockImplementation(() => new Promise((resolve) => {
      finishRecognition = resolve;
    }));
    const recognizedCard = {
      ...initialCard,
      revision: 3,
      fields: {
        ...initialCard.fields,
        course: { value: "100" },
        position: { value: "Brust" },
        name: { value: "OCR Name" },
        first_name: { value: "Anna" },
      },
      checkboxes: {
        female: { state: "unchecked" },
        male: { state: "checked" },
      },
      reference_check: {
        run_id: "run-2",
        warnings: {
          course: { expected: "100", detected: "25" },
          gender: { expected: "male", detected: null },
        },
      },
      recognition: { status: "completed", error_key: null },
    } as Card & { recognition: { status: "completed"; error_key: null } };
    const save = vi.spyOn(api, "patchCard").mockImplementation(async (_id, payload) => ({
      ...recognizedCard,
      revision: 4,
      fields: {
        ...recognizedCard.fields,
        ...Object.fromEntries(
          Object.entries(payload.fields ?? {}).map(([key, value]) => [key, { value }]),
        ),
      },
      checkboxes: {
        ...recognizedCard.checkboxes,
        ...Object.fromEntries(
          Object.entries(payload.checkboxes ?? {}).map(([key, state]) => [key, { state }]),
        ),
      },
    }));

    function Harness() {
      const [current, setCurrent] = useState(initialCard);
      return (
        <NotificationProvider>
          <ReviewView
            api={api} card={current} pendingImage={null} pending={false}
            sessions={[session]} localImageBlob={null} t={t}
            onDirtyChange={vi.fn()} onCardUpdate={setCurrent}
            onApproved={vi.fn()} onBack={vi.fn()} onRetake={vi.fn()}
            onRetryCapture={vi.fn()} onMove={vi.fn()} onDelete={vi.fn()}
          />
        </NotificationProvider>
      );
    }

    render(<Harness />);
    await user.click(screen.getByRole("textbox", { name: "Strecke" }));
    await user.click(screen.getByRole("textbox", { name: "Name" }));
    expect(screen.queryByRole("button", { name: /erkannt: 50/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Texterkennung starten" }));
    await waitFor(() => expect(api.recognize).toHaveBeenCalled());
    fireEvent.change(screen.getByRole("textbox", { name: "Strecke" }), {
      target: { value: "25" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: "Name" }), {
      target: { value: "Manuell während OCR" },
    });
    await act(async () => {
      finishRecognition?.(recognizedCard);
      await Promise.resolve();
    });
    expect(await screen.findByRole("button", {
      name: "Wettkampf erwartet: 100. Auf der Karte erkannt: 25.",
    })).toBeInTheDocument();
    expect(screen.getByRole("button", {
      name: "Wettkampf erwartet: Männlich. Auf der Karte erkannt: nicht lesbar.",
    })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Strecke" })).toHaveValue("100");
    expect(screen.getByRole("textbox", { name: "Lage" })).toHaveValue("Brust");
    expect(screen.getByRole("textbox", { name: "Vorname" })).toHaveValue("Anna");
    expect(screen.getByRole("textbox", { name: "Name" })).toHaveValue("Manuell während OCR");
    expect(screen.getByRole("radio", { name: "Junge" })).toBeChecked();
    await waitFor(() => expect(save).toHaveBeenCalled());
    expect(save.mock.calls.at(-1)?.[1].fields).toEqual({
      course: "100",
      name: "Manuell während OCR",
    });
  });
});
