export type DraftState = "saved" | "pending" | "saving" | "error";
export type DraftTransport = (
  revision: number,
  fields: Record<string, string>,
  checkboxes: Record<string, "unknown" | "checked" | "unchecked">,
) => Promise<{ revision: number }>;

export class DraftSaver {
  private revision: number;
  private fields: Record<string, string> = {};
  private checkboxes: Record<string, "unknown" | "checked" | "unchecked"> = {};
  private inFlight: Promise<number> | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private paused = false;
  private disposed = false;

  constructor(
    revision: number,
    private readonly transport: DraftTransport,
    private readonly onState: (state: DraftState, error?: unknown) => void,
    private readonly delay = 200,
  ) {
    this.revision = revision;
  }

  get currentRevision(): number {
    return this.revision;
  }

  get dirty(): boolean {
    return Object.keys(this.fields).length > 0 || Object.keys(this.checkboxes).length > 0;
  }

  isFieldDirty(key: string): boolean {
    return Object.hasOwn(this.fields, key);
  }

  isCheckboxDirty(key: string): boolean {
    return Object.hasOwn(this.checkboxes, key);
  }

  setField(key: string, value: string): void {
    this.fields[key] = value;
    this.changed();
  }

  setCheckbox(key: string, value: "unknown" | "checked" | "unchecked"): void {
    this.checkboxes[key] = value;
    this.changed();
  }

  setRevision(revision: number): void {
    this.revision = revision;
  }

  setPaused(paused: boolean): void {
    this.paused = paused;
    if (!paused && this.dirty && !this.inFlight) this.schedule();
  }

  private changed(): void {
    if (this.disposed) return;
    this.onState("pending");
    if (!this.paused) this.schedule();
  }

  private schedule(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.flush().catch(() => undefined);
    }, this.delay);
  }

  async flush(): Promise<number> {
    if (this.disposed) throw new Error("Draft saver is no longer active");
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    if (this.inFlight) {
      await this.inFlight;
      return this.dirty ? this.flush() : this.revision;
    }
    if (!this.dirty) {
      this.onState("saved");
      return this.revision;
    }

    const sentFields = { ...this.fields };
    const sentCheckboxes = { ...this.checkboxes };
    this.onState("saving");
    const request = this.transport(
      this.revision,
      sentFields,
      sentCheckboxes,
    )
      .then(({ revision }) => {
        this.revision = revision;
        this.removeAcknowledged(this.fields, sentFields);
        this.removeAcknowledged(this.checkboxes, sentCheckboxes);
        this.onState(this.dirty ? "pending" : "saved");
        return revision;
      })
      .catch((error: unknown) => {
        this.onState("error", error);
        throw error;
      })
      .finally(() => {
        this.inFlight = null;
      });
    this.inFlight = request;
    const revision = await request;
    return this.dirty && !this.paused ? this.flush() : revision;
  }

  private removeAcknowledged<T extends string>(
    pending: Record<string, T>,
    sent: Record<string, T>,
  ): void {
    for (const [key, value] of Object.entries(sent)) {
      if (pending[key] === value) delete pending[key];
    }
  }

  rebase(revision: number): void {
    this.revision = revision;
    if (this.dirty) this.onState("pending");
  }

  dispose(): void {
    this.disposed = true;
    if (this.timer) clearTimeout(this.timer);
  }
}
