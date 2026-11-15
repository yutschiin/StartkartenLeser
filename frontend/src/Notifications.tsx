import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { Alert, Button, Snackbar } from "@mui/material";

type Severity = "success" | "info" | "warning" | "error";
export interface NotifyOptions {
  // null keeps the snackbar open until it is closed, dismissed by key or its action is used.
  timeoutMs?: number | null;
  key?: string;
  action?: { label: string; onClick: () => void };
}
type Notify = ((severity: Severity, message: string, options?: NotifyOptions) => void) & {
  dismiss: (key: string) => void;
};
type Notification = {
  severity: Severity; message: string; timeoutMs: number | null; id: number;
  key?: string; action?: NotifyOptions["action"];
};

const timeouts: Record<Severity, number> = { success: 5000, info: 5000, warning: 8000, error: 10000 };
const noop = Object.assign(() => undefined, { dismiss: () => undefined }) as Notify;
const NotifyContext = createContext<Notify>(noop);

export function useNotify(): Notify {
  return useContext(NotifyContext);
}

export function NotificationProvider({ children }: { children: ReactNode }) {
  const [queue, setQueue] = useState<Notification[]>([]);
  const [current, setCurrent] = useState<Notification>();
  const [open, setOpen] = useState(false);
  const [dismissal, setDismissal] = useState<{ key: string }>();
  const [notify] = useState<Notify>(() => {
    let nextId = 0;
    const enqueue = (severity: Severity, message: string, options?: NotifyOptions) => {
      const notification: Notification = {
        severity, message, id: nextId++, key: options?.key, action: options?.action,
        timeoutMs: options?.timeoutMs === undefined ? timeouts[severity] : options.timeoutMs,
      };
      setQueue((pending) => [
        ...pending.filter((item) => item.key === undefined || item.key !== notification.key),
        notification,
      ]);
    };
    return Object.assign(enqueue, {
      dismiss: (key: string) => {
        setQueue((pending) => pending.filter((item) => item.key !== key));
        setDismissal({ key });
      },
    });
  });

  useEffect(() => {
    if (dismissal && current?.key === dismissal.key) setOpen(false);
  }, [dismissal, current]);

  useEffect(() => {
    if (!queue.length) return;
    if (!current) {
      setCurrent(queue[0]);
      setQueue((pending) => pending.slice(1));
      setOpen(true);
    } else if (open) {
      setOpen(false);
    }
  }, [queue, current, open]);

  const urgent = current?.severity === "warning" || current?.severity === "error";

  return (
    <NotifyContext.Provider value={notify}>
      {children}
      <Snackbar
        className="notification-snackbar"
        key={current?.id}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        open={open}
        autoHideDuration={current?.timeoutMs ?? null}
        onClose={(_, reason) => { if (reason !== "clickaway") setOpen(false); }}
        TransitionProps={{ onExited: () => setCurrent(undefined) }}
      >
        <Alert
          severity={current?.severity}
          variant="filled"
          role={urgent ? "alert" : "status"}
          aria-live={urgent ? "assertive" : "polite"}
          onClose={() => setOpen(false)}
          action={current?.action && (
            <Button
              color="inherit"
              size="small"
              onClick={() => { current.action?.onClick(); setOpen(false); }}
            >
              {current.action.label}
            </Button>
          )}
        >
          {current?.message}
        </Alert>
      </Snackbar>
    </NotifyContext.Provider>
  );
}
