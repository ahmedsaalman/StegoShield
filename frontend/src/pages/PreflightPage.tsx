import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { ChoiceGroup } from "../components/ChoiceGroup";
import { ErrorAlert } from "../components/ErrorAlert";
import { Field } from "../components/Field";
import { FileDrop } from "../components/FileDrop";
import { ImagePreview } from "../components/ImagePreview";
import { Meter } from "../components/Meter";
import { PageHeader } from "../components/PageHeader";
import { StatusBadge } from "../components/StatusBadge";
import { api, type KeyMethod, type Preflight } from "../lib/api";
import { formatBytes, formatDimensions, formatPercent, formatProbability } from "../lib/format";
import { RISK_PRESENTATION } from "../lib/presentation";
import { COVER_ACCEPT, useCoverImage } from "../lib/useCoverImage";
import { useRequest } from "../lib/useRequest";
import { useAppState } from "../state/AppState";
import { METHOD_CHOICES } from "./options";

const DEFAULT_MESSAGE_BYTES = 500;

export function PreflightPage() {
  const cover = useCoverImage();
  const { setHandoffCover } = useAppState();
  const navigate = useNavigate();
  const [method, setMethod] = useState<KeyMethod>("password");
  const [messageBytes, setMessageBytes] = useState(DEFAULT_MESSAGE_BYTES);
  const check = useRequest<Preflight>();

  const capacity = cover.capacity.status === "success" ? cover.capacity.data : null;
  const maxBytes = capacity?.max_message_bytes[method] ?? null;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!cover.file) return;
    const file = cover.file;
    void check.run((signal) => api.preflight(file, messageBytes, method, signal));
  }

  function hideInThisImage() {
    setHandoffCover(cover.file);
    void navigate("/hide");
  }

  function clearCover() {
    cover.clear();
    check.reset();
  }

  return (
    <>
      <PageHeader
        title="Pre-flight check"
        description="Before hiding anything, see how much an image can hold and how likely a steganalysis detector is to notice a message of your size."
      />
      <form className="stack-lg form" onSubmit={handleSubmit} noValidate>
        <section className="card stack" aria-labelledby="preflight-image-heading">
          <h2 id="preflight-image-heading" className="section__title">
            Candidate image
          </h2>
          {cover.file ? (
            <ImagePreview
              file={cover.file}
              alt="Candidate cover"
              onRemove={clearCover}
              details={
                capacity && (
                  <p className="text-muted">
                    {formatDimensions(capacity.width, capacity.height)} · holds up to{" "}
                    {formatBytes(capacity.max_message_bytes.password)}
                  </p>
                )
              }
            />
          ) : (
            <FileDrop
              label="Choose an image or drag it here"
              hint="PNG, JPEG, BMP or WebP."
              accept={COVER_ACCEPT}
              icon="image"
              onFile={(file) => {
                check.reset();
                cover.choose(file);
              }}
              error={cover.fileError}
            />
          )}
          {cover.capacity.status === "error" && <ErrorAlert error={cover.capacity.error} />}
        </section>

        <section className="card stack" aria-labelledby="preflight-plan-heading">
          <h2 id="preflight-plan-heading" className="section__title">
            Planned message
          </h2>
          <ChoiceGroup name="preflight-method" legend="Protection" choices={METHOD_CHOICES} value={method} onChange={setMethod} />
          <Field
            id="preflight-bytes"
            label="Message size in bytes"
            hint="One English letter is one byte; emoji and accented letters take 2–4. A short paragraph is about 500 bytes."
          >
            {(describedBy) => (
              <div className="size-input">
                <input
                  id="preflight-bytes"
                  className="input size-input__number"
                  type="number"
                  inputMode="numeric"
                  min={1}
                  max={maxBytes ?? undefined}
                  value={messageBytes}
                  onChange={(event) => setMessageBytes(Math.max(1, Number(event.target.value) || 1))}
                  aria-describedby={describedBy}
                />
                {maxBytes !== null && maxBytes > 1 && (
                  <input
                    className="size-input__range"
                    type="range"
                    min={1}
                    max={maxBytes}
                    value={Math.min(messageBytes, maxBytes)}
                    onChange={(event) => setMessageBytes(Number(event.target.value))}
                    aria-label="Message size slider"
                    aria-valuetext={formatBytes(messageBytes)}
                  />
                )}
              </div>
            )}
          </Field>
        </section>

        <div className="form__actions">
          <Button
            type="submit"
            variant="primary"
            icon="gauge"
            disabled={!cover.file}
            isLoading={check.state.status === "loading"}
            loadingLabel="Analysing image…"
          >
            Run pre-flight check
          </Button>
          {!cover.file && <span className="text-muted">Choose an image first.</span>}
        </div>
      </form>

      {check.state.status === "error" && <ErrorAlert error={check.state.error} />}
      {check.state.status === "success" && <PreflightReport result={check.state.data} onHide={hideInThisImage} />}
    </>
  );
}

function PreflightReport({ result, onHide }: { result: Preflight; onHide: () => void }) {
  const risk = RISK_PRESENTATION[result.risk.level];
  const methodCapacity = result.capacity.max_message_bytes[result.method];
  return (
    <section className="card stack-lg result" aria-labelledby="report-heading" role="status">
      <div className="stack">
        <h2 id="report-heading" className="section__title">
          Result for {formatBytes(result.message_bytes)}
        </h2>
        <StatusBadge status={risk} value={`${formatProbability(result.risk.probability)} detection risk`} size="lg" />
        <p>{risk.summary}</p>
      </div>

      {!result.fits && (
        <Alert tone="danger" title="This message doesn't fit">
          This image holds at most {formatBytes(methodCapacity)} with this protection method.
        </Alert>
      )}

      <Meter
        label="Share of the image's hiding space used"
        value={result.payload_percent / 100}
        valueText={formatPercent(result.payload_percent)}
        tone={result.fits ? "neutral" : "danger"}
        marker={{
          position: methodCapacity > 0 ? result.recommended_max_message_bytes / methodCapacity : 0,
          label: `Marker: suggested maximum, ${formatBytes(result.recommended_max_message_bytes)}`,
        }}
      />

      <dl className="facts facts--grid">
        <div>
          <dt>Holds up to</dt>
          <dd>{formatBytes(methodCapacity)}</dd>
        </div>
        <div>
          <dt>Suggested maximum</dt>
          <dd>{formatBytes(result.recommended_max_message_bytes)}</dd>
        </div>
        <div>
          <dt>Texture</dt>
          <dd>{result.texture}</dd>
        </div>
      </dl>

      <p>{result.recommendation}</p>
      <p className="text-muted">How this was estimated: {result.risk.method}.</p>

      {result.fits && (
        <div className="form__actions">
          <Button variant="primary" icon="arrowRight" onClick={onHide}>
            Hide a message in this image
          </Button>
        </div>
      )}
    </section>
  );
}
