import { type FormEvent } from "react";

import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { ErrorAlert } from "../components/ErrorAlert";
import { FileDrop } from "../components/FileDrop";
import { ImagePreview } from "../components/ImagePreview";
import { Meter } from "../components/Meter";
import { PageBody, PageHeader } from "../components/PageHeader";
import { StatusBadge } from "../components/StatusBadge";
import { api, type Detection, type FeatureContribution } from "../lib/api";
import { describeFeature } from "../lib/features";
import { formatProbability } from "../lib/format";
import { useCountUp } from "../lib/motion";
import { VERDICT_PRESENTATION } from "../lib/presentation";
import { COVER_ACCEPT, useCoverImage } from "../lib/useCoverImage";
import { useRequest } from "../lib/useRequest";
import { useAppState } from "../state/AppState";

const NUMBER_FORMAT = new Intl.NumberFormat("en", { maximumSignificantDigits: 4 });

export function DetectPage() {
  const { meta } = useAppState();
  const image = useCoverImage();
  const scan = useRequest<Detection>();
  const isDetectorMissing = meta !== null && !meta.detector.available;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!image.file) return;
    const file = image.file;
    void scan.run((signal) => api.detect(file, signal));
  }

  return (
    <>
      <PageHeader
        eyebrow="Analyse"
        title="Detect hidden data"
        description="Scan an image with a machine-learning steganalysis detector: the probability that it carries a hidden message, and the statistics behind the score."
      />
      <PageBody isNarrow>
        <div className="stack-lg">
          {isDetectorMissing && (
            <Alert tone="info" title="The detector isn't installed on this server yet">
              Scanning is unavailable until an administrator trains and installs the model. Everything else works as
              normal.
            </Alert>
          )}
          <form className="stack-lg" onSubmit={handleSubmit} noValidate>
            <Card
              title="Image to scan"
              footer={
                <>
                  <span>Analysed in memory and not stored.</span>
                  <Button
                    type="submit"
                    variant="primary"
                    size="sm"
                    icon="scan"
                    disabled={!image.file || isDetectorMissing}
                    isLoading={scan.state.status === "loading"}
                    loadingLabel="Scanning…"
                  >
                    Scan image
                  </Button>
                </>
              }
            >
              {image.file ? (
                <ImagePreview
                  file={image.file}
                  alt="The file to scan"
                  onRemove={() => {
                    image.clear();
                    scan.reset();
                  }}
                />
              ) : (
                <FileDrop
                  label="Drop an image here or click to browse"
                  hint="PNG, JPEG, BMP or WebP"
                  accept={COVER_ACCEPT}
                  icon="upload"
                  onFile={(file) => {
                    scan.reset();
                    image.choose(file);
                  }}
                  error={image.fileError}
                />
              )}
            </Card>
          </form>

          {scan.state.status === "error" && <ErrorAlert error={scan.state.error} />}
          {scan.state.status === "success" && <DetectionReport result={scan.state.data} />}
        </div>
      </PageBody>
    </>
  );
}

function DetectionReport({ result }: { result: Detection }) {
  const verdict = VERDICT_PRESENTATION[result.verdict];
  return (
    <Card
      title="Scan result"
      isLive
      footer={
        <span>
          {result.model_type}. Scores are statistical estimates: a low score doesn't prove an image is clean, and a high
          score isn't proof of a message.
        </span>
      }
    >
      <div className="verdict">
        <AnimatedPercent probability={result.probability} />
        <StatusBadge status={verdict} size="lg" />
        <p className="verdict__summary">{verdict.summary}</p>
      </div>
      <Meter
        label="Probability of hidden data"
        value={result.probability}
        valueText={formatProbability(result.probability)}
        tone={verdict.tone}
        marker={{
          position: result.threshold,
          label: `Marker: decision threshold (${formatProbability(result.threshold)}). Images at or above it are flagged.`,
        }}
      />
      {result.top_features.length > 0 && <FeatureTable features={result.top_features} />}
    </Card>
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

function FeatureTable({ features }: { features: FeatureContribution[] }) {
  const largest = Math.max(...features.map((feature) => feature.contribution), Number.EPSILON);
  return (
    <div className="stack-sm">
      <h3 className="subsection-title">What drove the score</h3>
      <div className="table-scroll" role="region" aria-label="Features that drove the score" tabIndex={0}>
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Statistic</th>
              <th scope="col">This image</th>
              <th scope="col">Typical clean</th>
              <th scope="col">Difference</th>
              <th scope="col">Influence</th>
            </tr>
          </thead>
          <tbody>
            {features.map((feature) => {
              const { label, channel } = describeFeature(feature.feature);
              const share = (feature.contribution / largest) * 100;
              return (
                <tr key={feature.feature}>
                  <th scope="row">
                    {label}
                    {channel && <span className="text-muted"> · {channel}</span>}
                  </th>
                  <td>{NUMBER_FORMAT.format(feature.value)}</td>
                  <td>{NUMBER_FORMAT.format(feature.typical_clean_value)}</td>
                  <td>{describeDeviation(feature.z_score)}</td>
                  <td>
                    <span className="influence">
                      <span className="influence__bar" style={{ width: `${share}%` }} aria-hidden="true" />
                      <span className="visually-hidden">{Math.round(share)}% of the largest</span>
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function describeDeviation(zScore: number): string {
  const magnitude = Math.abs(zScore);
  if (magnitude < 1) return "about normal";
  return `${NUMBER_FORMAT.format(magnitude)}σ ${zScore >= 0 ? "higher" : "lower"}`;
}
