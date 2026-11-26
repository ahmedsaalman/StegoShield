import { type ReactNode, useEffect } from "react";

import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { ErrorAlert } from "../components/ErrorAlert";
import { FileDrop } from "../components/FileDrop";
import { ToolArt } from "../components/illustrations/ToolArt";
import { ImagePreview } from "../components/ImagePreview";
import { PageBody, PageHeader } from "../components/PageHeader";
import { StatusBadge } from "../components/StatusBadge";
import {
  api,
  type DetectorPoint,
  type EmbeddingAlgorithm,
  type LabAttacks,
  type LabDetectorComparison,
  type LabQuality,
  type LabResults,
  type LabRobustness,
  type RiskLevel,
} from "../lib/api";
import { formatDimensions, formatPercent, formatProbability } from "../lib/format";
import { LAB_OUTCOME_PRESENTATION, RISK_PRESENTATION } from "../lib/presentation";
import { COVER_ACCEPT, useCoverImage } from "../lib/useCoverImage";
import { type Request, type RequestState, useRequest } from "../lib/useRequest";
import { useAppState } from "../state/AppState";

/** Each demo processes the image many times, so the API caps Lab uploads at 1 MP. */
const LAB_MAX_PIXELS = 1_048_576;
const PAYLOADS = [5, 10, 25, 50];
const ALGORITHMS: EmbeddingAlgorithm[] = ["replacement", "matching"];
const LEVELS: RiskLevel[] = ["low", "medium", "high"];
const TEXTURES = ["all", "smooth", "textured"] as const;
const LOSSY_TRANSPORTS = new Set(["jpeg_q90", "jpeg_q75", "resize_50"]);
const ALGORITHM_LABELS: Record<EmbeddingAlgorithm, string> = { replacement: "Replacement", matching: "Matching (±1)" };
const VISIBLE_BELOW_DB = 40;
const AUC_FORMAT = new Intl.NumberFormat("en", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
const DB_FORMAT = new Intl.NumberFormat("en", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const SSIM_FORMAT = new Intl.NumberFormat("en", { minimumFractionDigits: 4, maximumFractionDigits: 4 });

export function LabPage() {
  const { meta } = useAppState();
  const results = useRequest<LabResults>();
  const runResults = results.run;
  useEffect(() => {
    void runResults((signal) => api.labResults(signal));
  }, [runResults]);

  const image = useCoverImage();
  const quality = useRequest<LabQuality>();
  const robustness = useRequest<LabRobustness>();
  const attacks = useRequest<LabAttacks>();
  const detector = useRequest<LabDetectorComparison>();

  const capacity = image.capacity.status === "success" ? image.capacity.data : null;
  const isTooLarge = capacity !== null && capacity.width * capacity.height > LAB_MAX_PIXELS;
  const isDetectorMissing = meta !== null && !meta.detector.available;
  const canRun = image.file !== null && capacity !== null && !isTooLarge;
  const isBusy = [quality, robustness, attacks, detector].some((demo) => demo.state.status === "loading");

  function run<T>(demo: Request<T>, call: (file: File, signal: AbortSignal) => Promise<T>) {
    if (!image.file) return;
    const file = image.file;
    void demo.run((signal) => call(file, signal));
  }

  function runAll() {
    run(quality, api.labQuality);
    run(robustness, api.labRobustness);
    run(attacks, api.labAttacks);
    if (!isDetectorMissing) run(detector, api.labDetectorComparison);
  }

  function chooseImage(file: File) {
    [quality, robustness, attacks, detector].forEach((demo) => demo.reset());
    image.choose(file);
  }

  return (
    <>
      <PageHeader
        eyebrow="Evaluate"
        art={<ToolArt name="lab" isAmbient />}
        title="Evaluation Lab"
        description="Check the claims yourself: saved results from images the detector never trained on, and four live experiments you can run on your own image."
      />
      <PageBody>
        <div className="stack-lg">
          <SavedResults state={results.state} />

          <Card
            step="Live demos"
            title="Run the experiments on your image"
            description="The same experiment code that produced the saved results, run on one image. Nothing is stored."
            footer={
              <>
                <span>{canRun ? "Run all four, or each demo on its own below." : "Choose an image to enable the demos."}</span>
                <Button
                  variant="primary"
                  size="sm"
                  icon="scan"
                  disabled={!canRun || isBusy}
                  isLoading={isBusy}
                  loadingLabel="Running…"
                  onClick={runAll}
                >
                  Run all demos
                </Button>
              </>
            }
          >
            {image.file ? (
              <ImagePreview
                file={image.file}
                alt="The image the demos run on"
                onRemove={image.clear}
                activity={isBusy ? "scanning" : null}
                details={
                  capacity && (
                    <span className="inline-stats">
                      <span>{formatDimensions(capacity.width, capacity.height)}</span>
                      <span>Lab limit 1 MP (e.g. 1024 × 1024)</span>
                    </span>
                  )
                }
              />
            ) : (
              <FileDrop
                label="Drop an image here or click to browse"
                hint="PNG, JPEG, BMP or WebP, up to 1024 × 1024 pixels. A detailed photo works best."
                accept={COVER_ACCEPT}
                icon="upload"
                onFile={chooseImage}
                error={image.fileError}
              />
            )}
            {isTooLarge && (
              <Alert tone="warning" title="This image is too large for the Lab">
                The demos process the image many times, so they accept at most 1 megapixel. Crop or scale it to 1024 ×
                1024 or smaller.
              </Alert>
            )}
            {image.capacity.status === "error" && <ErrorAlert error={image.capacity.error} />}
          </Card>

          <div className="lab-grid">
            <DemoCard
              title="Visual quality"
              description="How much hiding 5–50 % test data changes the picture."
              state={quality.state}
              canRun={canRun}
              onRun={() => run(quality, api.labQuality)}
              loadingLabel="Measuring…"
            >
              {(data) => <QualityResult data={data} />}
            </DemoCard>
            <DemoCard
              title="Transport robustness"
              description="Whether a hidden message survives common ways images are re-saved."
              state={robustness.state}
              canRun={canRun}
              onRun={() => run(robustness, api.labRobustness)}
              loadingLabel="Testing…"
            >
              {(data) => <RobustnessResult data={data} />}
            </DemoCard>
            <DemoCard
              title="Attacks"
              description="Wrong keys, tampering, cropping and a signature scan against a real hidden message."
              state={attacks.state}
              canRun={canRun}
              onRun={() => run(attacks, api.labAttacks)}
              loadingLabel="Attacking…"
            >
              {(data) => <AttacksResult data={data} />}
            </DemoCard>
            <DemoCard
              title="Detector comparison"
              description="The detector's score for your image, clean and with test data hidden each way."
              state={detector.state}
              canRun={canRun && !isDetectorMissing}
              onRun={() => run(detector, api.labDetectorComparison)}
              loadingLabel="Scoring… (~5 s)"
              notReady={
                isDetectorMissing ? "The detector isn't installed on this server, so this demo is unavailable." : null
              }
            >
              {(data) => <DetectorResult data={data} />}
            </DemoCard>
          </div>
        </div>
      </PageBody>
    </>
  );
}

// ---------------------------------------------------------------- saved results

function SavedResults({ state }: { state: RequestState<LabResults> }) {
  return (
    <Card
      step="Saved results"
      title="How it performed on held-out images"
      description={
        state.status === "success"
          ? `From ${state.data.held_out_covers} test images the detector never trained on (seed ${state.data.seed}).`
          : "From the held-out experiment runs."
      }
      footer={<span>Source: experiments/results/*.csv · full write-up in docs/results.md</span>}
    >
      {state.status === "loading" && <p className="text-muted">Loading saved results…</p>}
      {state.status === "error" && <ErrorAlert error={state.error} />}
      {state.status === "success" && <SavedResultsBody results={state.data} />}
    </Card>
  );
}

function SavedResultsBody({ results }: { results: LabResults }) {
  const validity = (level: RiskLevel, texture: (typeof TEXTURES)[number]) =>
    results.preflight_validity.find((row) => row.predicted_level === level && row.texture === texture);
  const low = validity("low", "all");
  const high = validity("high", "all");
  const lossy = results.robustness.filter((row) => LOSSY_TRANSPORTS.has(row.transport));
  const lossySafe = lossy.reduce((sum, row) => sum + row.failed_safely_rate * row.n_trials, 0);
  const lossyTotal = lossy.reduce((sum, row) => sum + row.n_trials, 0);

  return (
    <div className="stack-lg">
      <dl className="stats">
        <div>
          <dt>Held-out test images</dt>
          <dd>{results.held_out_covers}</dd>
        </div>
        <div>
          <dt>Rated Low, then detected</dt>
          <dd>{low ? `${formatPercent(low.actual_detection_rate * 100)} of ${low.n_trials}` : "—"}</dd>
        </div>
        <div>
          <dt>Rated High, then detected</dt>
          <dd>{high ? `${formatPercent(high.actual_detection_rate * 100)} of ${high.n_trials}` : "—"}</dd>
        </div>
        <div>
          <dt>Lossy transport failed safely</dt>
          <dd>{lossyTotal ? `${Math.round(lossySafe)} / ${lossyTotal}` : "—"}</dd>
        </div>
      </dl>

      <section className="stack-sm" aria-labelledby="lab-auc-heading">
        <h3 id="lab-auc-heading" className="subsection-title">
          Detector ROC-AUC by payload (0.5 = coin flip, 1.0 = perfect)
        </h3>
        <AucTable slices={results.detector} />
      </section>

      <section className="stack-sm" aria-labelledby="lab-validity-heading">
        <h3 id="lab-validity-heading" className="subsection-title">
          Pre-flight prediction vs how often the detector actually caught the message
        </h3>
        <ScrollTable label="Pre-flight validity">
          <thead>
            <tr>
              <th scope="col">Predicted risk</th>
              <th scope="col">All images</th>
              <th scope="col">Smooth images</th>
              <th scope="col">Textured images</th>
            </tr>
          </thead>
          <tbody>
            {LEVELS.map((level) => (
              <tr key={level}>
                <th scope="row">
                  <StatusBadge status={RISK_PRESENTATION[level]} />
                </th>
                {TEXTURES.map((texture) => {
                  const row = validity(level, texture);
                  return (
                    <td key={texture}>
                      {row ? `${formatPercent(row.actual_detection_rate * 100)} detected (n = ${row.n_trials})` : "—"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </ScrollTable>
      </section>

      <div className="lab-split">
        <section className="stack-sm" aria-labelledby="lab-robustness-heading">
          <h3 id="lab-robustness-heading" className="subsection-title">
            Transport robustness
          </h3>
          <ScrollTable label="Saved robustness results">
            <thead>
              <tr>
                <th scope="col">Transport</th>
                <th scope="col">Recovered</th>
                <th scope="col">Failed safely</th>
                <th scope="col">Unsafe</th>
              </tr>
            </thead>
            <tbody>
              {results.robustness.map((row) => (
                <tr key={row.transport}>
                  <th scope="row">{row.label}</th>
                  <td>{formatPercent(row.recovered_rate * 100)}</td>
                  <td>{formatPercent(row.failed_safely_rate * 100)}</td>
                  <td>{formatPercent(row.unsafe_rate * 100)}</td>
                </tr>
              ))}
            </tbody>
          </ScrollTable>
        </section>
        <section className="stack-sm" aria-labelledby="lab-quality-heading">
          <h3 id="lab-quality-heading" className="subsection-title">
            Visual quality (mean PSNR, higher is better)
          </h3>
          <ScrollTable label="Saved quality results">
            <thead>
              <tr>
                <th scope="col">Payload</th>
                {ALGORITHMS.map((algorithm) => (
                  <th key={algorithm} scope="col">
                    {ALGORITHM_LABELS[algorithm]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {PAYLOADS.map((payload) => (
                <tr key={payload}>
                  <th scope="row">{payload} %</th>
                  {ALGORITHMS.map((algorithm) => {
                    const row = results.quality.find(
                      (item) => item.algorithm === algorithm && Math.round(item.payload_percent) === payload,
                    );
                    return <td key={algorithm}>{row ? `${DB_FORMAT.format(row.psnr_mean_db)} dB` : "—"}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </ScrollTable>
        </section>
      </div>
    </div>
  );
}

function AucTable({ slices }: { slices: LabResults["detector"] }) {
  const columns = ALGORITHMS.flatMap((algorithm) =>
    (["pseudorandom", "sequential"] as const).map((layout) => ({ algorithm, layout })),
  );
  return (
    <ScrollTable label="Detector ROC-AUC by payload">
      <thead>
        <tr>
          <th scope="col">Payload</th>
          {columns.map(({ algorithm, layout }) => (
            <th key={`${algorithm}-${layout}`} scope="col">
              {ALGORITHM_LABELS[algorithm]}, {layout === "pseudorandom" ? "scattered" : "sequential"}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {PAYLOADS.map((payload) => (
          <tr key={payload}>
            <th scope="row">{payload} %</th>
            {columns.map(({ algorithm, layout }) => {
              const slice = slices.find(
                (item) =>
                  item.algorithm === algorithm &&
                  item.layout === layout &&
                  Math.round(item.payload_percent) === payload,
              );
              return (
                <td key={`${algorithm}-${layout}`}>
                  {slice ? (
                    <span className="score-cell">
                      <span>{AUC_FORMAT.format(slice.roc_auc)}</span>
                      <span className="influence" aria-hidden="true">
                        <span
                          className="influence__bar"
                          style={{ width: `${Math.max(0, (slice.roc_auc - 0.5) / 0.5) * 100}%` }}
                        />
                      </span>
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </ScrollTable>
  );
}

// ---------------------------------------------------------------- live demos

interface DemoCardProps<T> {
  title: string;
  description: string;
  state: RequestState<T>;
  canRun: boolean;
  onRun: () => void;
  loadingLabel: string;
  notReady?: string | null;
  children: (data: T) => ReactNode;
}

function DemoCard<T>({ title, description, state, canRun, onRun, loadingLabel, notReady = null, children }: DemoCardProps<T>) {
  return (
    <Card
      title={title}
      description={description}
      footer={
        <>
          <span>{state.status === "success" ? "Done" : notReady ? "Unavailable" : canRun ? "Ready" : "Waiting for an image"}</span>
          <Button
            variant="secondary"
            size="sm"
            disabled={!canRun}
            isLoading={state.status === "loading"}
            loadingLabel={loadingLabel}
            onClick={onRun}
          >
            {state.status === "success" ? "Run again" : "Run"}
          </Button>
        </>
      }
    >
      {notReady && <Alert tone="info">{notReady}</Alert>}
      {/* Only the result area is live, so screen readers announce results, not the whole card. */}
      <div role="status" aria-label={`${title} result`} className="stack">
        {!notReady && state.status === "idle" && <p className="text-muted">Choose an image above, then run this demo.</p>}
        {state.status === "loading" && <p className="text-muted">{loadingLabel}</p>}
        {state.status === "error" && <ErrorAlert error={state.error} />}
        {state.status === "success" && children(state.data)}
      </div>
    </Card>
  );
}

function QualityResult({ data }: { data: LabQuality }) {
  const worst = Math.min(...data.points.map((point) => point.psnr_db ?? Infinity));
  return (
    <div className="stack">
      <ScrollTable label="Quality on your image">
        <thead>
          <tr>
            <th scope="col">Payload</th>
            {ALGORITHMS.map((algorithm) => (
              <th key={algorithm} scope="col">
                {ALGORITHM_LABELS[algorithm]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {PAYLOADS.map((payload) => (
            <tr key={payload}>
              <th scope="row">{payload} %</th>
              {ALGORITHMS.map((algorithm) => {
                const point = data.points.find(
                  (item) => item.algorithm === algorithm && Math.round(item.payload_percent) === payload,
                );
                return (
                  <td key={algorithm}>
                    {point ? (
                      <span className="score-cell">
                        <span>{point.psnr_db === null ? "identical" : `${DB_FORMAT.format(point.psnr_db)} dB`}</span>
                        <span className="text-muted">SSIM {SSIM_FORMAT.format(point.ssim)}</span>
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </ScrollTable>
      <p className="text-muted">
        {Number.isFinite(worst) && worst > VISIBLE_BELOW_DB
          ? `Even the largest payload stays at ${DB_FORMAT.format(worst)} dB, well above the ~${VISIBLE_BELOW_DB} dB where changes start to be visible.`
          : `Below ~${VISIBLE_BELOW_DB} dB, changes may start to be visible.`}
      </p>
    </div>
  );
}

function RobustnessResult({ data }: { data: LabRobustness }) {
  return (
    <div className="stack">
      <ul className="outcome-list">
        {data.trials.map((trial) => (
          <li key={trial.transport}>
            <span>{trial.label}</span>
            <StatusBadge status={LAB_OUTCOME_PRESENTATION[trial.outcome]} />
          </li>
        ))}
      </ul>
      <p className="text-muted">
        A {data.message_bytes.toLocaleString("en")}-byte message. "Failed safely" is the intended result for lossy
        transport: nothing leaks, and the image must travel as the original PNG.
      </p>
    </div>
  );
}

function AttacksResult({ data }: { data: LabAttacks }) {
  return (
    <ul className="outcome-list">
      {data.trials.map((trial) => (
        <li key={trial.attack}>
          <span>{trial.description}</span>
          <StatusBadge status={LAB_OUTCOME_PRESENTATION[trial.outcome]} />
        </li>
      ))}
    </ul>
  );
}

function DetectorResult({ data }: { data: LabDetectorComparison }) {
  const pointFor = (algorithm: EmbeddingAlgorithm, payload: number) =>
    data.points.find((point) => point.algorithm === algorithm && Math.round(point.payload_percent) === payload);
  const cleanPoint: DetectorPoint = {
    algorithm: "matching",
    payload_percent: 0,
    probability: data.clean_probability,
    is_detected: data.clean_probability >= data.threshold,
  };
  return (
    <div className="stack">
      <ScrollTable label="Detector scores on your image">
        <thead>
          <tr>
            <th scope="col">Payload</th>
            {ALGORITHMS.map((algorithm) => (
              <th key={algorithm} scope="col">
                {ALGORITHM_LABELS[algorithm]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">Clean (as uploaded)</th>
            <td colSpan={2}>
              <ProbabilityCell point={cleanPoint} threshold={data.threshold} />
            </td>
          </tr>
          {PAYLOADS.map((payload) => (
            <tr key={payload}>
              <th scope="row">{payload} %</th>
              {ALGORITHMS.map((algorithm) => {
                const point = pointFor(algorithm, payload);
                return <td key={algorithm}>{point ? <ProbabilityCell point={point} threshold={data.threshold} /> : "—"}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </ScrollTable>
      <p className="text-muted">
        The marker on each bar is the decision threshold ({formatProbability(data.threshold)}). Replacement is caught at
        small payloads; matching usually passes until larger ones, which is why it is the default and why messages
        should stay small.
      </p>
    </div>
  );
}

function ProbabilityCell({ point, threshold }: { point: DetectorPoint; threshold: number }) {
  return (
    <span className="probability-cell">
      <span className="probability-cell__track" aria-hidden="true">
        <span
          className={point.is_detected ? "probability-cell__fill probability-cell__fill--flagged" : "probability-cell__fill"}
          style={{ width: `${Math.min(100, point.probability * 100)}%` }}
        />
        <span className="probability-cell__marker" style={{ left: `${threshold * 100}%` }} />
      </span>
      <span className="probability-cell__text">
        {formatProbability(point.probability)} · {point.is_detected ? "flagged" : "passes"}
      </span>
    </span>
  );
}

function ScrollTable({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="table-scroll" role="region" aria-label={label} tabIndex={0}>
      <table className="table">{children}</table>
    </div>
  );
}
