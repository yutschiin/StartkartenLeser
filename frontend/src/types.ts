export type MarkState = "unknown" | "checked" | "unchecked";

export interface FieldValue {
  value?: string | null;
  state?: string;
  provenance?: string | null;
  confirmed?: boolean;
  raw_text?: string | null;
  raw_value?: string | null;
  [key: string]: unknown;
}

export interface CheckboxValue {
  state?: MarkState;
  value?: MarkState | boolean | null;
  provenance?: string | null;
  confirmed?: boolean;
  raw_text?: string | null;
  [key: string]: unknown;
}

export interface ReferenceWarning {
  expected: string;
  detected: string | null;
}

export interface ReferenceCheck {
  run_id: string;
  warnings: {
    wk_number?: ReferenceWarning;
    course?: ReferenceWarning;
    position?: ReferenceWarning;
    gender?: ReferenceWarning;
  };
}

export interface Session {
  card_count?: number;
  id: string;
  title?: string;
  created_at?: string;
  revision: number;
  number: number | null;
  distance_m: number | null;
  stroke: string | null;
  stroke_label?: string;
  gender: string | null;
}

export interface Card {
  id: string;
  session_id: string;
  sequence: number;
  state: string;
  revision: number;
  fields: Record<string, FieldValue>;
  checkboxes: Record<string, CheckboxValue>;
  shared_candidates?: Record<string, unknown> | unknown[];
  validation?: Record<string, string>;
  warning?: string | null;
  reference_check?: ReferenceCheck;
  [key: string]: unknown;
}

export interface Bootstrap {
  sessions: Session[];
  strokes: StrokeOption[];
  texts: Record<string, unknown>;
}

export interface StrokeOption {
  value: string;
  label: string;
}

export interface SessionDetail {
  session: Session;
  cards: Card[];
}

export interface CardOverlays {
  width: number;
  height: number;
  aligned?: boolean;
  overlays: Array<{
    region_key: string;
    label_key: string;
    source_corners: [number, number][];
  }>;
  error_key: string | null;
}

export interface ApiFailure {
  error?: string;
  message?: string;
}
