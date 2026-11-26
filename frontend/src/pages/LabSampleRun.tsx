import { useEffect, useId, useState } from "react";

import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { ErrorAlert } from "../components/ErrorAlert";
import { Meter } from "../components/Meter";
import { StatusBadge } from "../components/StatusBadge";
import { api, type LabSample, type LabSampleRun, type LabSamples, type SampleAlgorithmResult } from "../lib/api";
import { formatBytes, formatProbability } from "../lib/format";
import { RISK_PRESENTATION } from "../lib/presentation";
import { type LiveRunState, useLiveRuns } from "../lib/useLiveRuns";
import { useRequest } from "../lib/useRequest";

const DEFAULT_PAYLOAD_PERCENT = 10;
const MIN_PAYLOAD_PERCENT = 1;
const MAX_PAYLOAD_PERCENT = 50;
const SAMPLE_SIDE_PX = 512;
const PUBLIC_KEY_OVERHEAD_BYTES = 64;
const ALGORITHM_LABELS = { replacement: "LSB replacement", matching: "LSB matching (±1)" } as const;
const DB_FORMAT = new Intl.NumberFormat("en", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const SHARE_FORMAT = new Intl.NumberFormat("en", { style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2 });

type SampleState = LiveRunState<LabSampleRun>;

/** Approximate message size for a 512×512 sample (all built-in samples are that size). */
export function sampleMessageBytes(payloadPercent: number): number {
  const packetBytes = Math.floor((SAMPLE_SIDE_PX * SAMPLE_SIDE_PX * 3 * payloadPercent) / 100 / 8);
  return Math.max(1, packetBytes - PUBLIC_KEY_OVERHEAD_BYTES);
}

export function LabSampleRun({ isDetectorMissing }: { isDetectorMissing: boolean }) {
  const catalogue = useRequest<LabSamples>();
  const loadCatalogue = catalogue.run;
  useEffect(() => {
    void loadCatalogue((signal) => api.labSamples(signal));
  }, [loadCatalogue]);

  const [payloadPercent, setPayloadPercent] = useState(DEFAULT_PAYLOAD_PERCENT);
  const { states, isRunning, start, stop } = useLiveRuns<LabSampleRun>();
  const samples = catalogue.state.status === "success" ? catalogue.state.data.samples : [];
  const sliderId = useId();

  return (
    <>
      <Card
        step="Live sample run"
        title="What a hidden message is exposed to, photo by photo"
        description="Choose how much to hide. The Lab encrypts that much data and hides it in each built-in photo with both algorithms, live, then shows the pre-flight prediction, what the detector actually sees, and exactly which pixel values changed."
        footer={
          <>
            <span>
              {catalogue.state.status === "success"
                ? `${samples.length} photos the detector never trained on · ${catalogue.state.data.source}`
                : "Loading the built-in photos…"}
            </span>
            {isRunning ? (
              <Button variant="secondary" size="sm" icon="close" onClick={stop}>
                Stop
              </Button>
            ) : (
              <Button
                variant="primary"
                size="sm"
                icon="scan"
                disabled={samples.length === 0 || isDetectorMissing}
                onClick={() =>
                  void start(
                    samples.map((sample) => sample.id),
                    (id, signal) => api.labRunSample(id, payloadPercent, signal),
                  )
                }
              >
                Run on {samples.length || 8} photos
              </Button>
            )}
          </>
        }
      >
        {isDetectorMissing && (
          <Alert tone="info">The detector isn't installed on this server, so the sample run is unavailable.</Alert>
        )}
        {catalogue.state.status === "error" && <ErrorAlert error={catalogue.state.error} />}
        <div className="field">
          <label className="field__label" htmlFor={sliderId}>
            Payload size: {payloadPercent} % of each photo&apos;s hiding space
          </label>
          <p className="field__hint" id={`${sliderId}-hint`}>
            About {formatBytes(sampleMessageBytes(payloadPercent))} per photo. Small payloads are hard to detect; large
            ones are not.
          </p>
          <input
            id={sliderId}
            className="size-input__range"
            type="range"
            min={MIN_PAYLOAD_PERCENT}
            max={MAX_PAYLOAD_PERCENT}
            step={1}
            value={payloadPercent}
            disabled={isRunning}
            onChange={(event) => setPayloadPercent(Number(event.target.value))}
            aria-describedby={`${sliderId}-hint`}
            aria-valuetext={`${payloadPercent} percent, about ${formatBytes(sampleMessageBytes(payloadPercent))}`}
          />
        </div>
        <Scoreboard samples={samples} states={states} />
      </Card>

      {samples.length > 0 && (
        <ol className="sample-list" aria-label="Sample photos">
          {samples.map((sample, index) => (
            <SampleCard key={sample.id} index={index + 1} sample={sample} state={states[sample.id]} />
          ))}
        </ol>
      )}
    </>
  );
}

function Scoreboard({ samples, states }: { samples: LabSample[]; states: Record<string, SampleState> }) {
  const runs = samples.flatMap((sample) => {
    const state = states[sample.id];
    return state?.status === "done" ? [state.result] : [];
  });
  const started = samples.some((sample) => states[sample.id] !== undefined);
  if (!started) return null;

  const resultsFor = (algorithm: SampleAlgorithmResult["algorithm"]) =>
    runs.flatMap((run) => run.results.filter((result) => result.algorithm === algorithm));
  const flagged = (algorithm: SampleAlgorithmResult["algorithm"]) =>
    resultsFor(algorithm).filter((result) => result.is_detected).length;
  const all = runs.flatMap((run) => run.results);
  const meanGap = all.length
    ? all.reduce((sum, result) => sum + Math.abs(result.predicted_probability - result.actual_probability), 0) / all.length
    : null;
  const psnrs = all.map((result) => result.psnr_db).filter((value): value is number => value !== null);

  return (
    <div className="stack" role="status" aria-label="Sample run summary">
      <Meter
        label="Photos finished"
        value={samples.length ? runs.length / samples.length : 0}
        valueText={`${runs.length} of ${samples.length}`}
      />
      <dl className="stats">
        <div>
          <dt>Flagged with LSB replacement</dt>
          <dd>
            {flagged("replacement")} of {runs.length}
          </dd>
        </div>
        <div>
          <dt>Flagged with LSB matching</dt>
          <dd>
            {flagged("matching")} of {runs.length}
          </dd>
        </div>
        <div>
          <dt>Pre-flight vs detector, mean gap</dt>
          <dd>{meanGap === null ? "—" : `${Math.round(meanGap * 100)} points`}</dd>
        </div>
        <div>
          <dt>Lowest quality (PSNR)</dt>
          <dd>{psnrs.length ? `${DB_FORMAT.format(Math.min(...psnrs))} dB` : "—"}</dd>
        </div>
      </dl>
    </div>
  );
}

function SampleCard({ index, sample, state }: { index: number; sample: LabSample; state: SampleState | undefined }) {
  const titleId = useId();
  const matching =
    state?.status === "done" ? state.result.results.find((result) => result.algorithm === "matching") : null;
  return (
    <li className="sample-card" aria-labelledby={titleId}>
      <div className="sample-card__header">
        <span className="card__step">Photo {String(index).padStart(2, "0")}</span>
        <h3 id={titleId} className="subsection-title">
          {sample.title}
        </h3>
        <span className="tag">{sample.texture}</span>
        <span className="sample-card__status">{describeState(state)}</span>
      </div>
      <div className="sample-card__images">
        <figure>
          <div className="image-frame image-frame--overlay">
            <img src={sample.image_url} alt={`${sample.title}, original`} loading="lazy" />
            {state?.status === "running" && <span className="activity activity--scanning" aria-hidden="true" />}
          </div>
          <figcaption>Original</figcaption>
        </figure>
        <figure>
          <div className="image-frame">
            {matching ? (
              <img src={matching.stego_preview} alt={`${sample.title} with data hidden by LSB matching`} />
            ) : (
              <span className="sample-card__placeholder">—</span>
            )}
          </div>
          <figcaption>With hidden data (matching)</figcaption>
        </figure>
        <figure>
          <div className="image-frame image-frame--map">
            {matching ? (
              <img
                src={matching.change_map}
                alt={`Zoomed map of changed colour values in the centre of the photo; ${matching.changed_values.toLocaleString("en")} changed in total`}
              />
            ) : (
              <span className="sample-card__placeholder">—</span>
            )}
          </div>
          <figcaption>Changed values, centre 128 × 128 px zoomed (red, green, blue = channel)</figcaption>
        </figure>
      </div>
      <div role="status" aria-label={`${sample.title} result`}>
        {state?.status === "error" && <ErrorAlert error={state.error} />}
        {state?.status === "done" && <SampleResultTable run={state.result} />}
      </div>
    </li>
  );
}

function SampleResultTable({ run }: { run: LabSampleRun }) {
  return (
    <div className="stack-sm">
      <p className="text-muted">
        {formatBytes(run.message_bytes)} hidden ({run.payload_percent} % of the hiding space). Detector threshold{" "}
        {formatProbability(run.threshold)}.
      </p>
      <div className="table-scroll" role="region" aria-label="Exposure per algorithm" tabIndex={0}>
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Algorithm</th>
              <th scope="col">Pre-flight predicted</th>
              <th scope="col">Detector actually saw</th>
              <th scope="col">Quality</th>
              <th scope="col">Values changed</th>
            </tr>
          </thead>
          <tbody>
            {run.results.map((result) => (
              <tr key={result.algorithm}>
                <th scope="row">{ALGORITHM_LABELS[result.algorithm]}</th>
                <td>
                  <StatusBadge
                    status={RISK_PRESENTATION[result.predicted_level]}
                    value={formatProbability(result.predicted_probability)}
                  />
                </td>
                <td>
                  <span className={result.is_detected ? "verdict-text verdict-text--flagged" : "verdict-text"}>
                    {formatProbability(result.actual_probability)} · {result.is_detected ? "flagged" : "passes"}
                  </span>
                </td>
                <td>
                  {result.psnr_db === null ? "identical" : `${DB_FORMAT.format(result.psnr_db)} dB`} · SSIM{" "}
                  {result.ssim.toFixed(4)}
                </td>
                <td>
                  {result.changed_values.toLocaleString("en")} ({SHARE_FORMAT.format(result.changed_share)})
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function describeState(state: SampleState | undefined): string {
  switch (state?.status) {
    case "waiting":
      return "Waiting";
    case "running":
      return "Hiding and scoring…";
    case "done":
      return describeExposure(state.result);
    case "error":
      return "Failed";
    default:
      return "Not run yet";
  }
}

function describeExposure(run: LabSampleRun): string {
  const flagged = run.results.filter((result) => result.is_detected).map((result) => ALGORITHM_LABELS[result.algorithm]);
  if (flagged.length === 0) return "Not flagged by either algorithm";
  if (flagged.length === run.results.length) return "Flagged with both algorithms";
  return `Flagged with ${flagged.join(", ")} only`;
}
