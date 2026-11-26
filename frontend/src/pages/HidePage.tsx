import { type FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Alert } from "../components/Alert";
import { BlobImage } from "../components/BlobImage";
import { Button } from "../components/Button";
import { ChoiceGroup } from "../components/ChoiceGroup";
import { Disclosure } from "../components/Disclosure";
import { ErrorAlert } from "../components/ErrorAlert";
import { Field } from "../components/Field";
import { FileDrop } from "../components/FileDrop";
import { ImagePreview } from "../components/ImagePreview";
import { Meter } from "../components/Meter";
import { PageHeader } from "../components/PageHeader";
import { PasswordInput } from "../components/PasswordInput";
import { StatusBadge } from "../components/StatusBadge";
import {
  api,
  type Capacity,
  type EmbeddingAlgorithm,
  type EmbeddingLayout,
  type HiddenImage,
  type KeyMethod,
  type Preflight,
  type PublicKeyInfo,
} from "../lib/api";
import { saveFile } from "../lib/download";
import { formatBytes, formatDimensions, formatProbability } from "../lib/format";
import {
  firstInvalidField,
  type HideFormErrors,
  RECOMMENDED_PASSWORD_LENGTH,
  validateHideForm,
} from "../lib/hideValidation";
import { RISK_PRESENTATION } from "../lib/presentation";
import { COVER_ACCEPT, type CoverImage, useCoverImage } from "../lib/useCoverImage";
import { type RequestState, useRequest } from "../lib/useRequest";
import { useAppState } from "../state/AppState";
import { ALGORITHM_CHOICES, LAYOUT_CHOICES, METHOD_CHOICES } from "./options";

const FIELD_IDS = {
  cover: "hide-cover",
  message: "hide-message",
  password: "hide-password",
  confirmPassword: "hide-password-confirm",
  recipientKey: "hide-recipient-key",
} as const;

