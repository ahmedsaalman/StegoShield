import { type FormEvent, useState } from "react";

import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { ChoiceGroup } from "../components/ChoiceGroup";
import { CopyButton } from "../components/CopyButton";
import { Disclosure } from "../components/Disclosure";
import { ErrorAlert } from "../components/ErrorAlert";
import { Field } from "../components/Field";
import { FileDrop, describeFile } from "../components/FileDrop";
import { ImagePreview } from "../components/ImagePreview";
import { PageHeader } from "../components/PageHeader";
import { PasswordInput } from "../components/PasswordInput";
import { api, type EmbeddingLayout, type KeyMethod, type RevealResult, type UnlockSecret } from "../lib/api";
import { saveFile } from "../lib/download";
import { formatBytes } from "../lib/format";
import { useRequest } from "../lib/useRequest";
import { useAppState } from "../state/AppState";
import { LAYOUT_CHOICES } from "./options";

const STEGO_TYPES = new Set(["image/png", "image/bmp"]);
const LOSSY_TYPES = new Set(["image/jpeg", "image/webp"]);
const MAX_PRIVATE_KEY_FILE_BYTES = 16 * 1024;

const UNLOCK_CHOICES = [
  { value: "password" as const, label: "Password", description: "The sender protected it with a password." },
  { value: "public_key" as const, label: "My private key", description: "The sender used your public key." },
];

type FieldErrors = Partial<Record<"image" | "password" | "privateKey", string>>;

export function RevealPage() {
  const { meta } = useAppState();
  const [image, setImage] = useState<File | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);
  const [method, setMethod] = useState<KeyMethod>("password");
  const [password, setPassword] = useState("");
  const [privateKey, setPrivateKey] = useState<{ name: string; pem: string } | null>(null);
  const [privateKeyError, setPrivateKeyError] = useState<string | null>(null);
  const [passphrase, setPassphrase] = useState("");
  const [layout, setLayout] = useState<EmbeddingLayout>("pseudorandom");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const reveal = useRequest<RevealResult>();

  function chooseImage(file: File) {
    reveal.reset();
    const problem = describeStegoProblem(file, meta?.limits.max_upload_bytes);
    setImageError(problem);
    setImage(problem ? null : file);
  }

  async function choosePrivateKey(file: File) {
    if (file.size > MAX_PRIVATE_KEY_FILE_BYTES) {
      setPrivateKeyError("That file is too large to be a private key. Choose the .pem file from the Keys page.");
      return;
    }
    setPrivateKeyError(null);
    setPrivateKey({ name: file.name, pem: await file.text() });
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const errors = validate();
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0 || !image) return;
    const unlock: UnlockSecret =
      method === "password"
        ? { method, password }
        : { method, privateKey: privateKey?.pem ?? "", passphrase };
    const stegoImage = image;
    void reveal.run((signal) => api.reveal({ image: stegoImage, unlock, layout }, signal));
  }

  function validate(): FieldErrors {
    const errors: FieldErrors = {};
    if (!image) errors.image = "Choose the image you received.";
    if (method === "password" && !password) errors.password = "Enter the password.";
    if (method === "public_key" && !privateKey) errors.privateKey = "Choose your private key file.";
    return errors;
  }

  return (
    <>
      <PageHeader
        title="Reveal a message"
        description="Open an image you received and recover the hidden message with the password or your private key."
      />
      <form className="stack-lg form" onSubmit={handleSubmit} noValidate>
        <section className="card stack" aria-labelledby="reveal-image-heading">
          <h2 id="reveal-image-heading" className="section__title">
            Image you received
          </h2>
          {image ? (
            <ImagePreview file={image} alt="The file you received" onRemove={() => setImage(null)} />
          ) : (
            <FileDrop
              label="Choose the image or drag it here"
              hint="Use the original PNG file. Screenshots and photos re-sent through chat apps no longer contain the message."
              accept="image/png,image/bmp"
              icon="image"
              onFile={chooseImage}
              error={imageError ?? fieldErrors.image ?? null}
            />
          )}
        </section>

        <section className="card stack" aria-labelledby="reveal-key-heading">
          <h2 id="reveal-key-heading" className="section__title">
            Unlock it
          </h2>
          <ChoiceGroup name="reveal-method" legend="How was it protected?" choices={UNLOCK_CHOICES} value={method} onChange={setMethod} />
          {method === "password" ? (
            <Field id="reveal-password" label="Password" error={fieldErrors.password ?? null}>
              {(describedBy) => (
                <PasswordInput
                  id="reveal-password"
                  value={password}
                  onChange={setPassword}
                  describedBy={describedBy}
                  isInvalid={Boolean(fieldErrors.password)}
                  autoComplete="off"
                />
              )}
            </Field>
          ) : (
            <div className="stack">
              {privateKey ? (
                <div className="file-chip">
                  <span>
                    Private key: <strong>{privateKey.name}</strong>
                  </span>
                  <Button variant="ghost" icon="close" onClick={() => setPrivateKey(null)}>
                    Remove
                  </Button>
                </div>
              ) : (
                <FileDrop
                  label="Choose your private key (.pem)"
                  hint="The file is read in your browser and sent only with this request; it is never stored."
                  accept=".pem,.key,.txt,application/x-pem-file"
                  icon="key"
                  onFile={(file) => void choosePrivateKey(file)}
                  error={privateKeyError ?? fieldErrors.privateKey ?? null}
                />
              )}
              <Field
                id="reveal-passphrase"
                label="Key passphrase"
                optional
                hint="Only if you set a passphrase when you created the key."
              >
                {(describedBy) => (
                  <PasswordInput
                    id="reveal-passphrase"
                    value={passphrase}
                    onChange={setPassphrase}
                    describedBy={describedBy}
                    autoComplete="off"
                  />
                )}
              </Field>
            </div>
          )}
        </section>

        <Disclosure summary="Advanced options">
          <ChoiceGroup
            name="reveal-layout"
            legend="Where the sender placed the bits"
            choices={LAYOUT_CHOICES}
            value={layout}
            onChange={setLayout}
            layout="stack"
          />
        </Disclosure>

        {reveal.state.status === "error" && <ErrorAlert error={reveal.state.error} />}

        <div className="form__actions">
          <Button
            type="submit"
            variant="primary"
            icon="reveal"
            isLoading={reveal.state.status === "loading"}
            loadingLabel="Verifying and decrypting…"
          >
            Reveal message
          </Button>
        </div>
      </form>

      {reveal.state.status === "success" && (
        <RevealedMessage result={reveal.state.data} sourceName={image ? describeFile(image) : ""} onClear={reveal.reset} />
      )}
    </>
  );
}

