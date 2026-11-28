import { type FormEvent, useState } from "react";

import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { ChoiceGroup } from "../components/ChoiceGroup";
import { CopyButton } from "../components/CopyButton";
import { Disclosure } from "../components/Disclosure";
import { ErrorAlert } from "../components/ErrorAlert";
import { Field } from "../components/Field";
import { FileDrop } from "../components/FileDrop";
import { ToolArt } from "../components/illustrations/ToolArt";
import { ImagePreview } from "../components/ImagePreview";
import { PageBody, PageHeader } from "../components/PageHeader";
import { PasswordInput } from "../components/PasswordInput";
import { ScrambleText } from "../components/ScrambleText";
import {
  api,
  type EmbeddingLayout,
  type ExampleKeyPair,
  type KeyMethod,
  type RevealResult,
  type UnlockSecret,
} from "../lib/api";
import { saveFile } from "../lib/download";
import { formatBytes } from "../lib/format";
import { useRequest } from "../lib/useRequest";
import { useAppState } from "../state/AppState";
import { LAYOUT_CHOICES } from "./options";

const STEGO_TYPES = new Set(["image/png", "image/bmp"]);
const LOSSY_TYPES = new Set(["image/jpeg", "image/webp"]);
const MAX_PRIVATE_KEY_FILE_BYTES = 16 * 1024;
const EXAMPLE_PRIVATE_KEY_NAME = "Example private key (testing only)";

const UNLOCK_CHOICES = [
  { value: "password" as const, label: "Password", description: "The sender protected it with a password." },
  { value: "public_key" as const, label: "My private key", description: "The sender used your public key." },
];

type FieldErrors = Partial<Record<keyof typeof FIELD_IDS, string>>;

const FIELD_IDS = {
  image: "reveal-image",
  password: "reveal-password",
  privateKey: "reveal-private-key",
} as const;

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
  const [hasTriedSubmit, setHasTriedSubmit] = useState(false);
  const reveal = useRequest<RevealResult>();
  // Checked on every render once the user has tried to submit, so each message goes away as soon as it is fixed.
  const errors = validate();
  const fieldErrors: FieldErrors = hasTriedSubmit ? errors : {};

  function chooseImage(file: File) {
    reveal.reset();
    const problem = describeStegoProblem(file, meta?.limits.max_upload_bytes);
    setImageError(problem);
    setImage(problem ? null : file);
  }

  // A revealed message (or an error) belongs to the image it came from, so it goes when the image does.
  function removeImage() {
    reveal.reset();
    setImage(null);
  }

  const exampleKey = useRequest<ExampleKeyPair>();

  function fillExamplePrivateKey() {
    setPrivateKeyError(null);
    void exampleKey.run(async (signal) => {
      const example = await api.exampleKeyPair(signal);
      setPrivateKey({ name: EXAMPLE_PRIVATE_KEY_NAME, pem: example.private_key_pem });
      return example;
    });
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
    setHasTriedSubmit(true);
    const invalidField = (Object.keys(FIELD_IDS) as (keyof FieldErrors)[]).find((field) => errors[field]);
    if (invalidField || !image) {
      if (invalidField) document.getElementById(FIELD_IDS[invalidField])?.focus();
      return;
    }
    const unlock: UnlockSecret =
      method === "password" ? { method, password } : { method, privateKey: privateKey?.pem ?? "", passphrase };
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
        eyebrow="Receive"
        art={<ToolArt name="reveal" isAmbient />}
        title="Reveal a message"
        description="Open an image you received and recover the hidden message with the password or your private key."
      />
      <PageBody isNarrow>
        <div className="stack-lg">
          <form className="stack-lg" onSubmit={handleSubmit} noValidate>
            <Card
              step="Step 01"
              title="Image you received"
              footer={<span>Use the original PNG. Screenshots and re-sent photos no longer carry the message.</span>}
            >
              {image ? (
                <ImagePreview
                  file={image}
                  alt="The file you received"
                  onRemove={removeImage}
                  activity={reveal.state.status === "loading" ? "scanning" : null}
                />
              ) : (
                <FileDrop
                  id={FIELD_IDS.image}
                  label="Drop the image here or click to browse"
                  hint="PNG or BMP"
                  accept="image/png,image/bmp"
                  icon="upload"
                  onFile={chooseImage}
                  error={imageError ?? fieldErrors.image ?? null}
                />
              )}
            </Card>

            <Card step="Step 02" title="Unlock" description="Use the same method the sender chose.">
              <ChoiceGroup
                name="reveal-method"
                legend="How was it protected?"
                choices={UNLOCK_CHOICES}
                value={method}
                onChange={setMethod}
                isLegendVisible={false}
              />
              {method === "password" ? (
                <Field id={FIELD_IDS.password} label="Password" error={fieldErrors.password ?? null}>
                  {(describedBy) => (
                    <PasswordInput
                      id={FIELD_IDS.password}
                      value={password}
                      onChange={setPassword}
                      describedBy={describedBy}
                      isInvalid={Boolean(fieldErrors.password)}
                      autoComplete="off"
                    />
                  )}
                </Field>
              ) : (
                <PrivateKeyFields
                  privateKey={privateKey}
                  onChoose={(file) => void choosePrivateKey(file)}
                  onUseExample={fillExamplePrivateKey}
                  isLoadingExample={exampleKey.state.status === "loading"}
                  onRemove={() => setPrivateKey(null)}
                  error={privateKeyError ?? fieldErrors.privateKey ?? null}
                  passphrase={passphrase}
                  onPassphraseChange={setPassphrase}
                />
              )}
              {method === "public_key" && exampleKey.state.status === "error" && (
                <ErrorAlert error={exampleKey.state.error} />
              )}
            </Card>

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

            <div className="actions actions--end">
              <Button
                type="submit"
                variant="primary"
                size="lg"
                icon="reveal"
                isLoading={reveal.state.status === "loading"}
                loadingLabel="Verifying and decrypting…"
              >
                Reveal message
              </Button>
            </div>
          </form>

          {reveal.state.status === "success" && <RevealedMessage result={reveal.state.data} onClear={reveal.reset} />}
        </div>
      </PageBody>
    </>
  );
}