export function HidePage() {
  const { handoffCover, setHandoffCover, recipientKey: savedKey } = useAppState();
  const cover = useCoverImage(handoffCover);
  // The hand-off is consumed once; clear it when leaving so it is not reused later.
  useEffect(() => () => setHandoffCover(null), [setHandoffCover]);

  const [message, setMessage] = useState("");
  const [method, setMethod] = useState<KeyMethod>(savedKey ? "public_key" : "password");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [recipientKey, setRecipientKey] = useState(savedKey?.publicKeyBase64 ?? "");
  const [algorithm, setAlgorithm] = useState<EmbeddingAlgorithm>("matching");
  const [layout, setLayout] = useState<EmbeddingLayout>("pseudorandom");
  const [hasTriedSubmit, setHasTriedSubmit] = useState(false);

  const keyCheck = useRequest<PublicKeyInfo>();
  const hideRequest = useRequest<HiddenImage>();
  const messageBytes = new TextEncoder().encode(message).length;
  const capacity = cover.capacity.status === "success" ? cover.capacity.data : null;
  const capacityBytes = capacity ? capacity.max_message_bytes[method] : null;

  const errors = validateHideForm({
    hasCover: cover.file !== null,
    messageBytes,
    capacityBytes,
    method,
    password,
    confirmPassword,
    recipientKey,
    recipientKeyProblem: keyCheck.state.status === "error" ? keyCheck.state.error.message : null,
  });
  const visibleErrors: HideFormErrors = hasTriedSubmit ? errors : {};

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setHasTriedSubmit(true);
    const invalidField = firstInvalidField(errors);
    if (invalidField) {
      document.getElementById(FIELD_IDS[invalidField])?.focus();
      return;
    }
    if (!cover.file) return;
    const coverFile = cover.file;
    const protection =
      method === "password"
        ? { method, password }
        : { method, recipientPublicKey: recipientKey };
    void hideRequest.run((signal) => api.hide({ cover: coverFile, message, protection, algorithm, layout }, signal));
  }

  function startOver() {
    hideRequest.reset();
    cover.clear();
    setMessage("");
    setHasTriedSubmit(false);
  }

  if (hideRequest.state.status === "success" && cover.file) {
    return (
      <HideResult
        cover={cover.file}
        result={hideRequest.state.data}
        usedPassword={method === "password"}
        onStartOver={startOver}
      />
    );
  }

  return (
    <>
      <PageHeader
        title="Hide a message"
        description="Encrypt a message and hide it in an image. The result looks the same as the original, and only someone with the password or the matching private key can read it."
      />
      <form className="stack-lg form" onSubmit={handleSubmit} noValidate>
        <CoverStep cover={cover} error={visibleErrors.cover} />
        <MessageStep
          message={message}
          onMessageChange={setMessage}
          messageBytes={messageBytes}
          capacityBytes={capacityBytes}
          error={visibleErrors.message}
          cover={cover.file}
          method={method}
        />
        <section className="card stack" aria-labelledby="protect-heading">
          <StepHeading id="protect-heading" number={3} title="Choose how to protect it" />
          <ChoiceGroup
            name="hide-method"
            legend="How to protect the message"
            choices={METHOD_CHOICES}
            value={method}
            onChange={setMethod}
            isLegendVisible={false}
          />
          {method === "password" ? (
            <PasswordFields
              password={password}
              confirmPassword={confirmPassword}
              onPasswordChange={setPassword}
              onConfirmChange={setConfirmPassword}
              errors={visibleErrors}
            />
          ) : (
            <RecipientKeyField
              value={recipientKey}
              onChange={(value) => {
                setRecipientKey(value);
                keyCheck.reset();
              }}
              onCheck={() => void keyCheck.run((signal) => api.inspectPublicKey(recipientKey, signal))}
              check={keyCheck.state}
              error={visibleErrors.recipientKey}
            />
          )}
        </section>

        <Disclosure summary="Advanced options">
          <div className="stack">
            <ChoiceGroup
              name="hide-algorithm"
              legend="How pixels are changed"
              choices={ALGORITHM_CHOICES}
              value={algorithm}
              onChange={setAlgorithm}
              layout="stack"
            />
            <ChoiceGroup
              name="hide-layout"
              legend="Where bits are placed"
              choices={LAYOUT_CHOICES}
              value={layout}
              onChange={setLayout}
              layout="stack"
            />
            {layout === "sequential" && (
              <Alert tone="warning" title="Sequential placement is for experiments only">
                Anyone can find the message bits without the key, and detectors spot it easily. The message itself stays
                encrypted.
              </Alert>
            )}
          </div>
        </Disclosure>

        {hideRequest.state.status === "error" && <ErrorAlert error={hideRequest.state.error} />}
        {hasTriedSubmit && firstInvalidField(errors) && (
          <Alert tone="danger" title="Check the highlighted fields" live>
            Fix the items marked above, then try again.
          </Alert>
        )}

        <div className="form__actions">
          <Button
            type="submit"
            variant="primary"
            icon="lock"
            isLoading={hideRequest.state.status === "loading"}
            loadingLabel="Encrypting and hiding…"
          >
            Hide message
          </Button>
        </div>
      </form>
    </>
  );
}

function StepHeading({ id, number, title }: { id: string; number: number; title: string }) {
  return (
    <h2 id={id} className="step-heading">
      <span className="step-heading__number" aria-hidden="true">
        {number}
      </span>
      <span>
        <span className="visually-hidden">Step {number}: </span>
        {title}
      </span>
    </h2>
  );
}

function CoverStep({ cover, error }: { cover: CoverImage; error: string | undefined }) {
  return (
    <section className="card stack" aria-labelledby="cover-heading">
      <StepHeading id="cover-heading" number={1} title="Choose a cover image" />
      {cover.file ? (
        <ImagePreview
          file={cover.file}
          alt="Your chosen cover"
          onRemove={cover.clear}
          details={<CapacitySummary state={cover.capacity} />}
        />
      ) : (
        <div id={FIELD_IDS.cover} tabIndex={-1}>
          <FileDrop
            label="Choose an image or drag it here"
            hint="PNG, JPEG, BMP or WebP. Detailed photos (foliage, crowds, textures) hide messages best."
            accept={COVER_ACCEPT}
            icon="image"
            onFile={cover.choose}
            error={cover.fileError ?? error ?? null}
          />
        </div>
      )}
      {cover.capacity.status === "success" && cover.capacity.data.is_lossy_source && (
        <Alert tone="info" title="JPEG cover">
          That's fine: the result is saved as a PNG. Always send that PNG unchanged. Converting it back to JPEG erases
          the message.
        </Alert>
      )}
    </section>
  );
}