function describeStegoProblem(file: File, maxBytes: number | undefined): string | null {
  if (LOSSY_TYPES.has(file.type)) {
    return "This is a JPEG or WebP image. Compression destroys hidden messages, so nothing can be recovered. Ask the sender for the original PNG file.";
  }
  if (!STEGO_TYPES.has(file.type)) return "Choose a PNG (or BMP) image.";
  if (maxBytes !== undefined && file.size > maxBytes) {
    return `This file is ${formatBytes(file.size)}; the limit is ${formatBytes(maxBytes)}.`;
  }
  return null;
}

interface RevealedMessageProps {
  result: RevealResult;
  sourceName: string;
  onClear: () => void;
}

function RevealedMessage({ result, sourceName, onClear }: RevealedMessageProps) {
  const isText = result.encoding === "utf-8";
  return (
    <section className="card stack result" aria-labelledby="revealed-heading">
      <Alert tone="success" title="Message verified and decrypted" live>
        It was not changed after it was hidden. {formatBytes(result.message_bytes)} from {sourceName}.
      </Alert>
      <h2 id="revealed-heading" className="section__title">
        Hidden message
      </h2>
      {!isText && (
        <Alert tone="info">This message isn't text, so it is shown in Base64. Download it to get the original bytes.</Alert>
      )}
      <pre className="message-box" role="region" tabIndex={0} aria-label="Decrypted message">
        {result.message}
      </pre>
      <div className="form__actions">
        <CopyButton text={result.message} label="Copy message" />
        {!isText && (
          <Button
            variant="secondary"
            icon="download"
            onClick={() => saveFile(base64ToBlob(result.message), "message.bin")}
          >
            Download bytes
          </Button>
        )}
        <Button variant="ghost" icon="trash" onClick={onClear}>
          Clear from screen
        </Button>
      </div>
    </section>
  );
}

function base64ToBlob(base64: string): Blob {
  const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
  return new Blob([bytes], { type: "application/octet-stream" });
}
