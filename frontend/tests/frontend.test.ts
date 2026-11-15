import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClient, ApiError, establishToken, exportFileName } from "../src/api";
import { BrowserCamera } from "../src/camera";
import { DraftSaver } from "../src/draftSaver";
import { focusNextReviewControl, installSpaceButtonActivation } from "../src/keyboard";
import { translate } from "../src/localization";

describe("startup authentication", () => {
  it("calls default fetch with the browser global receiver for JSON and images", async () => {
    const fetcher = vi.fn(function (this: unknown) {
      if (this !== globalThis) throw new TypeError("Illegal invocation");
      return Promise.resolve(new Response(JSON.stringify({ ok: true })));
    });
    const originalFetch = globalThis.fetch;
    globalThis.fetch = fetcher;
    try {
      const unboundClient = { fetcher };
      expect(() => unboundClient.fetcher()).toThrow("Illegal invocation");

      const api = new ApiClient("local-token");
      await expect(api.request("/api/bootstrap")).resolves.toEqual({ ok: true });
      await expect(api.image("/api/cards/card-1/image")).resolves.toMatchObject({ size: 11 });
      expect(fetcher).toHaveBeenCalledTimes(3);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("keeps fallback errors keyed and preserves localized backend messages", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError("network"))
      .mockResolvedValueOnce(new Response("{}", { status: 500 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        error: "browser.export_drafts",
        message: "Bitte zuerst alle Karten freigeben.",
      }), { status: 409 }));
    const api = new ApiClient("local-token", fetcher);

    await expect(api.bootstrap()).rejects.toMatchObject({
      message: "", status: 0, key: "error.connection",
    });
    await expect(api.image("/api/cards/card-1/image")).rejects.toMatchObject({
      message: "", status: 500, key: "error.imageLoad",
    });
    await expect(api.exportSession("one")).rejects.toEqual(
      new ApiError("Bitte zuerst alle Karten freigeben.", 409, "browser.export_drafts"),
    );
  });

  it("stores the fragment token and removes it from the visible URL", () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    };
    const replaceUrl = vi.fn();

    const token = establishToken(
      { hash: "#secret-token", pathname: "/app/", search: "?mode=local" },
      storage,
      replaceUrl,
    );

    expect(token).toBe("secret-token");
    expect(storage.getItem("startkartenleser.apiToken")).toBe("secret-token");
    expect(replaceUrl).toHaveBeenCalledWith("/app/?mode=local");
  });

  it("adds the app token header to API and authenticated image requests", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true })))
      .mockResolvedValueOnce(new Response(new Blob(["image"])));
    const api = new ApiClient("local-token", fetcher);

    await api.request("/api/bootstrap");
    await api.image("/api/cards/card-1/image");

    expect(fetcher.mock.calls[0]?.[1]?.headers).toBeInstanceOf(Headers);
    expect(new Headers(fetcher.mock.calls[0]?.[1]?.headers).get("X-App-Token")).toBe("local-token");
    expect(new Headers(fetcher.mock.calls[1]?.[1]?.headers).get("X-App-Token")).toBe("local-token");
  });

  it("loads crop overlays from the authenticated card endpoint", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ width: 10, height: 20, overlays: [], error_key: null })),
    );
    const result = await new ApiClient("local-token", fetcher).overlays("card/one");

    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/cards/card%2Fone/overlays");
    expect(new Headers(fetcher.mock.calls[0]?.[1]?.headers).get("X-App-Token")).toBe("local-token");
    expect(result.width).toBe(10);
  });
});

describe("draft persistence", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("debounces changes and serializes edits made during an in-flight save", async () => {
    let resolveFirst: ((value: { revision: number }) => void) | undefined;
    const transport = vi.fn()
      .mockImplementationOnce(
        () =>
          new Promise<{ revision: number }>((resolve) => {
            resolveFirst = resolve;
          }),
      )
      .mockResolvedValueOnce({ revision: 3 });
    const states: string[] = [];
    const saver = new DraftSaver(1, transport, (state) => states.push(state), 200);

    saver.setField("name", "Müller");
    await vi.advanceTimersByTimeAsync(199);
    expect(transport).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(transport).toHaveBeenCalledTimes(1);
    expect(transport.mock.calls[0]).toEqual([1, { name: "Müller" }, {}]);

    saver.setField("name", "Schmidt");
    resolveFirst?.({ revision: 2 });
    await vi.waitFor(() => expect(transport).toHaveBeenCalledTimes(2));
    expect(transport.mock.calls[1]).toEqual([2, { name: "Schmidt" }, {}]);
    expect(saver.currentRevision).toBe(3);
    expect(saver.dirty).toBe(false);
    expect(states).toContain("saving");
    saver.dispose();
  });

  it("keeps edits dirty after a failed write and permits retry", async () => {
    const transport = vi
      .fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce({ revision: 2 });
    const states: string[] = [];
    const saver = new DraftSaver(1, transport, (state) => states.push(state));
    saver.setCheckbox("female", "unchecked");

    await expect(saver.flush()).rejects.toThrow("offline");
    expect(saver.dirty).toBe(true);
    expect(states.at(-1)).toBe("error");

    await expect(saver.flush()).resolves.toBe(2);
    expect(saver.dirty).toBe(false);
    expect(transport.mock.calls[1]).toEqual([1, {}, { female: "unchecked" }]);
    saver.dispose();
  });
});