function CapacitySummary({ state }: { state: RequestState<Capacity> }) {
  if (state.status === "loading") return <p className="text-muted">Measuring capacity…</p>;
  if (state.status === "error") return <ErrorAlert error={state.error} />;
  if (state.status !== "success") return null;
  const { width, height, max_message_bytes } = state.data;
  return (
    <dl className="facts">
      <div>
        <dt>Size</dt>
        <dd>{formatDimensions(width, height)}</dd>
      </div>
      <div>
        <dt>Holds up to</dt>
        <dd>{formatBytes(max_message_bytes.password)}</dd>
      </div>
    </dl>
  );
}

interface MessageStepProps {
  message: string;
  onMessageChange: (message: string) => void;
  messageBytes: number;
  capacityBytes: number | null;
  error: string | undefined;
  cover: File | null;
  method: KeyMethod;
}

function MessageStep({ message, onMessageChange, messageBytes, capacityBytes, error, cover, method }: MessageStepProps) {
  const isOverCapacity = capacityBytes !== null && messageBytes > capacityBytes;
  return (
    <section className="card stack" aria-labelledby="message-heading">
      <StepHeading id="message-heading" number={2} title="Write your message" />
      <Field id={FIELD_IDS.message} label="Secret message" error={error ?? null}>
        {(describedBy) => (
          <textarea
            id={FIELD_IDS.message}
            className="input textarea"
            rows={6}
            value={message}
            onChange={(event) => onMessageChange(event.target.value)}
            aria-describedby={describedBy ? `${describedBy} hide-message-usage` : "hide-message-usage"}
            aria-invalid={error ? true : undefined}
          />
        )}
      </Field>
      <div id="hide-message-usage">
        {capacityBytes !== null ? (
          <Meter
            label="Space used"
            value={capacityBytes > 0 ? messageBytes / capacityBytes : 1}
            valueText={`${formatBytes(messageBytes)} of ${formatBytes(capacityBytes)}`}
            tone={isOverCapacity ? "danger" : "neutral"}
          />
        ) : (
          <p className="text-muted">{formatBytes(messageBytes)} · choose an image to see how much fits</p>
        )}
      </div>
      {cover && messageBytes > 0 && !isOverCapacity && (
        <RiskCheck cover={cover} messageBytes={messageBytes} method={method} />
      )}
    </section>
  );
}

function RiskCheck({ cover, messageBytes, method }: { cover: File; messageBytes: number; method: KeyMethod }) {
  const check = useRequest<Preflight>();
  const [checked, setChecked] = useState<{ cover: File; method: KeyMethod; bytes: number } | null>(null);

  const isForThisCover = checked?.cover === cover && checked.method === method;
  const isStale = checked?.bytes !== messageBytes;
  return (
    <div className="inline-check">
      <Button
        variant="secondary"
        icon="gauge"
        isLoading={check.state.status === "loading"}
        loadingLabel="Checking…"
        onClick={() => {
          setChecked({ cover, method, bytes: messageBytes });
          void check.run((signal) => api.preflight(cover, messageBytes, method, signal));
        }}
      >
        {check.state.status === "success" && isForThisCover ? "Check again" : "Check detection risk"}
      </Button>
      {check.state.status === "success" && isForThisCover && (
        <div className="inline-check__result" role="status">
          <StatusBadge
            status={RISK_PRESENTATION[check.state.data.risk.level]}
            value={formatProbability(check.state.data.risk.probability)}
          />
          <span className="text-muted">
            {isStale ? "Message changed since this check. " : ""}
            <Link to="/preflight">Full pre-flight check</Link>
          </span>
        </div>
      )}
      {check.state.status === "error" && <ErrorAlert error={check.state.error} />}
    </div>
  );
}

interface PasswordFieldsProps {
  password: string;
  confirmPassword: string;
  onPasswordChange: (value: string) => void;
  onConfirmChange: (value: string) => void;
  errors: HideFormErrors;
}

