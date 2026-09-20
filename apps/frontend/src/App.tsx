import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiClient,
  type AdjustOutcomeView,
  type ApiError,
  type CaseRow,
  type SignalEnvelope,
  type TechniqueMode,
  type TechniqueResultView,
} from "./api/client";
import { AdjustDock } from "./components/AdjustDock";
import { AlignmentStrip } from "./components/AlignmentStrip";
import { SignalResults } from "./components/SignalResults";
import { TechniqueStrip } from "./components/TechniqueStrip";
import { DEFAULT_DIAMETER_MM, type AdjustToolId } from "./domain/adjustBindings";

function errorWords(error: unknown): string {
  if (error && typeof error === "object" && "detail" in error) {
    const detail = (error as ApiError).detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "message" in detail) {
      return String((detail as { message: unknown }).message);
    }
    return JSON.stringify(detail);
  }
  if (error instanceof Error) return error.message;
  return "The technique could not be run.";
}

export interface AppProps {
  readonly client?: ApiClient;
}

export function App({ client }: AppProps) {
  const api = useMemo(() => client ?? new ApiClient(), [client]);
  const [cases, setCases] = useState<readonly CaseRow[]>([]);
  const [caseId, setCaseId] = useState<string | null>(null);
  const [tooth, setTooth] = useState<number | null>(null);
  const [mode, setMode] = useState<TechniqueMode>("deterministic");
  const [tool, setTool] = useState<AdjustToolId>("best-fit");
  const [diameterMm, setDiameterMm] = useState(DEFAULT_DIAMETER_MM);
  const [signals, setSignals] = useState<SignalEnvelope | null>(null);
  const [result, setResult] = useState<TechniqueResultView | null>(null);
  const [outcome, setOutcome] = useState<AdjustOutcomeView | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const teeth = useMemo(() => {
    const selected = cases.find((row) => row.id === caseId);
    const fromSites = (selected?.suggested_sites ?? [])
      .map((site) => site.tooth)
      .filter((value): value is number => typeof value === "number");
    return fromSites;
  }, [cases, caseId]);

  useEffect(() => {
    let cancelled = false;
    api.listCases().then((rows) => {
      if (cancelled) return;
      setCases(rows);
      if (rows[0] !== undefined) {
        setCaseId(rows[0].id);
        const firstTooth = rows[0].suggested_sites[0]?.tooth;
        if (typeof firstTooth === "number") setTooth(firstTooth);
      }
    }, (err: unknown) => {
      if (!cancelled) setLoadError(errorWords(err));
    });
    return () => { cancelled = true; };
  }, [api]);

  const refreshSignals = useCallback(async (id: string, site: number) => {
    const envelope = await api.fetchSignals(id, site);
    setSignals(envelope);
    return envelope;
  }, [api]);

  useEffect(() => {
    if (caseId === null || tooth === null) return;
    let cancelled = false;
    refreshSignals(caseId, tooth).catch((err: unknown) => {
      if (!cancelled) setLoadError(errorWords(err));
    });
    return () => { cancelled = true; };
  }, [caseId, tooth, refreshSignals]);

  const runTechnique = useCallback(async () => {
    if (caseId === null || tooth === null) return;
    setBusy(true);
    setError(null);
    setRefusal(null);
    try {
      const payload = await api.postTechnique(caseId, tooth, {
        mode,
        apply: true,
        matching_diameter_mm: diameterMm,
      });
      setResult(payload);
      setSignals(payload.signals_after);
      setOutcome(payload.outcome);
      if (payload.status === "refused" && payload.refusals[0] !== undefined) {
        setRefusal(String(payload.refusals[0]["message"] ?? payload.detail));
      }
    } catch (err) {
      setError(errorWords(err));
    } finally {
      setBusy(false);
    }
  }, [api, caseId, tooth, mode, diameterMm]);

  const wrap = useCallback(async (act: () => Promise<{ outcome: AdjustOutcomeView }>) => {
    if (caseId === null || tooth === null) return;
    setBusy(true);
    setRefusal(null);
    try {
      const payload = await act();
      setOutcome(payload.outcome);
      await refreshSignals(caseId, tooth);
    } catch (err) {
      setRefusal(errorWords(err));
    } finally {
      setBusy(false);
    }
  }, [caseId, tooth, refreshSignals]);

  const landmarks = (signals?.groups["landmarks"]?.["items"] as { id: string }[] | undefined) ?? [];

  return (
    <div className="app" data-role="alignment-app">
      <header className="app__header">
        <h1>Alignment technique</h1>
        <p className="muted">
          Deterministic vs Intelligence, over the same adjust / MCP seam.
        </p>
      </header>

      {loadError !== null && (
        <p data-role="load-error" className="dock__refuse" role="alert">{loadError}</p>
      )}

      <div className="app__pickers">
        <label>
          Case
          <select
            data-role="case-select"
            value={caseId ?? ""}
            onChange={(event) => {
              const next = event.target.value || null;
              setCaseId(next);
              const row = cases.find((item) => item.id === next);
              const nextTooth = row?.suggested_sites[0]?.tooth;
              setTooth(typeof nextTooth === "number" ? nextTooth : null);
              setResult(null);
            }}
          >
            {cases.map((row) => (
              <option key={row.id} value={row.id}>{row.doctor}</option>
            ))}
          </select>
        </label>
        <label>
          Site
          <select
            data-role="tooth-select"
            value={tooth ?? ""}
            onChange={(event) => {
              setTooth(Number(event.target.value));
              setResult(null);
            }}
          >
            {teeth.map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        </label>
      </div>

      <AlignmentStrip caseId={caseId} tooth={tooth} signals={signals} />
      <TechniqueStrip
        mode={mode}
        onChangeMode={setMode}
        onRun={() => { void runTechnique(); }}
        busy={busy}
        disabled={caseId === null || tooth === null}
      />

      <div className="app__workspace">
        <AdjustDock
          tool={tool}
          onSelectTool={setTool}
          busy={busy}
          diameterMm={diameterMm}
          onChangeDiameter={setDiameterMm}
          onRotate={(step) => {
            if (caseId === null || tooth === null) return;
            void wrap(() => api.postRotation(caseId, tooth, { step_deg: step }));
          }}
          onResetRotation={() => {
            if (caseId === null || tooth === null) return;
            void wrap(() => api.postRotation(caseId, tooth, { reset: true }));
          }}
          onBestFit={(apply) => {
            if (caseId === null || tooth === null) return;
            void wrap(() => api.postBestFit(caseId, tooth, {
              matching_diameter_mm: diameterMm, apply,
            }));
          }}
          onRePreview={() => {
            if (caseId === null || tooth === null) return;
            void wrap(async () => {
              await api.postRePreview(caseId, tooth);
              return { outcome: outcome ?? {
                tooth, operation: "re-preview", detail: "re-read", applied: false,
              } };
            });
          }}
          landmarks={landmarks}
          lastOutcome={outcome}
          refusal={refusal}
        />
        <SignalResults result={result} error={error} />
      </div>
    </div>
  );
}
