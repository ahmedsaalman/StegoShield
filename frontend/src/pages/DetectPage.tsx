import { type FormEvent } from "react";

import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { ErrorAlert } from "../components/ErrorAlert";
import { FileDrop } from "../components/FileDrop";
import { ImagePreview } from "../components/ImagePreview";
import { Meter } from "../components/Meter";
import { PageHeader } from "../components/PageHeader";
import { StatusBadge } from "../components/StatusBadge";
import { api, type Detection, type FeatureContribution } from "../lib/api";
import { describeFeature } from "../lib/features";
import { formatProbability } from "../lib/format";
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
        title="Detect hidden data"
        description="Scan an image with a machine-learning steganalysis detector. You get the probability that it carries a hidden message and the statistics that drove the score."
      />
      <form className="stack-lg form" onSubmit={handleSubmit} noValidate>
        {isDetectorMissing && (
          <Alert tone="info" title="The detector isn't installed on this server yet">
            Scanning is unavailable until an administrator trains and installs the model. Everything else works as
            normal.
          </Alert>
        )}
        <section className="card stack" aria-labelledby="detect-image-heading">
          <h2 id="detect-image-heading" className="section__title">
            Image to scan
          </h2>
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
              label="Choose an image or drag it here"
              hint="PNG, JPEG, BMP or WebP. The image is analysed in memory and not stored."
              accept={COVER_ACCEPT}
              icon="image"
              onFile={(file) => {
                scan.reset();
                image.choose(file);
              }}
              error={image.fileError}
            />
          )}
        </section>
        <div className="form__actions">
          <Button
            type="submit"
            variant="primary"
            icon="scan"
            disabled={!image.file || isDetectorMissing}
            isLoading={scan.state.status === "loading"}
            loadingLabel="Scanning…"
          >
            Scan image
          </Button>
        </div>
      </form>

      {scan.state.status === "error" && <ErrorAlert error={scan.state.error} />}
      {scan.state.status === "success" && <DetectionReport result={scan.state.data} />}
    </>
  );
}

function DetectionReport({ result }: { result: Detection }) {
  const verdict = VERDICT_PRESENTATION[result.verdict];
  return (
    <section className="card stack-lg result" aria-labelledby="detection-heading" role="status">
      <div className="stack">
        <h2 id="detection-heading" className="section__title">
          Scan result
        </h2>
        <StatusBadge status={verdict} value={formatProbability(result.probability)} size="lg" />
        <p>{verdict.summary}</p>
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
      <p className="text-muted">
        Model: {result.model_type}. Scores are statistical estimates. A low score doesn't prove an image is clean,
        and a high score isn't proof of a message.
      </p>
    </section>
  );
}

function FeatureTable({ features }: { features: FeatureContribution[] }) {
  const largest = Math.max(...features.map((feature) => feature.contribution), Number.EPSILON);
  return (
    <div className="stack">
      <h3 className="subsection-title">What drove the score</h3>
      <div className="table-scroll" role="region" aria-label="Features that drove the score" tabIndex={0}>
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Statistic</th>
              <th scope="col">This image</th>
              <th scope="col">Typical clean image</th>
              <th scope="col">Difference</th>
              <th scope="col">Influence</th>
            </tr>
          </thead>
          <tbody>
            {features.map((feature) => {
              const { label, channel } = describeFeature(feature.feature);
              return (
                <tr key={feature.feature}>
                  <th scope="row">
                    {label}
                    {channel && <span className="text-muted"> ({channel} channel)</span>}
                  </th>
                  <td>{NUMBER_FORMAT.format(feature.value)}</td>
                  <td>{NUMBER_FORMAT.format(feature.typical_clean_value)}</td>
                  <td>{describeDeviation(feature.z_score)}</td>
                  <td>
                    <span className="influence">
                      <span
                        className="influence__bar"
                        style={{ width: `${(feature.contribution / largest) * 100}%` }}
                        aria-hidden="true"
                      />
                      <span className="visually-hidden">{Math.round((feature.contribution / largest) * 100)}% of the largest</span>
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
  const direction = zScore >= 0 ? "higher" : "lower";
  if (magnitude < 1) return "about normal";
  return `${NUMBER_FORMAT.format(magnitude)}σ ${direction}`;
}