function PasswordFields({ password, confirmPassword, onPasswordChange, onConfirmChange, errors }: PasswordFieldsProps) {
  const isShort = password.length > 0 && password.length < RECOMMENDED_PASSWORD_LENGTH;
  return (
    <div className="grid-2">
      <Field
        id={FIELD_IDS.password}
        label="Password"
        hint={
          isShort
            ? `Short passwords can be guessed. Use ${RECOMMENDED_PASSWORD_LENGTH}+ characters; a few unrelated words work well.`
            : "Share it with the recipient through a different channel than the image."
        }
        error={errors.password ?? null}
      >
        {(describedBy) => (
          <PasswordInput
            id={FIELD_IDS.password}
            value={password}
            onChange={onPasswordChange}
            describedBy={describedBy}
            isInvalid={Boolean(errors.password)}
            autoComplete="new-password"
          />
        )}
      </Field>
      <Field id={FIELD_IDS.confirmPassword} label="Confirm password" error={errors.confirmPassword ?? null}>
        {(describedBy) => (
          <PasswordInput
            id={FIELD_IDS.confirmPassword}
            value={confirmPassword}
            onChange={onConfirmChange}
            describedBy={describedBy}
            isInvalid={Boolean(errors.confirmPassword)}
            autoComplete="new-password"
          />
        )}
      </Field>
    </div>
  );
}

interface RecipientKeyFieldProps {
  value: string;
  onChange: (value: string) => void;
  onCheck: () => void;
  check: RequestState<PublicKeyInfo>;
  error: string | undefined;
}

function RecipientKeyField({ value, onChange, onCheck, check, error }: RecipientKeyFieldProps) {
  return (
    <div className="stack">
      <Field
        id={FIELD_IDS.recipientKey}
        label="Recipient's public key"
        hint={
          <>
            PEM, Base64 or hex. The recipient can create one on the <Link to="/keys">Keys</Link> page.
          </>
        }
        error={error ?? null}
      >
        {(describedBy) => (
          <textarea
            id={FIELD_IDS.recipientKey}
            className="input textarea textarea--mono"
            rows={3}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onBlur={() => value.trim() && check.status === "idle" && onCheck()}
            aria-describedby={describedBy}
            aria-invalid={error ? true : undefined}
            spellCheck={false}
          />
        )}
      </Field>
      {check.status === "loading" && <p className="text-muted">Checking key…</p>}
      {check.status === "success" && (
        <Alert tone="success" title="Valid public key" live>
          Fingerprint <code className="fingerprint">{check.data.fingerprint}</code>. Confirm it with the recipient (in
          person or by phone) so you know the key really is theirs.
        </Alert>
      )}
    </div>
  );
}

interface HideResultProps {
  cover: File;
  result: HiddenImage;
  usedPassword: boolean;
  onStartOver: () => void;
}

function HideResult({ cover, result, usedPassword, onStartOver }: HideResultProps) {
  return (
    <>
      <PageHeader title="Your message is hidden" description="Download the new image and send it to the recipient." />
      <div className="stack-lg">
        <Alert tone="success" title="Done: the message is encrypted and hidden" live>
          The two images below should look identical. Only the password or the recipient's private key can reveal the
          message.
        </Alert>
        <div className="compare">
          <figure className="compare__item">
            <BlobImage blob={cover} alt="Original cover" />
            <figcaption>Original</figcaption>
          </figure>
          <figure className="compare__item">
            <BlobImage blob={result.blob} alt="Cover with the message hidden in it" />
            <figcaption>With hidden message · {formatBytes(result.blob.size)}</figcaption>
          </figure>
        </div>
        <div className="form__actions">
          <Button variant="primary" icon="download" onClick={() => saveFile(result.blob, result.filename)}>
            Download {result.filename}
          </Button>
          <Button variant="secondary" onClick={onStartOver}>
            Hide another message
          </Button>
        </div>
        <section className="card" aria-labelledby="sending-heading">
          <h2 id="sending-heading" className="section__title">
            Before you send it
          </h2>
          <ul className="list">
            <li>Send the PNG as a file or document attachment, not as a photo. Apps that recompress photos erase the message.</li>
            <li>Don't edit, crop, resize or screenshot the image.</li>
            {usedPassword && <li>Share the password through a different channel than the image.</li>}
          </ul>
        </section>
      </div>
    </>
  );
}
