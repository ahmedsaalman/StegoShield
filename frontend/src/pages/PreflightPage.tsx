import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { ChoiceGroup } from "../components/ChoiceGroup";
import { ErrorAlert } from "../components/ErrorAlert";
import { Field } from "../components/Field";
import { FileDrop } from "../components/FileDrop";
import { ToolArt } from "../components/illustrations/ToolArt";
import { ImagePreview } from "../components/ImagePreview";
import { Meter } from "../components/Meter";
import { PageBody, PageHeader } from "../components/PageHeader";
import { StatusBadge } from "../components/StatusBadge";
import { api, type KeyMethod, type Preflight } from "../lib/api";
import { formatBytes, formatDimensions, formatPercent, formatProbability, parsePositiveInteger } from "../lib/format";
import { useCountUp } from "../lib/motion";
import { RISK_PRESENTATION } from "../lib/presentation";
import { COVER_ACCEPT, useCoverImage } from "../lib/useCoverImage";
import { useRequest } from "../lib/useRequest";
import { useAppState } from "../state/AppState";
import { METHOD_CHOICES } from "./options";

const DEFAULT_MESSAGE_BYTES = 500;
const SIZE_FIELD_ID = "preflight-bytes";

export function PreflightPage() {
  const cover = useCoverImage();
  const { setHandoffCover } = useAppState();
  const navigate = useNavigate();
  const [method, setMethod] = useState<KeyMethod>("password");
  // Kept as typed, so the field can be cleared and retyped without snapping back to a number.
  const [sizeText, setSizeText] = useState(String(DEFAULT_MESSAGE_BYTES));
  const [hasTriedSubmit, setHasTriedSubmit] = useState(false);
  const messageBytes = parsePositiveInteger(sizeText);
  const sizeError = hasTriedSubmit && messageBytes === null ? "Enter a whole number of bytes, 1 or more." : null;
  const check = useRequest<Preflight>();

  const capacity = cover.capacity.status === "success" ? cover.capacity.data : null;
  const maxBytes = capacity?.max_message_bytes[method] ?? null;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setHasTriedSubmit(true);
    if (messageBytes === null) {
      document.getElementById(SIZE_FIELD_ID)?.focus();
      return;
    }
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
        eyebrow="Send"
        art={<ToolArt name="preflight" isAmbient />}
        title="Pre-flight check"
        description="Before hiding anything, see how much an image can hold and how likely a steganalysis detector is to notice a message of your size."
      />
      <PageBody isNarrow>
        <div className="stack-lg">
          <form className="stack-lg" onSubmit={handleSubmit} noValidate>
            <Card
              step="Step 01"
              title="Candidate image"
              footer={
                capacity ? (
                  <span className="inline-stats">
                    <span>{formatDimensions(capacity.width, capacity.height)}</span>
                    <span>Holds up to {formatBytes(capacity.max_message_bytes.password)}</span>
                  </span>
                ) : (
                  <span>Capacity appears once you choose an image.</span>
                )
              }
            >
              {cover.file ? (
                <ImagePreview
                  file={cover.file}
                  alt="Candidate cover"
                  onRemove={clearCover}
                  activity={check.state.status === "loading" ? "scanning" : null}
                />
              ) : (
                <FileDrop
                  label="Drop an image here or click to browse"
                  hint="PNG, JPEG, BMP or WebP"
                  accept={COVER_ACCEPT}
                  icon="upload"
                  onFile={(file) => {
                    check.reset();
                    cover.choose(file);
                  }}
                  error={cover.fileError}
                />
              )}
              {cover.capacity.status === "error" && <ErrorAlert error={cover.capacity.error} />}
            </Card>

            <Card step="Step 02" title="Planned message">
              <ChoiceGroup
                name="preflight-method"
                legend="Protection"
                choices={METHOD_CHOICES}
                value={method}
                onChange={setMethod}
              />
              <Field
                id={SIZE_FIELD_ID}
                label="Message size in bytes"
                error={sizeError}
                hint="One English letter is one byte; emoji and accented letters take 2–4. A short paragraph is about 500 bytes."
              >
                {(describedBy) => (
                  <div className="size-input">
                    <input
                      id={SIZE_FIELD_ID}
                      className="input size-input__number"
                      type="number"
                      inputMode="numeric"
                      min={1}
                      max={maxBytes ?? undefined}
                      value={sizeText}
                      onChange={(event) => setSizeText(event.target.value)}
                      aria-describedby={describedBy}
                      aria-invalid={sizeError ? true : undefined}
                    />
                    {maxBytes !== null && maxBytes > 1 && (
                      <input
                        className="size-input__range"
                        type="range"
                        min={1}
                        max={maxBytes}
                        value={Math.min(messageBytes ?? 1, maxBytes)}
                        onChange={(event) => setSizeText(event.target.value)}
                        aria-label="Message size slider"
                        aria-valuetext={formatBytes(messageBytes ?? 1)}
                      />
                    )}
                  </div>
                )}
              </Field>
            </Card>

            <div className="actions actions--end">
              {!cover.file && <span className="text-muted">Choose an image first.</span>}
              <Button
                type="submit"
                variant="primary"
                size="lg"
                icon="gauge"
                disabled={!cover.file}
                isLoading={check.state.status === "loading"}
                loadingLabel="Analysing image…"
              >
                Run pre-flight check
              </Button>
            </div>
          </form>

          {check.state.status === "error" && <ErrorAlert error={check.state.error} />}
          {check.state.status === "success" && <PreflightReport result={check.state.data} onHide={hideInThisImage} />}
        </div>
      </PageBody>
    </>
  );
}

function AnimatedPercent({ probability }: { probability: number }) {
  const shown = useCountUp(probability * 100);
  return (
    <>
      <span className="verdict__value" aria-hidden="true">
        {Math.round(shown)}%
      </span>
      <span className="visually-hidden">{formatProbability(probability)}</span>
    </>
  );
}

function PreflightReport({ result, onHide }: { result: Preflight; onHide: () => void }) {
  const risk = RISK_PRESENTATION[result.risk.level];
  const methodCapacity = result.capacity.max_message_bytes[result.method];
  return (
    <Card
      title={`Result for ${formatBytes(result.message_bytes)}`}
      isLive
      footer={
        <>
          <span>Estimated with: {result.risk.method}</span>
          {result.fits && (
            <Button variant="primary" size="sm" icon="arrowRight" onClick={onHide}>
              Hide a message in this image
            </Button>
          )}
        </>
      }
    >
      <div className="verdict">
        <AnimatedPercent probability={result.risk.probability} />
        <StatusBadge status={risk} size="lg" />
        <p className="verdict__summary">{risk.summary}</p>
      </div>

      {!result.fits && (
        <Alert tone="danger" title="This message doesn't fit">
          This image holds at most {formatBytes(methodCapacity)} with this protection method.
        </Alert>
      )}

      <Meter
        label="Hiding space used"
        value={result.payload_percent / 100}
        valueText={formatPercent(result.payload_percent)}
        tone={result.fits ? "neutral" : "danger"}
        marker={{
          position: methodCapacity > 0 ? result.recommended_max_message_bytes / methodCapacity : 0,
          label: `Marker: suggested maximum, ${formatBytes(result.recommended_max_message_bytes)}`,
        }}
      />

      <dl className="stats">
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

      <p className="text-muted">{result.recommendation}</p>
    </Card>
  );
}
