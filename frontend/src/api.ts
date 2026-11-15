import type {
  ApiFailure,
  Bootstrap,
  Card,
  CardOverlays,
  Session,
  SessionDetail,
} from "./types";

export const TOKEN_KEY = "startkartenleser.apiToken";
export const SESSION_KEY = "startkartenleser.selectedSession";
export const CARD_KEY = "startkartenleser.selectedCard";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly key?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function establishToken(
  location: Pick<Location, "hash" | "pathname" | "search">,
  storage: Pick<Storage, "getItem" | "setItem">,
  replaceUrl: (url: string) => void,
): string | null {
  let fragmentToken = "";
  if (location.hash.startsWith("#")) {
    try {
      fragmentToken = decodeURIComponent(location.hash.slice(1));
    } catch {
      fragmentToken = location.hash.slice(1);
    }
  }
  if (fragmentToken) {
    storage.setItem(TOKEN_KEY, fragmentToken);
    replaceUrl(`${location.pathname}${location.search}`);
    return fragmentToken;
  }
  return storage.getItem(TOKEN_KEY);
}

export class ApiClient {
  constructor(
    private readonly token: string,
    private readonly fetcher: typeof fetch = (...args) => globalThis.fetch(...args),
  ) {}

  async request<T>(
    path: string,
    init: RequestInit = {},
  ): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("X-App-Token", this.token);
    if (init.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    let response: Response;
    try {
      response = await this.fetcher(path, { ...init, headers });
    } catch {
      throw new ApiError("", 0, "error.connection");
    }
    if (!response.ok) {
      const payload = (await response.json().catch(() => ({}))) as ApiFailure;
      throw new ApiError(
        payload.message || "",
        response.status,
        payload.error,
      );
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  async image(path: string): Promise<Blob> {
    const response = await this.fetcher(path, {
      headers: { "X-App-Token": this.token },
    }).catch(() => {
      throw new ApiError("", 0, "error.connection");
    });
    if (!response.ok) {
      const payload = (await response.json().catch(() => ({}))) as ApiFailure;
      throw new ApiError(
        payload.message || "",
        response.status,
        payload.error || "error.imageLoad",
      );
    }
    return response.blob();
  }

  bootstrap(): Promise<Bootstrap> {
    return this.request("/api/bootstrap");
  }

  getSession(id: string): Promise<SessionDetail> {
    return this.request(`/api/sessions/${encodeURIComponent(id)}`);
  }

  getCard(id: string): Promise<Card> {
    return this.request(`/api/cards/${encodeURIComponent(id)}`);
  }

  createSession(input: {
    number: number;
    distance_m: number;
    stroke: string;
    gender: string;
  }): Promise<Session> {
    return this.request("/api/sessions", {
      method: "POST",
      body: JSON.stringify(input),
    });
  }

  deleteSession(id: string): Promise<void> {
    return this.request(`/api/sessions/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
  }

  deleteCard(id: string): Promise<void> {
    return this.request(`/api/cards/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
  }

  capture(input: {
    session_id: string;
    request_id: string;
    image: string;
    replace_card_id?: string;
    revision?: number;
  }): Promise<Card> {
    return this.request("/api/capture", {
      method: "POST",
      body: JSON.stringify(input),
    });
  }

  patchCard(
    id: string,
    payload: {
      revision: number;
      fields?: Record<string, string>;
      checkboxes?: Record<string, "unknown" | "checked" | "unchecked">;
    },
  ): Promise<Card> {
    return this.request(`/api/cards/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  }

  approve(id: string, revision: number): Promise<Card> {
    return this.request(`/api/cards/${encodeURIComponent(id)}/approve`, {
      method: "POST",
      body: JSON.stringify({ revision }),
    });
  }

  recognize(id: string, revision: number): Promise<Card & {
    recognition?: {
      status: "completed" | "partial" | "unavailable" | "failed" | "cancelled";
      error_key: string | null;
    };
  }> {
    return this.request(`/api/cards/${encodeURIComponent(id)}/recognize`, {
      method: "POST",
      body: JSON.stringify({ revision }),
    });
  }

  move(id: string, revision: number, session_id: string): Promise<Card> {
    return this.request(`/api/cards/${encodeURIComponent(id)}/move`, {
      method: "POST",
      body: JSON.stringify({ revision, session_id }),
    });
  }

  overlays(id: string): Promise<CardOverlays> {
    return this.request(`/api/cards/${encodeURIComponent(id)}/overlays`);
  }

  exportSession(id: string): Promise<Blob> {
    return this.image(`/api/sessions/${encodeURIComponent(id)}/export`);
  }
}

export function isClassified(session: Session): boolean {
  return (
    session.number !== null &&
    session.distance_m !== null &&
    Boolean(session.stroke) &&
    Boolean(session.gender)
  );
}

export function exportFileName(
  session: Session,
  text: (key: string, values?: Record<string, string | number>) => string,
  strokes: Array<{ value: string; label: string }> = [],
): string {
  const gender = text(`gender.${session.gender}`)
    .toLowerCase()
    .replace(/ä/g, "ae")
    .replace(/ö/g, "oe")
    .replace(/ü/g, "ue")
    .replace(/ß/g, "ss");
  const strokeKey = `stroke.${session.stroke}`;
  const translatedStroke = text(strokeKey);
  const strokeLabel = translatedStroke !== strokeKey
    ? session.stroke ?? "lage"
    : strokes.find((item) => item.value === session.stroke)?.label
      ?? session.stroke_label
      ?? session.stroke
      ?? "lage";
  const stroke = strokeLabel
    .toLowerCase()
    .replace(/ä/g, "ae")
    .replace(/ö/g, "oe")
    .replace(/ü/g, "ue")
    .replace(/ß/g, "ss")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "") || "lage";
  return `wettkampf-${session.number}-${session.distance_m}m-${stroke}-${gender}.csv`;
}

export function sessionDisplayTitle(
  session: Session,
  text: (key: string, values?: Record<string, string | number>) => string,
  strokes: Array<{ value: string; label: string }> = [],
): string {
  if (!isClassified(session)) return text("session.legacy");
  const strokeKey = `stroke.${session.stroke}`;
  const localizedStroke = text(strokeKey);
  const configuredStroke = session.stroke_label
    ?? strokes.find((item) => item.value === session.stroke)?.label;
  return text("wettkampf.title", {
    number: session.number as number,
    distance: session.distance_m as number,
    stroke: configuredStroke ?? (localizedStroke === strokeKey ? session.stroke ?? "" : localizedStroke),
    gender: text(`gender.${session.gender}`),
  });
}
