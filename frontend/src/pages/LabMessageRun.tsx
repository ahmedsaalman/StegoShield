import { useEffect, useId, useState } from "react";

import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { ChoiceGroup } from "../components/ChoiceGroup";
import { Disclosure } from "../components/Disclosure";
import { ErrorAlert } from "../components/ErrorAlert";
import { Meter } from "../components/Meter";
import { StatusBadge } from "../components/StatusBadge";
import {
  api,
  type EmbeddingAlgorithm,
  type LabMessageRun as MessageRun,
  type LabSampleText,
  type MessageAlgorithmResult,
} from "../lib/api";
import { describeFeature } from "../lib/features";
import { formatBytes, formatPercent, formatProbability } from "../lib/format";
import { LAB_OUTCOME_PRESENTATION, RISK_PRESENTATION } from "../lib/presentation";
import { type LiveRunState, useLiveRuns } from "../lib/useLiveRuns";
import { useRequest } from "../lib/useRequest";

const PUBLIC_KEY_OVERHEAD_BYTES = 64;
const PREVIEW_CHARACTERS = 320;
const NOTABLE_Z_SCORE = 1;
const ALGORITHM_LABELS: Record<EmbeddingAlgorithm, string> = {
  replacement: "LSB replacement",
  matching: "LSB matching (±1)",
};
const HIGHLIGHT_CHOICES = [
  { value: "matching" as const, label: "LSB matching (±1)", description: "The app's default." },
  { value: "replacement" as const, label: "LSB replacement", description: "Easier to detect." },
];
const DB_FORMAT = new Intl.NumberFormat("en", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const Z_FORMAT = new Intl.NumberFormat("en", { maximumFractionDigits: 1 });

interface ImageSize {
  width: number;
  height: number;
}

interface LabMessageRunProps {
  file: File | null;
  imageSize: ImageSize | null;
  canRun: boolean;
  isDetectorMissing: boolean;
}

/** Share of the image's hiding space a message of `bytes` fills (public-key mode). */
export function payloadShare(bytes: number, size: ImageSize): number {
  return ((bytes + PUBLIC_KEY_OVERHEAD_BYTES) * 8) / (size.width * size.height * 3);
}

export function LabMessageRun({ file, imageSize, canRun, isDetectorMissing }: LabMessageRunProps) {
  const texts = useRequest<{ texts: LabSampleText[] }>();
  const loadTexts = texts.run;
  useEffect(() => {
    void loadTexts((signal) => api.labTexts(signal));
  }, [loadTexts]);

  const runs = useLiveRuns<MessageRun>();
  const resetRuns = runs.reset;
  useEffect(() => resetRuns(), [file, resetRuns]);

  const [highlight, setHighlight] = useState<EmbeddingAlgorithm>("matching");
  const list = texts.state.status === "success" ? texts.state.data.texts : [];
  const isReady = canRun && !isDetectorMissing && list.length > 0 && file !== null;

  function runAll() {
    if (!file) return;
    const image = file;
    void runs.start(
      list.map((text) => text.id),
      (id, signal) => api.labRunMessage(id, image, signal),
    );
  }

  return (
    <>
      <Card
        step="Your image × sample messages"
        title="Hide each sample message in your image"
        description="Six built-in messages, from a one-line note to a long dossier. Each is encrypted and hidden in your image with both algorithms, then put through every test: detection, quality, and five safety checks. You see the text, the result, and exactly which pixels it changed."
        footer={
          <>
            <span>{file ? "Uses the image chosen above." : "Choose an image above first."}</span>
            {runs.isRunning ? (
              <Button variant="secondary" size="sm" icon="close" onClick={runs.stop}>
                Stop
              </Button>
            ) : (
              <Button variant="primary" size="sm" icon="scan" disabled={!isReady} onClick={runAll}>
                Run {list.length || 6} messages in your image
              </Button>
            )}
          </>
        }
      >
        {isDetectorMissing && (
          <Alert tone="info">The detector isn&apos;t installed on this server, so messages can&apos;t be scored.</Alert>
        )}
        {texts.state.status === "error" && <ErrorAlert error={texts.state.error} />}
        {list.length > 0 && <TextsTable texts={list} imageSize={imageSize} />}
        {list.length > 0 && (
          <Disclosure summary="Read the sample messages">
            <div className="stack">
              {list.map((text) => (
                <section key={text.id} className="stack-sm" aria-label={text.title}>
                  <h4 className="subsection-title">
                    {text.title} · {formatBytes(text.size_bytes)}
                  </h4>
                  <pre className="message-box message-box--compact" role="region" aria-label={`${text.title} text`} tabIndex={0}>
                    {text.text}
                  </pre>
                </section>
              ))}
            </div>
          </Disclosure>
        )}
        <ChoiceGroup
          name="lab-highlight"
          legend="Show highlights for"
          choices={HIGHLIGHT_CHOICES}
          value={highlight}
          onChange={setHighlight}
        />
        <MessageScoreboard texts={list} states={runs.states} />
      </Card>

      {Object.keys(runs.states).length > 0 && (
        <ol className="sample-list" aria-label="Sample messages in your image">
          {list.map((text) => (
            <MessageCard key={text.id} text={text} state={runs.states[text.id]} highlight={highlight} />
          ))}
        </ol>
      )}
    </>
  );
}

function TextsTable({ texts, imageSize }: { texts: LabSampleText[]; imageSize: ImageSize | null }) {
  return (
    <div className="table-scroll" role="region" aria-label="Sample messages" tabIndex={0}>
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Message</th>
            <th scope="col">Size</th>
            <th scope="col">Share of your image&apos;s hiding space</th>
          </tr>
        </thead>
        <tbody>
          {texts.map((text) => {
            const share = imageSize ? payloadShare(text.size_bytes, imageSize) : null;
            return (
              <tr key={text.id}>
                <th scope="row">
                  {text.title}
                  <span className="text-muted"> · {text.description}</span>
                </th>
                <td>{formatBytes(text.size_bytes)}</td>
                <td>{share === null ? "choose an image" : share > 1 ? "doesn't fit" : formatPercent(share * 100)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function MessageScoreboard({ texts, states }: { texts: LabSampleText[]; states: Record<string, LiveRunState<MessageRun>> }) {
  if (Object.keys(states).length === 0) return null;
  const runs = texts.flatMap((text) => {
    const state = states[text.id];
    return state?.status === "done" ? [state.result] : [];
  });
  const fitted = runs.filter((run) => run.fits);
  const flagged = (algorithm: EmbeddingAlgorithm) =>
    fitted.filter((run) => run.results.some((r) => r.algorithm === algorithm && r.is_detected)).length;
  const checks = fitted.flatMap((run) => run.results.flatMap((result) => result.checks));
  const passed = checks.filter((check) => check.outcome === check.expected).length;

  return (
    <div className="stack" role="status" aria-label="Message run summary">
      <Meter
        label="Messages finished"
        value={texts.length ? runs.length / texts.length : 0}
        valueText={`${runs.length} of ${texts.length}`}
      />
      <dl className="stats">
        <div>
          <dt>Flagged with LSB replacement</dt>
          <dd>
            {flagged("replacement")} of {fitted.length}
          </dd>
        </div>
        <div>
          <dt>Flagged with LSB matching</dt>
          <dd>
            {flagged("matching")} of {fitted.length}
          </dd>
        </div>
        <div>
          <dt>Safety checks as expected</dt>
          <dd>
            {passed} of {checks.length}
          </dd>
        </div>
        <div>
          <dt>Didn&apos;t fit</dt>
          <dd>{runs.length - fitted.length}</dd>
        </div>
      </dl>
    </div>
  );
}

interface MessageCardProps {
  text: LabSampleText;
  state: LiveRunState<MessageRun> | undefined;
  highlight: EmbeddingAlgorithm;
}

function MessageCard({ text, state, highlight }: MessageCardProps) {
  const titleId = useId();
  const run = state?.status === "done" ? state.result : null;
  const shown = run?.results.find((result) => result.algorithm === highlight) ?? null;
  const preview = text.text.length > PREVIEW_CHARACTERS ? `${text.text.slice(0, PREVIEW_CHARACTERS)}…` : text.text;

  return (
    <li className="sample-card" aria-labelledby={titleId}>
      <div className="sample-card__header">
        <span className="card__step">Message</span>
        <h3 id={titleId} className="subsection-title">
          {text.title}
        </h3>
        <span className="tag">{formatBytes(text.size_bytes)}</span>
        <span className="sample-card__status">{describeState(state)}</span>
      </div>
      <div className="message-layout">
        <figure className="message-layout__text">
          <pre className="message-box message-box--compact">{preview}</pre>
          <figcaption>The sample text that was hidden</figcaption>
        </figure>
        <ExposureFigure text={text} result={shown} isRunning={state?.status === "running"} />
      </div>
      <div role="status" aria-label={`${text.title} result`} className="stack">
        {state?.status === "error" && <ErrorAlert error={state.error} />}
        {run && !run.fits && (
          <Alert tone="warning" title="Doesn't fit in this image">
            This message is {formatBytes(run.message_bytes)} but your image holds at most{" "}
            {formatBytes(run.capacity_bytes)}. Use a larger image.
          </Alert>
        )}
        {run?.fits && shown && <WhyItMatters run={run} result={shown} />}
        {run?.fits && <ResultsTable run={run} />}
        {run?.fits && <ChecksTable results={run.results} />}
      </div>
    </li>
  );
}

function ExposureFigure({
  text,
  result,
  isRunning,
}: {
  text: LabSampleText;
  result: MessageAlgorithmResult | null;
  isRunning: boolean;
}) {
  return (
    <div className="exposure">
      <figure className="exposure__overview">
        <div className="image-frame image-frame--overlay exposure__frame">
          {result ? (
            <img
              src={result.overview_image}
              alt={`Your upload with ${text.title} hidden: changed pixels in cyan, flat areas in red, most exposed spot boxed in yellow`}
            />
          ) : (
            <span className="sample-card__placeholder">{isRunning ? "Hiding and testing…" : "—"}</span>
          )}
          {isRunning && <span className="activity activity--scanning" aria-hidden="true" />}
        </div>
        <figcaption>
          <span className="legend-swatch legend-swatch--cyan" aria-hidden="true" /> changed pixels{" "}
          <span className="legend-swatch legend-swatch--red" aria-hidden="true" /> flattest third of the image{" "}
          <span className="legend-swatch legend-swatch--yellow" aria-hidden="true" /> most exposed spot
        </figcaption>
      </figure>
      {result?.hotspot && result.hotspot_original && result.hotspot_stego && (
        <div className="exposure__zoom">
          <figure>
            <div className="image-frame image-frame--map">
              <img src={result.hotspot_original} alt="Most exposed spot, before hiding, zoomed" />
            </div>
            <figcaption>Before (zoomed)</figcaption>
          </figure>
          <figure>
            <div className="image-frame image-frame--map">
              <img src={result.hotspot_stego} alt="The same spot after hiding, changed pixels in cyan, zoomed" />
            </div>
            <figcaption>
              After: {result.hotspot.width} × {result.hotspot.height} px at ({result.hotspot.x}, {result.hotspot.y})
            </figcaption>
          </figure>
        </div>
      )}
    </div>
  );
}

function WhyItMatters({ run, result }: { run: MessageRun; result: MessageAlgorithmResult }) {
  const notable = result.top_signals.filter((signal) => Math.abs(signal.z_score) >= NOTABLE_Z_SCORE);
  return (
    <div className="why">
      <h4 className="subsection-title">Why: {ALGORITHM_LABELS[result.algorithm]}</h4>
      <p>
        The detector scored this image <strong>{formatProbability(result.actual_probability)}</strong> (
        {result.is_detected ? "flagged" : "passes"}; the line is {formatProbability(run.threshold)}). The message
        filled {formatPercent(run.payload_percent)} of the hiding space and changed{" "}
        {result.changed_pixels.toLocaleString("en")} pixels.
      </p>
      <p>
        {formatPercent(result.flat_change_share * 100)} of those changes landed in the flattest third of your image
        (red), roughly in proportion to its area, because the key scatters bits evenly rather than avoiding smooth
        areas. That is where ±1 changes stand out most; the yellow box marks the flat spot that took the most changes.
        The detector judges the whole image at once; the map shows where the evidence sits.
      </p>
      <p>
        {notable.length > 0
          ? `Strongest signals: ${notable.map(describeSignal).join("; ")}.`
          : "No statistic was far from a typical clean photo (all within 1σ)."}{" "}
        {result.is_detected
          ? "To hide this safely, use a shorter message or a more detailed image."
          : "At this size the message blends in."}
      </p>
    </div>
  );
}

function ResultsTable({ run }: { run: MessageRun }) {
  return (
    <div className="table-scroll" role="region" aria-label="Detection and quality per algorithm" tabIndex={0}>
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Algorithm</th>
            <th scope="col">Pre-flight predicted</th>
            <th scope="col">Detector actually saw</th>
            <th scope="col">Quality</th>
            <th scope="col">Pixels changed</th>
            <th scope="col">Changes in flat areas</th>
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
              <td>{result.psnr_db === null ? "identical" : `${DB_FORMAT.format(result.psnr_db)} dB`}</td>
              <td>{result.changed_pixels.toLocaleString("en")}</td>
              <td>{formatPercent(result.flat_change_share * 100)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ChecksTable({ results }: { results: MessageAlgorithmResult[] }) {
  const first = results[0];
  if (!first) return null;
  return (
    <div className="table-scroll" role="region" aria-label="Safety checks" tabIndex={0}>
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Safety check</th>
            {results.map((result) => (
              <th key={result.algorithm} scope="col">
                {ALGORITHM_LABELS[result.algorithm]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {first.checks.map((check, index) => (
            <tr key={check.check}>
              <th scope="row">
                {check.label}
                <span className="text-muted"> · expected: {LAB_OUTCOME_PRESENTATION[check.expected].label}</span>
              </th>
              {results.map((result) => {
                const outcome = result.checks[index]?.outcome;
                return (
                  <td key={result.algorithm}>
                    {outcome && <StatusBadge status={LAB_OUTCOME_PRESENTATION[outcome]} />}
                    {outcome && outcome !== check.expected && <strong className="verdict-text--flagged"> Unexpected</strong>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function describeSignal(signal: { feature: string; z_score: number }): string {
  const { label, channel } = describeFeature(signal.feature);
  const where = channel ? ` (${channel})` : "";
  return `${label}${where}, ${Z_FORMAT.format(Math.abs(signal.z_score))}σ ${signal.z_score >= 0 ? "above" : "below"} a clean photo`;
}

function describeState(state: LiveRunState<MessageRun> | undefined): string {
  switch (state?.status) {
    case "waiting":
      return "Waiting";
    case "running":
      return "Hiding and testing…";
    case "error":
      return "Failed";
    case "done": {
      const run = state.result;
      if (!run.fits) return "Doesn't fit";
      const flagged = run.results.filter((r) => r.is_detected).map((r) => ALGORITHM_LABELS[r.algorithm]);
      if (flagged.length === 0) return "Not flagged by either algorithm";
      if (flagged.length === run.results.length) return "Flagged with both algorithms";
      return `Flagged with ${flagged.join(", ")} only`;
    }
    default:
      return "Not run yet";
  }
}