describe("keyboard and camera lifecycle", () => {
  it("suppresses space repeats and does not carry activation to a newly focused button", () => {
    const first = document.createElement("button");
    const second = document.createElement("button");
    document.body.append(first, second);
    const firstAction = vi.fn();
    const secondAction = vi.fn();
    first.addEventListener("click", firstAction);
    second.addEventListener("click", secondAction);
    const uninstall = installSpaceButtonActivation();

    first.focus();
    first.dispatchEvent(new KeyboardEvent("keydown", { key: " ", bubbles: true }));
    first.dispatchEvent(new KeyboardEvent("keydown", { key: " ", bubbles: true, repeat: true }));
    second.focus();
    second.dispatchEvent(new KeyboardEvent("keyup", { key: " ", bubbles: true }));

    expect(firstAction).not.toHaveBeenCalled();
    expect(secondAction).not.toHaveBeenCalled();
    uninstall();
    first.remove();
    second.remove();
  });

  it("activates only the focused button after a single Space press", () => {
    const button = document.createElement("button");
    document.body.append(button);
    const action = vi.fn();
    button.addEventListener("click", action);
    const uninstall = installSpaceButtonActivation();

    button.focus();
    button.dispatchEvent(new KeyboardEvent("keydown", { key: " ", bubbles: true }));
    button.dispatchEvent(new KeyboardEvent("keyup", { key: " ", bubbles: true }));
    expect(action).toHaveBeenCalledTimes(1);

    uninstall();
    button.remove();
  });

  it("advances Enter focus in the same order as native Tab", () => {
    const root = document.createElement("form");
    const first = document.createElement("input");
    const second = document.createElement("button");
    first.dataset.reviewControl = "true";
    second.dataset.reviewControl = "true";
    root.append(first, second);
    document.body.append(root);

    expect(focusNextReviewControl(first, root)).toBe(true);
    expect(document.activeElement).toBe(second);
    root.remove();
  });

  it("requests ideal HD video without audio and stops every track", async () => {
    const track = {
      onended: null,
      stop: vi.fn(),
      getSettings: () => ({}),
    } as unknown as MediaStreamTrack;
    const stream = {
      getTracks: () => [track],
      getVideoTracks: () => [track],
    } as unknown as MediaStream;
    const mediaDevices = {
      getUserMedia: vi.fn().mockResolvedValue(stream),
    } as unknown as MediaDevices;
    const video = document.createElement("video");
    Object.defineProperties(video, {
      readyState: { configurable: true, value: HTMLMediaElement.HAVE_CURRENT_DATA },
      videoWidth: { configurable: true, value: 1920 },
      videoHeight: { configurable: true, value: 1080 },
    });
    vi.spyOn(video, "play").mockResolvedValue();
    const camera = new BrowserCamera(video, mediaDevices);

    await camera.start();
    expect(mediaDevices.getUserMedia).toHaveBeenCalledWith({
      video: { width: { ideal: 1920 }, height: { ideal: 1080 } },
      audio: false,
    });
    camera.stop();
    expect(track.stop).toHaveBeenCalledTimes(1);
    expect(video.srcObject).toBeNull();
  });
});

describe("export file name", () => {
  it("includes number, distance, stroke and gender as ASCII", () => {
    const t = (key: string, values?: Record<string, string | number>) => translate({}, key, values);
    const base = { id: "s", revision: 1, number: 3, distance_m: 100, stroke: "ruecken" };
    expect(exportFileName({ ...base, gender: "male" }, t)).toBe("wettkampf-3-100m-ruecken-maennlich.csv");
    expect(exportFileName({ ...base, gender: "female", stroke: "freistil" }, t)).toBe("wettkampf-3-100m-freistil-weiblich.csv");
    expect(exportFileName({ ...base, gender: "female", stroke: "Über Kraul" }, t)).toBe("wettkampf-3-100m-ueber-kraul-weiblich.csv");
  });
});