interface PrivateKeyFieldsProps {
  privateKey: { name: string; pem: string } | null;
  onChoose: (file: File) => void;
  onUseExample: () => void;
  isLoadingExample: boolean;
  onRemove: () => void;
  error: string | null;
  passphrase: string;
  onPassphraseChange: (value: string) => void;
}

function PrivateKeyFields({
  privateKey,
  onChoose,
  onUseExample,
  isLoadingExample,
  onRemove,
  error,
  passphrase,
  onPassphraseChange,
}: PrivateKeyFieldsProps) {
  return (
    <div className="stack">
      {privateKey ? (
        <div className="file-chip">
          <span>
            Private key <code className="fingerprint">{privateKey.name}</code>
          </span>
          <Button variant="ghost" size="sm" icon="close" onClick={onRemove}>
            Remove
          </Button>
        </div>
      ) : (
        <FileDrop
          id={FIELD_IDS.privateKey}
          label="Drop your private key here or click to browse"
          hint=".pem file. Read in your browser and sent only with this request; never stored."
          accept=".pem,.key,.txt,application/x-pem-file"
          icon="key"
          onFile={onChoose}
          error={error}
        />
      )}
      {!privateKey && (
        <div className="inline-action">
          <span className="text-muted">Hidden with the example key?</span>
          <Button
            variant="ghost"
            size="sm"
            icon="key"
            onClick={onUseExample}
            isLoading={isLoadingExample}
            loadingLabel="Loading…"
          >
            Use the example private key
          </Button>
        </div>
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
            onChange={onPassphraseChange}
            describedBy={describedBy}
            autoComplete="off"
          />
        )}
      </Field>
    </div>
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

function RevealedMessage({ result, onClear }: { result: RevealResult; onClear: () => void }) {
  const isText = result.encoding === "utf-8";
  return (
    <Card
      title="Hidden message"
      description="Verified: it was not changed after it was hidden."
      isLive
      footer={
        <>
          <span className="inline-stats">
            <span>{formatBytes(result.message_bytes)}</span>
            <span>{isText ? "UTF-8 text" : "Binary, shown as Base64"}</span>
          </span>
          <div className="actions">
            <Button variant="ghost" size="sm" icon="trash" onClick={onClear}>
              Clear
            </Button>
            {!isText && (
              <Button
                variant="secondary"
                size="sm"
                icon="download"
                onClick={() => saveFile(base64ToBlob(result.message), "message.bin")}
              >
                Download bytes
              </Button>
            )}
            <CopyButton text={result.message} label="Copy message" />
          </div>
        </>
      }
    >
      <pre className="message-box" role="region" tabIndex={0} aria-label="Decrypted message">
        <ScrambleText text={result.message} />
      </pre>
    </Card>
  );
}

function base64ToBlob(base64: string): Blob {
  const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
  return new Blob([bytes], { type: "application/octet-stream" });
}
