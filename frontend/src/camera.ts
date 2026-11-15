export class BrowserCamera {
  private stream: MediaStream | null = null;
  private generation = 0;

  constructor(
    private readonly video: HTMLVideoElement,
    private readonly mediaDevices: MediaDevices | undefined = navigator.mediaDevices,
    private readonly onEnded: () => void = () => undefined,
  ) {}

  stop(): void {
    this.generation += 1;
    for (const track of this.stream?.getTracks() ?? []) {
      track.onended = null;
      track.stop();
    }
    this.stream = null;
    this.video.srcObject = null;
  }

  async start(deviceId?: string): Promise<void> {
    this.stop();
    const generation = this.generation;
    if (!this.mediaDevices?.getUserMedia) throw new Error("camera.unavailable");
    let stream: MediaStream;
    try {
      stream = await this.mediaDevices.getUserMedia({
        video: {
          ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
          width: { ideal: 1920 },
          height: { ideal: 1080 },
        },
        audio: false,
      });
      if (generation !== this.generation) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      this.stream = stream;
      this.video.srcObject = stream;
      for (const track of stream.getVideoTracks()) {
        track.onended = () => {
          if (generation !== this.generation) return;
          this.stop();
          this.onEnded();
        };
      }
      await this.video.play();
      if (generation !== this.generation) return;
      if (
        this.video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA ||
        !this.video.videoWidth ||
        !this.video.videoHeight
      ) {
        throw new Error("camera.captureError");
      }
    } catch (error) {
      if (generation !== this.generation) return;
      const name = error instanceof DOMException ? error.name : "";
      const key =
        name === "NotAllowedError" || name === "SecurityError"
          ? "camera.permission"
          : name === "NotFoundError" || name === "OverconstrainedError"
            ? "camera.missing"
            : name === "NotReadableError" || name === "AbortError"
              ? "camera.busy"
              : error instanceof Error && error.message === "camera.captureError"
                ? "camera.captureError"
                : "camera.unavailable";
      this.stop();
      throw new Error(key);
    }
  }

  capture(): Promise<Blob> {
    if (
      !this.video.videoWidth ||
      !this.video.videoHeight ||
      this.video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA
    ) {
      return Promise.reject(new Error("camera.captureError"));
    }
    const canvas = document.createElement("canvas");
    canvas.width = this.video.videoWidth;
    canvas.height = this.video.videoHeight;
    const context = canvas.getContext("2d");
    if (!context) return Promise.reject(new Error("camera.captureError"));
    context.drawImage(this.video, 0, 0, canvas.width, canvas.height);
    return new Promise((resolve, reject) => {
      canvas.toBlob(
        (blob) => (blob ? resolve(blob) : reject(new Error("camera.captureError"))),
        "image/jpeg",
        0.92,
      );
    });
  }
}

export function blobAsDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") resolve(reader.result);
      else reject(new Error("camera.fileError"));
    };
    reader.onerror = () => reject(new Error("camera.fileError"));
    reader.readAsDataURL(blob);
  });
}
