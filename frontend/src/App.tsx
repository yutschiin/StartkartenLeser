import {
  Box,
  Button,
  Card as MuiCard,
  CardActionArea,
  CardActions,
  CardContent,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Divider,
  FormControl,
  FormControlLabel,
  InputLabel,
  InputAdornment,
  IconButton,
  MenuItem,
  Radio,
  RadioGroup,
  Select,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import AddPhotoAlternateOutlinedIcon from "@mui/icons-material/AddPhotoAlternateOutlined";
import AddIcon from "@mui/icons-material/Add";
import CameraAltOutlinedIcon from "@mui/icons-material/CameraAltOutlined";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import DownloadOutlinedIcon from "@mui/icons-material/DownloadOutlined";
import DocumentScannerOutlinedIcon from "@mui/icons-material/DocumentScannerOutlined";
import VisibilityOffOutlinedIcon from "@mui/icons-material/VisibilityOffOutlined";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import ReplayIcon from "@mui/icons-material/Replay";
import SaveOutlinedIcon from "@mui/icons-material/SaveOutlined";
import VerifiedOutlinedIcon from "@mui/icons-material/VerifiedOutlined";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import { useCallback, type FocusEvent, type MouseEvent, useEffect, useLayoutEffect, useRef, useState } from "react";
import { PageLayout } from "./PageLayout";
import {
  ApiClient,
  ApiError,
  CARD_KEY,
  SESSION_KEY,
  TOKEN_KEY,
  establishToken,
  exportFileName,
  isClassified,
  sessionDisplayTitle,
} from "./api";
import { BrowserCamera, blobAsDataUrl } from "./camera";
import { de, type FrontendMessageKey } from "./catalog.de";
import { useNotify } from "./Notifications";
import { DraftSaver, type DraftState } from "./draftSaver";
import { focusNextReviewControl, installSpaceButtonActivation } from "./keyboard";
import { translate } from "./localization";
import type {
  Card,
  CardOverlays,
  CheckboxValue,
  FieldValue,
  MarkState,
  Session,
} from "./types";

type Screen = "overview" | "session" | "camera" | "review";
type TextFn = (
  key: string,
  values?: Record<string, string | number>,
) => string;

const routineFields = [
  "name",
  "first_name",
  "year",
  "heat",
  "lane",
  "time",
  "timekeeper",
] as const;
const markFields = ["female", "male"] as const;
const strokeOptions = [
  "freistil",
  "brust",
  "ruecken",
  "schmetterling",
  "lagen",
] as const;

function messageFromApi(error: unknown, t: TextFn): string {
  if (!(error instanceof ApiError)) return t("error.generic");
  if (error.status === 0) return t("error.connection");
  if (error.message) {
    return error.message;
  }
  if (error.key) {
    const translated = t(error.key);
    if (translated !== error.key) return translated;
  }
  if (error.status === 401 || error.status === 403) return t("error.auth");
  if (error.status === 404) return t("error.stale");
  return t("error.generic");
}

function fieldString(field: FieldValue | undefined): string {
  const value = field?.value;
  return value == null ? "" : String(value);
}

function checkboxState(box: CheckboxValue | undefined): MarkState {
  const candidate = box?.state ?? box?.value;
  if (candidate === "checked" || candidate === true) return "checked";
  if (candidate === "unchecked" || candidate === false) return "unchecked";
  return "unknown";
}

function provenanceLabel(value: unknown, t: TextFn): string {
  const known = value === "ocr" || value === "manual" || value === "user_edited";
  return t(`frontend.provenance.${known ? value : "unknown"}`);
}

function referenceWarningKey(cardId: string, runId: string, field: string): string {
  return `startkartenleser.referenceWarning:${encodeURIComponent(cardId)}:${encodeURIComponent(runId)}:${field}`;
}

function referenceValue(field: string, value: string | null, t: TextFn): string {
  if (value === null) return t("review.referenceUnreadable");
  if (field === "gender" && (value === "male" || value === "female")) {
    return t(`gender.${value}`);
  }
  return value;
}

function ReferenceWarningIcon({
  field,
  expected,
  detected,
  t,
}: {
  field: string;
  expected: string;
  detected: string | null;
  t: TextFn;
}) {
  const expectedValue = referenceValue(field, expected, t);
  const detectedValue = referenceValue(field, detected, t);
  const message = t("review.referenceWarning", {
    expected: expectedValue,
    detected: detectedValue,
  });
  return (
    <Tooltip title={message}>
      <IconButton
        size="small"
        color="warning"
        aria-label={message}
        data-reference-warning={field}
      >
        <WarningAmberOutlinedIcon fontSize="small" />
      </IconButton>
    </Tooltip>
  );
}

export function SharedEvidence({ candidates, t }: {
  candidates: Card["shared_candidates"];
  t: TextFn;
}) {
  const entries = Object.entries(candidates ?? {}).filter(
    (entry): entry is [string, { raw_text: string; provenance?: unknown }] =>
      typeof entry[1] === "object" &&
      entry[1] !== null &&
      "raw_text" in entry[1] &&
      typeof entry[1].raw_text === "string" &&
      entry[1].raw_text.length > 0,
  );
  if (entries.length === 0) return null;
  return (
    <Box component="section" aria-label={t("card.shared")}>
      <Typography fontWeight={650}>{t("card.shared")}</Typography>
      <Box component="dl" className="shared-evidence">
        {entries.map(([key, candidate]) => (
          <Box key={key}>
            <Typography component="dt" variant="caption">{t("review.ocrRaw")}</Typography>
            <Typography component="dd" sx={{ m: 0, whiteSpace: "pre-wrap" }}>
              {candidate.raw_text}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {t("review.provenance")}: {provenanceLabel(candidate.provenance, t)}
            </Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

function reviewed(card: Card): boolean {
  return card.state.toLowerCase() === "reviewed";
}

function useObjectUrl(blob: Blob | null): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!blob) {
      setUrl(null);
      return;
    }
    const nextUrl = URL.createObjectURL(blob);
    setUrl(nextUrl);
    return () => URL.revokeObjectURL(nextUrl);
  }, [blob]);
  return url;
}

export default function App() {
  const [api, setApi] = useState<ApiClient | null>(null);
  const [texts, setTexts] = useState<Record<string, string>>({});
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSession, setActiveSession] = useState<Session | null>(null);
  const [cards, setCards] = useState<Card[]>([]);
  const [activeCard, setActiveCard] = useState<Card | null>(null);
  const [screen, setScreen] = useState<Screen>("overview");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const notify = useNotify();
  const notifiedErrorRef = useRef("");
  const resetRecoveryRef = useRef<() => void>(() => undefined);
  const [pendingImage, setPendingImage] = useState<string | null>(null);
  const [retakeTarget, setRetakeTarget] = useState<Card | null>(null);
  const [recoverable, setRecoverable] = useState(false);
  const [recoverStale, setRecoverStale] = useState(false);
  const [dialog, setDialog] = useState<"deleteSession" | "deleteCard" | "retake" | null>(null);
  const [imageBlob, setImageBlob] = useState<Blob | null>(null);
  const [autoRecognizeCardId, setAutoRecognizeCardId] = useState<string | null>(null);
  const [reviewResetKey, setReviewResetKey] = useState(0);
  const [authEpoch, setAuthEpoch] = useState(0);
  const pendingRequestRef = useRef<{ image: string; id: string } | null>(null);
  const currentDirtyRef = useRef(false);

  const t = useCallback<TextFn>(
    (key, values = {}) => {
      return translate(texts, key, values);
    },
    [texts],
  );
  const localize = useCallback(
    (reason: unknown) => messageFromApi(reason, t),
    [t],
  );

  const refreshBootstrap = useCallback(async (client: ApiClient) => {
    const bootstrap = await client.bootstrap();
    const backendTexts = Object.fromEntries(
      Object.entries(bootstrap.texts ?? {}).filter(
        (entry): entry is [string, string] => typeof entry[1] === "string",
      ),
    );
    setTexts(backendTexts);
    setSessions(bootstrap.sessions ?? []);
    return bootstrap;
  }, []);

  const loadSession = useCallback(
    async (client: ApiClient, session: Session): Promise<void> => {
      setBusy(true);
      setError("");
      try {
        const detail = await client.getSession(session.id);
        setActiveSession(detail.session);
        setSessions((items) => items.map((item) => item.id === detail.session.id ? detail.session : item));
        setCards(detail.cards);
        setActiveCard(null);
        setPendingImage(null);
        setScreen("session");
        sessionStorage.setItem(SESSION_KEY, session.id);
        sessionStorage.removeItem(CARD_KEY);
      } catch (reason) {
        setError(localize(reason));
        if (reason instanceof ApiError && reason.status === 404) {
          setRecoverable(true);
          setRecoverStale(true);
        }
      } finally {
        setBusy(false);
      }
    },
    [localize],
  );

  useEffect(() => {
    // A reused tab opening a new launch URL only changes the fragment.
    const onHashChange = () => {
      if (window.location.hash.length <= 1) return;
      if (currentDirtyRef.current) {
        setError(de["error.authDirty"]);
        return;
      }
      const previous = window.sessionStorage.getItem(TOKEN_KEY);
      const token = establishToken(
        window.location,
        window.sessionStorage,
        (url) => window.history.replaceState(null, "", url),
      );
      if (!token || token === previous) return;
      currentDirtyRef.current = false;
      pendingRequestRef.current = null;
      setApi(null);
      setTexts({});
      setSessions([]);
      setActiveSession(null);
      setCards([]);
      setActiveCard(null);
      setPendingImage(null);
      setRetakeTarget(null);
      setDialog(null);
      setImageBlob(null);
      setRecoverable(false);
      setRecoverStale(false);
      setError("");
      setBusy(false);
      setScreen("overview");
      setLoading(true);
      setAuthEpoch((epoch) => epoch + 1);
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const token = establishToken(
      window.location,
      window.sessionStorage,
      (url) => window.history.replaceState(null, "", url),
    );
    if (!token) {
      setLoading(false);
      setError(de["error.auth"]);
      return;
    }
    const client = new ApiClient(token);
    setApi(client);
    void (async () => {
      try {
        const bootstrap = await client.bootstrap();
        if (cancelled) return;
        const backendTexts = Object.fromEntries(
          Object.entries(bootstrap.texts ?? {}).filter(
            (entry): entry is [string, string] => typeof entry[1] === "string",
          ),
        );
        setTexts(backendTexts);
        setSessions(bootstrap.sessions ?? []);
        const sessionId = sessionStorage.getItem(SESSION_KEY);
        const cardId = sessionStorage.getItem(CARD_KEY);
        if (sessionId) {
          const known = (bootstrap.sessions ?? []).find((item) => item.id === sessionId);
          if (!known) {
            setError(de["error.stale"]);
            setRecoverable(true);
            setRecoverStale(true);
          } else {
            try {
              const detail = await client.getSession(sessionId);
              if (cancelled) return;
              setActiveSession(detail.session);
        setSessions((items) => items.map((item) => item.id === detail.session.id ? detail.session : item));
              setCards(detail.cards);
              if (cardId) {
                const card = await client.getCard(cardId);
                if (cancelled) return;
                if (card.session_id !== sessionId) throw new ApiError("", 404);
                setActiveCard(card);
                setScreen("review");
              } else {
                setScreen("session");
              }
            } catch (reason) {
              if (cancelled) return;
              setError(messageFromApi(reason, (key, values = {}) => {
                return translate(backendTexts, key, values);
              }));
              setRecoverable(true);
              setRecoverStale(true);
            }
          }
        }
      } catch (reason) {
        if (cancelled) return;
        setError(messageFromApi(reason, (key) => de[key as FrontendMessageKey] ?? key));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [authEpoch]);

  useEffect(() => installSpaceButtonActivation(), []);

  useEffect(() => {
    if (!error) {
      notifiedErrorRef.current = "";
      return;
    }
    if (loading || notifiedErrorRef.current === error) return;
    notifiedErrorRef.current = error;
    if (recoverable || recoverStale) {
      notify(recoverStale ? "warning" : "error", error, {
        key: "recover",
        timeoutMs: null,
        action: recoverable ? { label: t("action.recover"), onClick: resetRecoveryRef.current } : undefined,
      });
    } else {
      notify("error", error);
    }
  }, [error, loading, notify, recoverable, recoverStale, t]);

  useEffect(() => {
    if (!error) notify.dismiss("recover");
  }, [error, notify]);

  useEffect(() => {
    const onEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || document.querySelector('[role="dialog"]')) return;
      const targetId =
        screen === "review"
          ? "review-back"
          : screen === "camera"
            ? "camera-back"
            : null;
      if (!targetId) return;
      event.preventDefault();
      document.getElementById(targetId)?.click();
    };
    document.addEventListener("keydown", onEscape);
    return () => document.removeEventListener("keydown", onEscape);
  }, [screen]);

  useEffect(() => {
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!currentDirtyRef.current) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
    };
  }, []);

  useEffect(() => {
    if (!api || !activeCard) {
      setImageBlob(null);
      return;
    }
    let active = true;
    setImageBlob(null);
    void api
      .image(`/api/cards/${encodeURIComponent(activeCard.id)}/card-image`)
      .then((blob) => {
        if (active) setImageBlob(blob);
      })
      .catch((reason: unknown) => {
        if (active) setError(localize(reason));
      });
    return () => {
      active = false;
    };
  }, [api, activeCard?.id, reviewResetKey, localize]);

  const setCurrentCard = useCallback((card: Card | null) => {
    setActiveCard(card);
    if (card) sessionStorage.setItem(CARD_KEY, card.id);
    else sessionStorage.removeItem(CARD_KEY);
  }, []);

  const openSession = async (session: Session) => {
    if (!api) return;
    await loadSession(api, session);
  };

  const createSession = async (input: {
    number: number;
    distance_m: number;
    stroke: string;
    gender: string;
  }) => {
    if (!api) return;
    setBusy(true);
    setError("");
    try {
      const created = await api.createSession(input);
      const bootstrap = await api.bootstrap();
      setSessions(bootstrap.sessions);
      await loadSession(api, created);
    } catch (reason) {
      setError(localize(reason));
    } finally {
      setBusy(false);
    }
  };

  const openCard = async (card: Card) => {
    if (!api) return;
    setBusy(true);
    setError("");
    try {
      const detail = await api.getCard(card.id);
      setCurrentCard(detail);
      setPendingImage(null);
      setImageBlob(null);
      setScreen("review");
    } catch (reason) {
      setError(localize(reason));
      if (reason instanceof ApiError && reason.status === 404) {
        setRecoverable(true);
        setRecoverStale(true);
      }
    } finally {
      setBusy(false);
    }
  };

  const navigateToOverview = async () => {
    if (currentDirtyRef.current) return;
    setActiveSession(null);
    setCards([]);
    setCurrentCard(null);
    setPendingImage(null);
    setRetakeTarget(null);
    setScreen("overview");
    setError("");
    sessionStorage.removeItem(SESSION_KEY);
    sessionStorage.removeItem(CARD_KEY);
  };

  const refreshCurrentSession = async () => {
    if (!api || !activeSession) return;
    try {
      const detail = await api.getSession(activeSession.id);
      setActiveSession(detail.session);
      setSessions((items) => items.map((item) => item.id === detail.session.id ? detail.session : item));
      setCards(detail.cards);
    } catch (reason) {
      setError(localize(reason));
    }
  };

  const startCamera = (replace?: Card) => {
    if (!activeSession || !isClassified(activeSession)) return;
    setError("");
    setRetakeTarget(replace ?? null);
    setScreen("camera");
  };

  const captureImage = async (dataUrl: string) => {
    if (!api || !activeSession) return;
    setError("");
    if (!pendingRequestRef.current || pendingRequestRef.current.image !== dataUrl) {
      pendingRequestRef.current = { image: dataUrl, id: crypto.randomUUID() };
    }
    setPendingImage(dataUrl);
    if (!retakeTarget) setImageBlob(null);
    setScreen("review");
    const target = retakeTarget;
    setBusy(true);
    try {
      const card = await api.capture({
        session_id: activeSession.id,
        request_id: pendingRequestRef.current.id,
        image: dataUrl,
        ...(target
          ? { replace_card_id: target.id, revision: target.revision }
          : {}),
      });
      setImageBlob(null);
      setAutoRecognizeCardId(card.id);
      setCurrentCard(card);
      setRetakeTarget(null);
      setPendingImage(null);
      pendingRequestRef.current = null;
      if (target) setReviewResetKey((current) => current + 1);
      await refreshCurrentSession();
    } catch (reason) {
      if (target) {
        setCurrentCard(target);
        setPendingImage(null);
        setRetakeTarget(null);
        setScreen("review");
      }
      setError(localize(reason));
      if (!target) setPendingImage(dataUrl);
    } finally {
      setBusy(false);
    }
  };

  const acceptCardImage = async (blob: Blob) => {
    try {
      await captureImage(await blobAsDataUrl(blob));
    } catch (reason) {
      setError(localize(reason));
    }
  };

  const deleteSession = async () => {
    if (!api || !activeSession) return;
    setBusy(true);
    try {
      await api.deleteSession(activeSession.id);
      setDialog(null);
      setActiveSession(null);
      setCards([]);
      setCurrentCard(null);
      setScreen("overview");
      sessionStorage.removeItem(SESSION_KEY);
      sessionStorage.removeItem(CARD_KEY);
      await refreshBootstrap(api);
    } catch (reason) {
      setError(localize(reason));
    } finally {
      setBusy(false);
    }
  };

  const deleteCard = async () => {
    if (!api || !activeCard) return;
    setBusy(true);
    try {
      await api.deleteCard(activeCard.id);
      setDialog(null);
      setCurrentCard(null);
      setScreen("session");
      await refreshCurrentSession();
    } catch (reason) {
      setError(localize(reason));
    } finally {
      setBusy(false);
    }
  };

  const exportSession = async () => {
    if (!api || !activeSession || !canExport) return;
    setBusy(true);
    setError("");
    try {
      const csv = await api.exportSession(activeSession.id);
      const url = URL.createObjectURL(csv);
      const link = document.createElement("a");
      link.href = url;
      link.download = exportFileName(activeSession, t);
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) {
      setError(localize(reason));
    } finally {
      setBusy(false);
    }
  };

  const moveCard = async (card: Card, destination: string) => {
    if (!api || !destination) return;
    setBusy(true);
    setError("");
    try {
      await api.move(card.id, card.revision, destination);
      const target = sessions.find((session) => session.id === destination);
      if (target) await loadSession(api, target);
      else await refreshCurrentSession();
    } catch (reason) {
      setError(localize(reason));
    } finally {
      setBusy(false);
    }
  };

  const classifiedSessions = sessions.filter(isClassified);
  const approvedCount = cards.filter(reviewed).length;
  const canExport =
    Boolean(activeSession && isClassified(activeSession)) &&
    cards.length > 0 &&
    cards.every(reviewed);
  const exportReason =
    cards.length === 0
      ? "session.exportEmpty"
      : cards.some((card) => !reviewed(card))
        ? "session.exportDrafts"
        : "";

  const resetRecovery = () => {
    setRecoverable(false);
    setRecoverStale(false);
    setError("");
    setScreen("overview");
    setActiveSession(null);
    setCards([]);
    setCurrentCard(null);
    sessionStorage.removeItem(SESSION_KEY);
    sessionStorage.removeItem(CARD_KEY);
  };
  resetRecoveryRef.current = resetRecovery;

  return (
    <>
      <Box className="app-shell">
        {loading && (
          <PageLayout title={t("app.title")} showBrand>
            <Box className="loading-panel" role="status">
              <CircularProgress aria-label={t("status.loading")} />
            </Box>
          </PageLayout>
        )}

        {!loading && screen === "overview" && (
          <Overview
            sessions={sessions}
            busy={busy}
            t={t}
            onCreate={createSession}
            onOpen={openSession}
          />
        )}

        {!loading && screen === "session" && activeSession && (
          <SessionView
            session={activeSession}
            cards={cards}
            classifiedSessions={classifiedSessions}
            busy={busy}
            canExport={canExport}
            exportReason={exportReason ? t(exportReason) : ""}
            approvedCount={approvedCount}
            t={t}
            onBack={navigateToOverview}
            onOpenCard={openCard}
            onStartCamera={() => startCamera()}
            onDeleteSession={() => setDialog("deleteSession")}
            onDeleteCard={(card) => {
              setCurrentCard(card);
              setDialog("deleteCard");
            }}
            onExport={exportSession}
            onMove={moveCard}
          />
        )}

        {!loading && screen === "camera" && activeSession && (
          <CameraView
            api={api}
            session={activeSession}
            replace={retakeTarget}
            busy={busy}
            t={t}
            onCapture={acceptCardImage}
            onCancel={() => {
              setError("");
              if (retakeTarget) {
                setCurrentCard(retakeTarget);
                setRetakeTarget(null);
                setScreen("review");
              } else {
                setScreen("session");
              }
            }}
          />
        )}

        {!loading && screen === "review" && (
          <ReviewView
            key={`${activeCard?.id ?? "pending"}-${reviewResetKey}`}
            api={api}
            card={activeCard}
            session={activeSession}
            pendingImage={pendingImage}
            pending={busy && (!activeCard || Boolean(retakeTarget))}
            sessions={classifiedSessions}
            localImageBlob={imageBlob}
            autoRecognize={Boolean(activeCard) && activeCard?.id === autoRecognizeCardId}
            onAutoRecognizeStarted={() => setAutoRecognizeCardId(null)}
            t={t}
            onDirtyChange={(dirty) => {
              currentDirtyRef.current = dirty;
            }}
            onCardUpdate={(card) => {
              setCurrentCard(card);
              setCards((items) =>
                items.map((item) => (item.id === card.id ? card : item)),
              );
            }}
            onApproved={async () => {
              setCurrentCard(null);
              setPendingImage(null);
              setScreen("camera");
              await refreshCurrentSession();
            }}
            onBack={async () => {
              if (currentDirtyRef.current) return;
              setCurrentCard(null);
              setPendingImage(null);
              pendingRequestRef.current = null;
              setScreen("session");
              await refreshCurrentSession();
            }}
            onRetake={(card) => {
              if (card) {
                setRetakeTarget(card);
                setDialog("retake");
              }
              else startCamera();
            }}
            onRetryCapture={() => {
              if (pendingImage) void captureImage(pendingImage);
            }}
            onMove={moveCard}
            onDelete={() => setDialog("deleteCard")}
          />
        )}
        <Dialog
          open={dialog !== null}
          onClose={() => {
            setDialog(null);
            if (dialog === "deleteCard" && screen === "session") setCurrentCard(null);
            if (dialog === "retake") {
              setRetakeTarget(null);
              window.setTimeout(
                () => document.getElementById("retake-card")?.focus(),
                0,
              );
            }
          }}
          aria-labelledby="confirm-title"
        >
          <DialogTitle id="confirm-title">
            {dialog === "deleteSession"
              ? t("frontend.session.delete")
              : dialog === "retake"
                ? t("review.retakeConfirm")
                : t("card.delete")}
          </DialogTitle>
          <DialogContent>
            <DialogContentText>
              {dialog === "deleteSession"
                ? t("session.deleteConfirm")
                : dialog === "retake"
                  ? t("camera.retakeConfirm")
                  : t("card.deleteConfirm")}
            </DialogContentText>
          </DialogContent>
          <DialogActions>
            <Button
              onClick={() => {
                setDialog(null);
                if (dialog === "deleteCard" && screen === "session") setCurrentCard(null);
                if (dialog === "retake") {
                  setRetakeTarget(null);
                  window.setTimeout(
                    () => document.getElementById("retake-card")?.focus(),
                    0,
                  );
                }
              }}
            >
              {t("action.cancel")}
            </Button>
            <Button
              color={dialog === "deleteSession" ? "error" : "primary"}
              variant="contained"
              disabled={busy}
              onClick={() => {
                if (dialog === "deleteSession") void deleteSession();
                else if (dialog === "retake") {
                  setDialog(null);
                  if (retakeTarget || activeCard) startCamera(retakeTarget ?? activeCard!);
                } else void deleteCard();
              }}
            >
              {dialog === "deleteSession"
                ? t("action.delete")
                : dialog === "retake"
                  ? t("camera.replace")
                  : t("action.delete")}
            </Button>
          </DialogActions>
        </Dialog>

        <Box component="footer" className="footer-hint">
          {t("keyboard.hint")}
        </Box>
      </Box>
    </>
  );
}

interface OverviewProps {
  sessions: Session[];
  busy: boolean;
  t: TextFn;
  onCreate: (input: {
    number: number;
    distance_m: number;
    stroke: string;
    gender: string;
  }) => Promise<void>;
  onOpen: (session: Session) => Promise<void>;
}

function Overview({ sessions, busy, t, onCreate, onOpen }: OverviewProps) {
  const [createOpen, setCreateOpen] = useState(false);
  const [number, setNumber] = useState("");
  const [distance, setDistance] = useState("");
  const [stroke, setStroke] = useState("freistil");
  const [gender, setGender] = useState("female");

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    void onCreate({ number: Number(number), distance_m: Number(distance), stroke, gender });
  };

  return (
    <PageLayout title={t("app.title")} showBrand
      chips={<Chip label={t("session.list") + " · " + sessions.length} variant="outlined" />}
      actions={<Button variant="contained" startIcon={<AddIcon />} disabled={busy} onClick={() => setCreateOpen(true)}>{t("overview.add")}</Button>}
    >
      <Stack spacing={2} className="overview">
        {sessions.length === 0 ? (
          <MuiCard className="empty-card"><CardContent><Typography color="text.secondary">{t("session.empty")}</Typography></CardContent></MuiCard>
        ) : sessions.map((session) => (
          <MuiCard key={session.id} className="session-card">
            <CardActionArea disabled={busy} onClick={() => void onOpen(session)}>
              <CardContent className="session-row">
                <Box className={isClassified(session) ? "status-dot good" : "status-dot"} />
                <Box sx={{ flex: 1 }}>
                  {!isClassified(session) && <Typography variant="caption" color="text.secondary">{t("session.legacy")}</Typography>}
                  <Typography variant="h2">{sessionDisplayTitle(session, t)}</Typography>
                  {session.created_at && <Typography variant="body2" color="text.secondary">{new Date(session.created_at).toLocaleString("de-DE")}</Typography>}
                  {!isClassified(session) && <Typography className="legacy-note" color="text.secondary">{t("session.legacyHelp")}</Typography>}
                </Box>
                {typeof session.card_count === "number" && <Chip label={t("session.count", { count: session.card_count })} variant="outlined" />}
              </CardContent>
            </CardActionArea>
          </MuiCard>
        ))}
      </Stack>
      <Dialog open={createOpen} onClose={() => { if (!busy) setCreateOpen(false); }} aria-labelledby="create-session-title" fullWidth maxWidth="sm">
        <DialogTitle id="create-session-title">{t("overview.add")}</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>{t("overview.createHelp")}</DialogContentText>
          <Box component="form" onSubmit={submit} className="create-form" id="create-session-form">
            <TextField
              label={t("session.number")}
              type="number"
              value={number}
              onChange={(event) => setNumber(event.target.value)}
              required
              inputProps={{ min: 1, step: 1 }}
            />
            <TextField
              label={t("session.distance")}
              type="number"
              value={distance}
              onChange={(event) => setDistance(event.target.value)}
              required
              inputProps={{ min: 1, step: 1 }}
            />
            <FormControl>
              <InputLabel id="create-stroke-label">{t("session.stroke")}</InputLabel>
              <Select
                label={t("session.stroke")}
                labelId="create-stroke-label"
                value={stroke}
                onChange={(event) => setStroke(event.target.value)}
              >
                {strokeOptions.map((option) => (
                  <MenuItem key={option} value={option}>
                    {t(`stroke.${option}`)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl>
              <InputLabel id="create-gender-label">{t("session.gender")}</InputLabel>
              <Select
                label={t("session.gender")}
                labelId="create-gender-label"
                value={gender}
                onChange={(event) => setGender(event.target.value)}
              >
                <MenuItem value="female">{t("gender.female")}</MenuItem>
                <MenuItem value="male">{t("gender.male")}</MenuItem>
              </Select>
            </FormControl>

          </Box>
        </DialogContent>
        <DialogActions>
          <Button disabled={busy} onClick={() => setCreateOpen(false)}>{t("action.cancel")}</Button>
            <Button
              type="submit" form="create-session-form"
              variant="contained"
              size="large"
              disabled={busy || !number || !distance}
              startIcon={busy ? <CircularProgress size={18} /> : <AddIcon />}
            >
              {t("session.createAction")}
            </Button>
        </DialogActions>
      </Dialog>
    </PageLayout>
  );
}

interface SessionViewProps {
  session: Session;
  cards: Card[];
  classifiedSessions: Session[];
  busy: boolean;
  canExport: boolean;
  exportReason: string;
  approvedCount: number;
  t: TextFn;
  onBack: () => void;
  onOpenCard: (card: Card) => Promise<void>;
  onStartCamera: () => void;
  onDeleteSession: () => void;
  onDeleteCard: (card: Card) => void;
  onExport: () => Promise<void>;
  onMove: (card: Card, destination: string) => Promise<void>;
}

function SessionView({
  session,
  cards,
  classifiedSessions,
  busy,
  canExport,
  exportReason,
  approvedCount,
  t,
  onBack,
  onOpenCard,
  onStartCamera,
  onDeleteSession,
  onDeleteCard,
  onExport,
  onMove,
}: SessionViewProps) {
  const classified = isClassified(session);
  const notify = useNotify();
  useEffect(() => {
    if (classified) return;
    notify("warning", t("session.legacyHelp"), { key: "legacy-session" });
    return () => notify.dismiss("legacy-session");
  }, [classified, notify, t]);
  return (
    <PageLayout title={sessionDisplayTitle(session, t)}
      back={{ label: t("session.backToOverview"), onClick: onBack }}
      chips={<Chip label={t("session.counts", { total: cards.length, reviewed: approvedCount })} variant="outlined" />}
      actions={
        <>
          <Button
            variant="contained"
            size="large"
            startIcon={<CameraAltOutlinedIcon />}
            disabled={!classified || busy}
            onClick={onStartCamera}
          >
            {t("camera.title")}
          </Button>
          <Button
            variant="outlined"
            startIcon={<DownloadOutlinedIcon />}
            disabled={!canExport || busy}
            title={exportReason}
            onClick={() => void onExport()}
          >
            {t("session.export")}
          </Button>
          <Button
            color="error"
            variant="outlined"
            startIcon={<DeleteOutlineIcon />}
            disabled={busy}
            onClick={onDeleteSession}
            aria-label={t("frontend.session.delete")}
          >
            {t("action.delete")}
          </Button>
        </>
      }
    >
      <Stack spacing={3.5} className="session-view">
        {classified && !canExport && (
          <Typography className="export-note" color="text.secondary">
            {exportReason}
          </Typography>
        )}
        <Box className="section-heading">
          <Typography variant="h2">{t("card.list")}</Typography>
        </Box>
        {cards.length === 0 ? (
          <MuiCard className="empty-card">
            <CardContent><Typography color="text.secondary">{t("card.empty")}</Typography></CardContent>
          </MuiCard>
        ) : (
          <Box className="card-grid">
            {cards.map((card) => (
              <CardTile
                key={card.id}
                card={card}
                session={session}
                sessions={classifiedSessions.filter((item) => item.id !== session.id)}
                busy={busy}
                t={t}
                onOpen={() => void onOpenCard(card)}
                onDelete={() => onDeleteCard(card)}
                onMove={(target) => void onMove(card, target)}
              />
            ))}
          </Box>
        )}
      </Stack>
    </PageLayout>
  );
}

function CardTile({
  card,
  session,
  sessions,
  busy,
  t,
  onOpen,
  onDelete,
  onMove,
}: {
  card: Card;
  session: Session;
  sessions: Session[];
  busy: boolean;
  t: TextFn;
  onOpen: () => void;
  onDelete: () => void;
  onMove: (destination: string) => void;
}) {
  const [destination, setDestination] = useState("");
  return (
    <MuiCard className="card-tile">
      <CardActionArea onClick={onOpen} disabled={busy}>
        <CardContent>
          <Stack direction="row" spacing={1} alignItems="center" mb={2}>
            {reviewed(card) ? (
              <CheckCircleIcon className="status-icon good" color="success" />
            ) : (
              <RadioButtonUncheckedIcon className="status-icon pending" color="warning" />
            )}
            <Typography component="h3" fontWeight={700}>{t("frontend.card.row", { number: card.sequence, state: t(`status.${card.state.toLowerCase()}`) })}</Typography>
          </Stack>
          <Box component="dl" className="card-details">
            {(["name", "first_name", "year", "gender", "heat", "lane", "time", "timekeeper"] as const).map((key) => (
              <Box key={key}>
                <Typography component="dt" variant="caption" color="text.secondary">
                  {t(key === "gender" ? "review.gender" : `field.${key}`)}
                </Typography>
                <Typography component="dd">
                  {key === "gender"
                    ? markFields.filter((mark) => checkboxState(card.checkboxes[mark]) === "checked")
                        .map((mark) => t(`field.${mark}`)).join(" · ") || "–"
                    : fieldString(card.fields[key]) || "–"}
                </Typography>
              </Box>
            ))}
          </Box>
        </CardContent>
      </CardActionArea>
      <CardActions className="card-secondary-actions" onClick={(event) => event.stopPropagation()}>
        {!isClassified(session) && (
          <>
            <FormControl size="small" className="move-select">
              <InputLabel>{t("card.move")}</InputLabel>
              <Select
                value={destination}
                label={t("card.move")}
                onChange={(event) => setDestination(event.target.value)}
              >
                {sessions.map((item) => (
                  <MenuItem value={item.id} key={item.id}>{sessionDisplayTitle(item, t)}</MenuItem>
                ))}
              </Select>
            </FormControl>
            <Button
              disabled={busy || !destination}
              onClick={() => onMove(destination)}
              variant="outlined"
            >
              {t("card.move")}
            </Button>
          </>
        )}
        <Button onClick={onDelete} color="error" disabled={busy} aria-label={t("card.delete")}>
          <DeleteOutlineIcon />
        </Button>
      </CardActions>
    </MuiCard>
  );
}

interface CameraViewProps {
  api: ApiClient | null;
  session: Session;
  replace: Card | null;
  busy: boolean;
  t: TextFn;
  onCapture: (blob: Blob) => Promise<void>;
  onCancel: () => void;
}

export function CameraView({
  session,
  replace,
  busy,
  t,
  onCapture,
  onCancel,
}: CameraViewProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const cameraRef = useRef<BrowserCamera | null>(null);
  const shutterRef = useRef<HTMLButtonElement | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [cameraError, setCameraError] = useState("");
  const notify = useNotify();
  useEffect(() => {
    if (!cameraError) return;
    notify("error", t(cameraError), { key: "camera-error" });
  }, [cameraError, notify, t]);
  const [cameraReady, setCameraReady] = useState(false);
  const [starting, setStarting] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const startAttemptRef = useRef(0);
  const shutterEnabled = cameraReady && !capturing && !busy;

  useLayoutEffect(() => {
    if (shutterEnabled) shutterRef.current?.focus();
  }, [shutterEnabled]);

  const start = useCallback(async () => {
    if (!cameraRef.current) return;
    const attempt = ++startAttemptRef.current;
    setStarting(true);
    setCameraError("");
    setCameraReady(false);
    try {
      await cameraRef.current.start();
      if (attempt !== startAttemptRef.current) return;
      setCameraReady(true);
    } catch (reason) {
      if (attempt !== startAttemptRef.current) return;
      setCameraError(reason instanceof Error ? reason.message : "camera.unavailable");
    } finally {
      if (attempt === startAttemptRef.current) setStarting(false);
    }
  }, []);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const camera = new BrowserCamera(video, navigator.mediaDevices, () => {
      setCameraReady(false);
      setCameraError("camera.disconnected");
    });
    cameraRef.current = camera;
    const onPageHide = () => camera.stop();
    window.addEventListener("pagehide", onPageHide);
    void start();
    return () => {
      startAttemptRef.current += 1;
      window.removeEventListener("pagehide", onPageHide);
      camera.stop();
      cameraRef.current = null;
    };
  }, [start]);

  const takePhoto = async () => {
    if (!cameraRef.current || !cameraReady || capturing || busy) return;
    setCapturing(true);
    try {
      const blob = await cameraRef.current.capture();
      cameraRef.current.stop();
      await onCapture(blob);
    } catch (reason) {
      setCameraError(reason instanceof Error ? reason.message : "camera.captureError");
      await start();
    } finally {
      setCapturing(false);
    }
  };

  const chooseFile = async (file?: File) => {
    if (!file) return;
    if (!["image/jpeg", "image/png"].includes(file.type)) {
      setCameraError("camera.fileError");
      return;
    }
    setCapturing(true);
    try {
      cameraRef.current?.stop();
      await onCapture(file);
    } catch {
      setCameraError("camera.fileError");
    } finally {
      setCapturing(false);
    }
  };

  return (
    <PageLayout title={replace ? t("camera.retake") : t("camera.title")}
      back={{ id: "camera-back", label: replace ? t("review.back") : t("session.back"), onClick: onCancel }}
      chips={<Chip label={sessionDisplayTitle(session, t)} variant="outlined" />}
    >
      <Stack spacing={2.5} className="camera-view">
        <Box className="camera-layout">
          <Box className="video-frame">
            <video ref={videoRef} autoPlay muted playsInline aria-label={t("camera.preview")} />
            {!cameraReady && (
              <Box className="video-overlay" role="status">
                {starting ? <CircularProgress /> : <CameraAltOutlinedIcon />}
                <Typography>{starting ? t("camera.starting") : t(cameraError || "camera.notReady")}</Typography>
              </Box>
            )}
          </Box>
          <Stack className="camera-controls" spacing={1.5}>
            <Typography variant="h2">{t("camera.title")}</Typography>
            <Typography color="text.secondary">{t(cameraReady ? "camera.ready" : "camera.cameraHelp")}</Typography>
            <Button
              ref={shutterRef}
              id="take-picture"
              variant="contained"
              size="large"
              startIcon={capturing ? <CircularProgress size={18} color="inherit" /> : <CameraAltOutlinedIcon />}
              disabled={!shutterEnabled}
              onClick={() => void takePhoto()}
            >
              {t(replace ? "camera.replace" : "camera.capture")}
            </Button>
            <Button
              startIcon={<ReplayIcon />}
              disabled={starting || cameraReady}
              onClick={() => void start()}
            >
              {t("camera.retry")}
            </Button>
            <Divider />
            <Typography variant="body2" color="text.secondary">{t("camera.fallback")}</Typography>
            <Button
              component="label"
              variant="outlined"
              startIcon={<AddPhotoAlternateOutlinedIcon />}
              disabled={capturing || busy}
            >
              {t("camera.file")}
              <input
                ref={fileRef}
                className="visually-hidden"
                type="file"
                accept="image/jpeg,image/png"
                aria-label={t("camera.file")}
                onChange={(event) => {
                  void chooseFile(event.target.files?.[0]);
                  event.target.value = "";
                }}
              />
            </Button>
          </Stack>
        </Box>
      </Stack>
    </PageLayout>
  );
}

// Selecting on focus covers Tab; the one-shot mouseup guard stops the click from clearing it.
let selectedByFocus = false;
const selectAllOnFocus = {
  onFocus: (event: FocusEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    selectedByFocus = true;
    event.target.select();
  },
  onMouseUp: (event: MouseEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    if (!selectedByFocus) return;
    selectedByFocus = false;
    event.preventDefault();
  },
  onKeyUp: () => {
    selectedByFocus = false;
  },
};

function ImageBusy({ text }: { text: string }) {
  return (
    <Box className="image-busy" role="status">
      <CircularProgress size={28} color="inherit" />
      <Typography>{text}</Typography>
    </Box>
  );
}

interface ReviewViewProps {
  session?: Session | null;
  api: ApiClient | null;
  card: Card | null;
  pendingImage: string | null;
  pending: boolean;
  sessions: Session[];
  localImageBlob: Blob | null;
  autoRecognize?: boolean;
  onAutoRecognizeStarted?: () => void;
  t: TextFn;
  onDirtyChange: (dirty: boolean) => void;
  onCardUpdate: (card: Card) => void;
  onApproved: () => Promise<void>;
  onBack: () => Promise<void>;
  onRetake: (card?: Card) => void;
  onRetryCapture: () => void;
  onMove: (card: Card, destination: string) => Promise<void>;
  onDelete: () => void;
}

export function ReviewView({
  session,
  api,
  card,
  pendingImage,
  pending,
  sessions,
  localImageBlob,
  autoRecognize = false,
  onAutoRecognizeStarted,
  t,
  onDirtyChange,
  onCardUpdate,
  onApproved,
  onBack,
  onRetake,
  onRetryCapture,
  onMove,
  onDelete,
}: ReviewViewProps) {
  const review = useCardDraft(api, card, t, onCardUpdate, onDirtyChange);
  const retakeRef = useRef<HTMLButtonElement | null>(null);
  const notify = useNotify();
  const [actionBusy, setActionBusy] = useState(false);
  const [recognizing, setRecognizing] = useState(false);
  const [overlayData, setOverlayData] = useState<CardOverlays | null>(null);
  const [overlayOpen, setOverlayOpen] = useState(true);
  const [acknowledgedWarnings, setAcknowledgedWarnings] = useState<Set<string>>(
    () => new Set(),
  );
  const autoStartedRef = useRef<string | null>(null);
  const imageBlob = useObjectUrl(localImageBlob);
  const imageUrl = pendingImage ?? imageBlob;
  const isLegacy = Boolean(card && !sessions.some((session) => session.id === card.session_id));
  const availableMoves = sessions.filter((session) => session.id !== card?.session_id);

  useLayoutEffect(() => {
    if (!pending && !recognizing) retakeRef.current?.focus();
  }, [card?.id, Boolean(pendingImage), pending, recognizing]);

  useEffect(() => {
    onDirtyChange(
      review.dirty || review.status === "saving" || review.status === "error",
    );
  }, [review.dirty, review.status, onDirtyChange]);

  const approve = async () => {
    if (!api || !card || actionBusy || recognizing || pending) return;
    setActionBusy(true);
    try {
      const revision = await review.flush();
      const approved = await api.approve(card.id, revision);
      review.acceptActionRevision(approved.revision);
      onCardUpdate(approved);
      onDirtyChange(false);
      await onApproved();
    } catch (reason) {
      notify("error", messageFromApi(reason, t));
    } finally {
      setActionBusy(false);
    }
  };

  const requestRetake = () => {
    if (!card) {
      onRetake();
      return;
    }
    void review.navigate(async () => {
      onRetake(review.savedCard() ?? card);
    });
  };

  const requestDelete = () => {
    void review.navigate(async () => onDelete());
  };

  const recognize = async () => {
    if (!api || !card || actionBusy || recognizing || pending) return;
    setRecognizing(true);
    review.pause(true);
    try {
      const revision = await review.flush();
      const before = review.editVersions();
      const result = await api.recognize(card.id, revision);
      review.applyRecognition(result, before);
      if (result.recognition?.error_key) {
        notify("error", t(result.recognition.error_key));
      } else if (result.recognition?.status === "partial") {
        notify("info", t("review.recognitionPartial"));
      } else if (result.recognition?.status === "completed") {
        notify("success", t("review.recognitionComplete"));
      } else if (result.recognition?.status) {
        notify("error", t("review.recognitionError"));
      }
    } catch (reason) {
      notify("error", messageFromApi(reason, t));
    } finally {
      review.pause(false);
      setRecognizing(false);
      void review.flush().catch(() => undefined);
    }
  };

  const toggleOverlays = async () => {
    if (!api || !card) return;
    if (overlayOpen) {
      setOverlayOpen(false);
      return;
    }
    if (!overlayData) {
      try {
        setOverlayData(await api.overlays(card.id));
      } catch (reason) {
        notify("error", messageFromApi(reason, t));
        return;
      }
    }
    setOverlayOpen(true);
  };

  const cardId = card?.id;
  const referenceCheck = card?.reference_check;
  const acknowledgeReferenceWarning = (field: "wk_number" | "course" | "position" | "gender") => {
    if (!cardId || !referenceCheck?.run_id || !referenceCheck.warnings[field]) return;
    const key = referenceWarningKey(cardId, referenceCheck.run_id, field);
    sessionStorage.setItem(key, "1");
    setAcknowledgedWarnings((current) => new Set(current).add(key));
  };
  const visibleReferenceWarning = (field: "wk_number" | "course" | "position" | "gender") => {
    const warning = referenceCheck?.warnings[field];
    if (!warning || !cardId || !referenceCheck?.run_id) return undefined;
    const key = referenceWarningKey(cardId, referenceCheck.run_id, field);
    if (acknowledgedWarnings.has(key)) return undefined;
    if (sessionStorage.getItem(key) === "1") return undefined;
    return warning;
  };
  useEffect(() => {
    if (!api || !cardId) return;
    let active = true;
    api.overlays(cardId).then(
      (data) => { if (active) setOverlayData(data); },
      () => { if (active) setOverlayOpen(false); },
    );
    return () => { active = false; };
  }, [api, cardId]);

  useEffect(() => {
    if (!autoRecognize || !cardId || pending || autoStartedRef.current === cardId) return;
    autoStartedRef.current = cardId;
    onAutoRecognizeStarted?.();
    void recognize();
    // recognize() reads the latest draft state; only a new eligible card may start it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRecognize, cardId, pending]);

  const cardWarning = card?.warning;
  useEffect(() => {
    if (!cardWarning) return;
    notify("warning", t(cardWarning), { key: "card-warning" });
    return () => notify.dismiss("card-warning");
  }, [cardWarning, cardId, notify, t]);

  const overlayErrorKey = overlayOpen ? overlayData?.error_key : null;
  useEffect(() => {
    if (!overlayErrorKey) return;
    notify("warning", t(overlayErrorKey), { key: "overlay-warning" });
    return () => notify.dismiss("overlay-warning");
  }, [overlayErrorKey, notify, t]);

  const moveRequired = isLegacy && availableMoves.length === 0 && !pending;
  useEffect(() => {
    if (!moveRequired) return;
    notify("info", t("legacy.moveRequired"), { key: "move-required" });
    return () => notify.dismiss("move-required");
  }, [moveRequired, notify, t]);

  const saveFailed = !card && !pending && Boolean(imageUrl);
  useEffect(() => {
    if (!saveFailed) return;
    notify("error", t("review.saveError"), { key: "capture-save-failed" });
    return () => notify.dismiss("capture-save-failed");
  }, [saveFailed, notify, t]);

  const draftError = review.error ? messageFromApi(review.error, t) : "";
  useEffect(() => {
    if (!draftError) return;
    notify("error", draftError, {
      key: "draft-save-failed",
      timeoutMs: null,
      action: { label: t("review.retrySave"), onClick: () => void review.retry() },
    });
    return () => notify.dismiss("draft-save-failed");
    // review.retry reads the latest draft state when invoked.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftError, notify, t]);

  const saveLabel = t(review.status === "pending" ? "review.unsaved" : `review.${review.status}`);
  const saveStatus = card && (
    <Chip
      icon={review.status === "saving" ? <CircularProgress size={14} /> : <SaveOutlinedIcon />}
      label={saveLabel}
      color={review.status === "error" ? "error" : review.status === "saved" ? "success" : "default"}
      variant={review.status === "saved" ? "filled" : "outlined"}
      aria-live="polite"
    />
  );
  const reviewActions = card && (
    <>
      <Button
        variant="outlined"
        startIcon={recognizing ? <CircularProgress size={18} color="inherit" /> : <DocumentScannerOutlinedIcon />}
        onClick={() => void recognize()}
        disabled={recognizing || actionBusy || pending}
      >
        {recognizing ? t("review.recognizing") : t("review.recognize")}
      </Button>
      <Button
        variant={overlayOpen ? "contained" : "outlined"}
        startIcon={overlayOpen ? <VisibilityOutlinedIcon /> : <VisibilityOffOutlinedIcon />}
        aria-pressed={overlayOpen}
        onClick={() => void toggleOverlays()}
        disabled={!imageUrl || pending}
      >
        {t(overlayOpen ? "review.overlaysOn" : "review.overlaysOff")}
      </Button>
      <Button
        color="error"
        variant="outlined"
        startIcon={<DeleteOutlineIcon />}
        onClick={requestDelete}
        disabled={pending || actionBusy || recognizing}
      >
        {t("card.delete")}
      </Button>
    </>
  );
  const layoutProps = {
    title: t("review.title"),
    back: { id: "review-back", label: t("review.back"), onClick: () => void (card ? review.navigate(onBack) : onBack()), disabled: recognizing },
    chips: <>{session && <Chip label={sessionDisplayTitle(session, t)} variant="outlined" />}{saveStatus}</>,
    actions: reviewActions,
    singleLine: true,
  };

  if (!card) {
    return (
      <PageLayout {...layoutProps}>
        <Stack spacing={2} className="review-view">
          {imageUrl && (
            <Box className="image-stage">
              <img className="source-image" src={imageUrl} alt={t("card.image")} />
              {pending && <ImageBusy text={t("review.processing")} />}
            </Box>
          )}
          {imageUrl && !pending && (
            <Button
              startIcon={<SaveOutlinedIcon />}
              variant="contained"
              onClick={onRetryCapture}
            >
              {t("action.retry")}
            </Button>
          )}
          <Button
            ref={retakeRef}
            id="retake-card"
            variant="outlined"
            startIcon={<ReplayIcon />}
            disabled={pending}
            onClick={requestRetake}
          >
            {t("camera.retake")}
          </Button>
        </Stack>
      </PageLayout>
    );
  }

  const fieldValue = (key: string) => review.values[key] ?? "";
  const validation = card.validation ?? {};

  return (
    <PageLayout {...layoutProps}>
      <Stack
        spacing={2.5}
        className="review-view"
        onKeyDown={(event) => {
          if (event.defaultPrevented) return;
          if (
            event.key === "Enter" &&
            event.ctrlKey &&
            !event.nativeEvent.isComposing
          ) {
            event.preventDefault();
            void approve();
          } else if (event.key === "s" && (event.ctrlKey || event.metaKey) && !recognizing) {
            event.preventDefault();
            void review.flush().catch((reason) => notify("error", messageFromApi(reason, t)));
          }
        }}
      >
        <Box className="review-layout">
          <Box component="section" className="image-panel" aria-label={t("card.image")}>
            <Typography variant="h2">{t("card.image")}</Typography>
            {imageUrl ? (
              <Box className="image-stage">
              {overlayOpen && overlayData && overlayData.overlays.length > 0 ? (
                <svg
                  className="source-svg"
                  viewBox={`0 0 ${overlayData.width} ${overlayData.height}`}
                  role="img"
                  aria-label={t("review.overlayImage")}
                >
                  <image href={imageUrl} x="0" y="0" width={overlayData.width} height={overlayData.height} />
                  {overlayData.overlays.map((overlay) => (
                    <polygon
                      key={`${overlay.region_key}-${overlay.label_key}`}
                      points={overlay.source_corners.map(([x, y]) => `${x},${y}`).join(" ")}
                      className="crop-polygon"
                    >
                      <title>{t(overlay.label_key)}</title>
                    </polygon>
                  ))}
                </svg>
              ) : (
                <img className="source-image" src={imageUrl} alt={t("card.image")} />
              )}
              {recognizing && <ImageBusy text={t("review.recognizingLocked")} />}
              {pending && !recognizing && <ImageBusy text={t("review.processing")} />}
              </Box>
            ) : (
              <Box className="image-placeholder" role="status">
                <CircularProgress size={26} />
                <Typography>{t("review.imageLoading")}</Typography>
              </Box>
            )}
            {overlayOpen && overlayData && overlayData.overlays.length === 0 && !overlayData.error_key && (
              <Typography color="text.secondary">{t("review.noOverlays")}</Typography>
            )}

            {isLegacy && availableMoves.length > 0 && !pending && (
              <MoveControl
                card={card}
                sessions={availableMoves}
                disabled={recognizing || actionBusy}
                t={t}
                onMove={async (target, destination) => {
                  await review.navigate(async () => {
                    await onMove({ ...target, revision: review.currentRevision() }, destination);
                  });
                }}
              />
            )}
          </Box>

          <Box component="form" className="review-form" onSubmit={(event) => event.preventDefault()} onKeyDown={(event) => {
            if (
              event.key === "Tab" &&
              !event.ctrlKey &&
              !event.metaKey &&
              event.target instanceof HTMLElement &&
              focusNextReviewControl(event.target, event.currentTarget, event.shiftKey)
            ) {
              event.preventDefault();
            } else if (
              event.key === "Enter" &&
              event.ctrlKey &&
              !event.nativeEvent.isComposing
            ) {
              event.preventDefault();
              void approve();
            } else if (event.key === "s" && (event.ctrlKey || event.metaKey) && !recognizing) {
              event.preventDefault();
              void review.flush().catch((reason) => notify("error", messageFromApi(reason, t)));
            } else if (
              event.key === "Enter" &&
              !event.ctrlKey &&
              !event.metaKey &&
              event.target instanceof HTMLInputElement
            ) {
              event.preventDefault();
              focusNextReviewControl(event.target, event.currentTarget);
            }
          }}>
            <Button
              ref={retakeRef}
              id="retake-card"
              data-review-control="true"
              variant="outlined"
              startIcon={<ReplayIcon />}
              disabled={actionBusy || recognizing || pending}
              onClick={requestRetake}
              sx={{ mb: 2 }}
            >
              {t("camera.retake")}
            </Button>
            <Box className="field-grid">
              {routineFields.slice(0, 3).map((field) => (
                <TextField
                  key={field}
                  className={`field-${field}`}
                  label={t(`field.${field}`)}
                  value={fieldValue(field)}
                  disabled={actionBusy || pending || recognizing}
                  error={Boolean(validation[field])}
                  helperText={validation[field] ? t("review.validation", { message: validation[field] }) : " "}
                  onChange={(event) => review.setField(field, event.target.value)}
                  onBlur={() => void review.flush().catch((reason) => notify("error", messageFromApi(reason, t)))}
                  inputProps={{
                    "data-review-control": true,
                    autoComplete: "off",
                    spellCheck: false,
                    ...selectAllOnFocus,
                  }}
                />
              ))}
              <Box className="marks-row">
                <Typography variant="caption">{t("review.gender")}</Typography>
                <Stack direction="row" alignItems="center">
                  <RadioGroup
                    row
                    aria-label={t("review.gender")}
                    value={
                      review.marks.female === "checked" && review.marks.male === "unchecked"
                        ? "female"
                        : review.marks.male === "checked" && review.marks.female === "unchecked"
                          ? "male"
                          : ""
                    }
                    onChange={(_event, value) => {
                      const male = value === "male";
                      review.setMark("female", male ? "unchecked" : "checked");
                      review.setMark("male", male ? "checked" : "unchecked");
                    }}
                    onBlur={(event: FocusEvent<HTMLDivElement>) => {
                      if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                        acknowledgeReferenceWarning("gender");
                      }
                      void review.flush().catch((reason) => notify("error", messageFromApi(reason, t)));
                    }}
                  >
                    {markFields.map((field) => (
                      <FormControlLabel
                        key={field}
                        value={field}
                        disabled={actionBusy || pending || recognizing}
                        label={t(`field.${field}`)}
                        control={<Radio slotProps={{ input: { tabIndex: 0, ...{ "data-review-control": true } } }} />}
                      />
                    ))}
                  </RadioGroup>
                  {visibleReferenceWarning("gender") && (
                    <ReferenceWarningIcon
                      field="gender"
                      {...visibleReferenceWarning("gender")!}
                      t={t}
                    />
                  )}
                </Stack>
                {!(
                  (review.marks.female === "checked" && review.marks.male === "unchecked") ||
                  (review.marks.male === "checked" && review.marks.female === "unchecked")
                ) && <Typography variant="caption" color="warning.main">{t("review.genderUnselected")}</Typography>}
              </Box>
              {(["course", "position", "wk_number", ...routineFields.slice(3)]).map((field) => (
                <TextField
                  key={field}
                  className={`field-${field}`}
                  label={t(`field.${field}`)}
                  value={fieldValue(field)}
                  disabled={actionBusy || pending || recognizing}
                  error={Boolean(validation[field])}
                  helperText={validation[field] ? t("review.validation", { message: validation[field] }) : " "}
                  onChange={(event) => review.setField(field, event.target.value)}
                  onBlur={() => {
                    if (field === "wk_number" || field === "course" || field === "position") {
                      acknowledgeReferenceWarning(field);
                    }
                    void review.flush().catch((reason) => notify("error", messageFromApi(reason, t)));
                  }}
                  InputProps={field === "wk_number" || field === "course" || field === "position"
                    ? {
                        endAdornment: visibleReferenceWarning(field) ? (
                          <InputAdornment position="end">
                            <ReferenceWarningIcon
                              field={field}
                              {...visibleReferenceWarning(field)!}
                              t={t}
                            />
                          </InputAdornment>
                        ) : undefined,
                      }
                    : undefined}
                  inputProps={{
                    "data-review-control": true,
                    autoComplete: "off",
                    spellCheck: false,
                    ...selectAllOnFocus,
                  }}
                />
              ))}
            </Box>

            <Stack direction="row" justifyContent="center" spacing={1.2} className="review-actions">
              <Button
                variant="contained"
                color="success"
                size="large"
                data-review-control="true"
                startIcon={actionBusy ? <CircularProgress size={18} color="inherit" /> : <VerifiedOutlinedIcon />}
                disabled={actionBusy || recognizing || pending || review.status === "error"}
                onClick={() => void approve()}
              >
                {t("review.approve")}
              </Button>
            </Stack>
          </Box>
        </Box>

      </Stack>
    </PageLayout>
  );
}

function MoveControl({
  card,
  sessions,
  disabled,
  t,
  onMove,
}: {
  card: Card;
  sessions: Session[];
  disabled: boolean;
  t: TextFn;
  onMove: (card: Card, destination: string) => Promise<void>;
}) {
  const [destination, setDestination] = useState("");
  return (
    <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems="center">
      <FormControl fullWidth>
        <InputLabel>{t("card.moveDialog")}</InputLabel>
        <Select
          value={destination}
          disabled={disabled}
          label={t("card.moveDialog")}
          onChange={(event) => setDestination(event.target.value)}
        >
          {sessions.map((session) => (
            <MenuItem key={session.id} value={session.id}>{sessionDisplayTitle(session, t)}</MenuItem>
          ))}
        </Select>
      </FormControl>
      <Button
        disabled={disabled || !destination}
        variant="contained"
        onClick={() => void onMove(card, destination)}
      >
        {t("card.moveConfirm")}
      </Button>
    </Stack>
  );
}

function useCardDraft(
  api: ApiClient | null,
  card: Card | null,
  t: TextFn,
  onCardUpdate: (card: Card) => void,
  onDirtyChange: (dirty: boolean) => void,
) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [marks, setMarks] = useState<Record<string, MarkState>>({});
  const [status, setStatus] = useState<DraftState>("saved");
  const [error, setError] = useState<unknown>(null);
  const saverRef = useRef<DraftSaver | null>(null);
  const versionsRef = useRef<Record<string, number>>({});
  const editVersionRef = useRef(0);
  const valuesRef = useRef(values);
  const marksRef = useRef(marks);
  const cardRef = useRef(card);
  const onCardUpdateRef = useRef(onCardUpdate);
  const onDirtyChangeRef = useRef(onDirtyChange);
  const textRef = useRef(t);
  valuesRef.current = values;
  marksRef.current = marks;
  cardRef.current = card;
  onCardUpdateRef.current = onCardUpdate;
  onDirtyChangeRef.current = onDirtyChange;
  textRef.current = t;

  useEffect(() => {
    if (!card) return;
    const initialValues = Object.fromEntries(
      [...routineFields, "wk_number", "course", "position"].map((key) => [
        key,
        fieldString(card.fields[key]),
      ]),
    );
    const initialMarks = Object.fromEntries(
      markFields.map((key) => [key, checkboxState(card.checkboxes[key])]),
    ) as Record<string, MarkState>;
    setValues(initialValues);
    setMarks(initialMarks);
    setStatus("saved");
    setError(null);
    versionsRef.current = {};
    editVersionRef.current = 0;
    const saver = new DraftSaver(
      card.revision,
      async (revision, fields, checkboxes) => {
        if (!api) throw new Error(textRef.current("error.connection"));
        try {
          const updated = await api.patchCard(card.id, {
            revision,
            ...(Object.keys(fields).length ? { fields } : {}),
            ...(Object.keys(checkboxes).length ? { checkboxes } : {}),
          });
          cardRef.current = updated;
          onCardUpdateRef.current(updated);
          setError(null);
          return { revision: updated.revision };
        } catch (reason) {
          setError(reason);
          throw reason;
        }
      },
      (nextStatus, reason) => {
        setStatus(nextStatus);
        if (reason) setError(reason);
        if (nextStatus === "saved") setError(null);
        onDirtyChangeRef.current(nextStatus !== "saved");
      },
    );
    saverRef.current = saver;
    return () => {
      saver.dispose();
      if (saverRef.current === saver) saverRef.current = null;
    };
  }, [card?.id, api]);

  const setField = (field: string, value: string) => {
    setValues((current) => ({ ...current, [field]: value }));
    editVersionRef.current += 1;
    versionsRef.current[field] = editVersionRef.current;
    saverRef.current?.setField(field, value);
    onDirtyChange(true);
  };
  const setMark = (field: string, value: MarkState) => {
    setMarks((current) => ({ ...current, [field]: value }));
    editVersionRef.current += 1;
    versionsRef.current[field] = editVersionRef.current;
    saverRef.current?.setCheckbox(field, value);
    onDirtyChange(true);
  };

  const flush = async (): Promise<number> => {
    setError(null);
    const revision = await saverRef.current?.flush();
    onDirtyChange(Boolean(saverRef.current?.dirty));
    return revision ?? card?.revision ?? 0;
  };

  const retry = async () => {
    const saver = saverRef.current;
    if (!saver || !api || !card) return;
    if (error instanceof ApiError && error.status === 409) {
      try {
        const latest = await api.getCard(card.id);
        saver.rebase(latest.revision);
        onCardUpdate({ ...latest });
      } catch (reason) {
        setError(reason);
        return;
      }
    }
    setError(null);
    try {
      await saver.flush();
      onDirtyChange(false);
    } catch (reason) {
      setError(reason);
    }
  };

  const navigate = async (action: () => Promise<void>) => {
    try {
      await flush();
      if (saverRef.current?.dirty) return;
      await action();
    } catch (reason) {
      setError(reason);
    }
  };

  const applyRecognition = (
    result: Card,
    versionsBefore: Record<string, number>,
  ) => {
    const newReference = Boolean(
      result.reference_check &&
      result.reference_check.run_id !== cardRef.current?.reference_check?.run_id,
    );
    const nextValues = { ...valuesRef.current };
    for (const [field, record] of Object.entries(result.fields ?? {})) {
      if (
        (newReference && (field === "wk_number" || field === "course" || field === "position")) ||
        ((versionsRef.current[field] ?? 0) <= (versionsBefore[field] ?? 0) &&
          !saverRef.current?.isFieldDirty(field))
      ) {
        const value = fieldString(record);
        nextValues[field] = value;
        if (
          newReference && (field === "wk_number" || field === "course" || field === "position") &&
          saverRef.current?.isFieldDirty(field)
        ) {
          saverRef.current.setField(field, value);
        }
      }
    }
    const nextMarks = { ...marksRef.current };
    for (const [field, record] of Object.entries(result.checkboxes ?? {})) {
      if (
        (newReference && (field === "female" || field === "male")) ||
        ((versionsRef.current[field] ?? 0) <= (versionsBefore[field] ?? 0) &&
          !saverRef.current?.isCheckboxDirty(field))
      ) {
        const value = checkboxState(record);
        nextMarks[field] = value;
        if (
          newReference && (field === "female" || field === "male") &&
          saverRef.current?.isCheckboxDirty(field)
        ) {
          saverRef.current.setCheckbox(field, value);
        }
      }
    }
    setValues(nextValues);
    setMarks(nextMarks);
    saverRef.current?.setRevision(result.revision);
    onCardUpdateRef.current(result);
    setError(null);
  };

  const editVersions = () => ({ ...versionsRef.current });
  const acceptActionRevision = (revision: number) => saverRef.current?.setRevision(revision);
  const pause = (paused: boolean) => saverRef.current?.setPaused(paused);
  const dirty = Boolean(saverRef.current?.dirty);

  return {
    values,
    marks,
    status,
    error,
    dirty,
    currentRevision: () =>
      saverRef.current?.currentRevision ?? cardRef.current?.revision ?? 0,
    savedCard: () => cardRef.current,
    setField,
    setMark,
    flush,
    retry,
    navigate,
    applyRecognition,
    editVersions,
    acceptActionRevision,
    pause,
  };
}
