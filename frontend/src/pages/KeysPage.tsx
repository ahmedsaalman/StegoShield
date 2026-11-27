import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { CopyButton } from "../components/CopyButton";
import { ErrorAlert } from "../components/ErrorAlert";
import { Field } from "../components/Field";
import { ToolArt } from "../components/illustrations/ToolArt";
import { PageBody, PageHeader } from "../components/PageHeader";
import { PasswordInput } from "../components/PasswordInput";
import { ScrambleText } from "../components/ScrambleText";
import { api, type ExampleKeyPair, type KeyPair, type PublicKeyInfo } from "../lib/api";
import { saveFile } from "../lib/download";
import { useRequest } from "../lib/useRequest";
import { useAppState } from "../state/AppState";

const PEM_MIME_TYPE = "application/x-pem-file";

export function KeysPage() {
  return (
    <>
      <PageHeader
        eyebrow="Set up"
        art={<ToolArt name="keys" isAmbient />}
        title="Keys"
        description="Public-key protection lets people send you messages without sharing a password. Create your key pair once, then give your public key to anyone who should be able to write to you."
      />
      <PageBody isNarrow>
        <div className="stack-lg">
          <GenerateKeyPair />
          <RecipientKey />
          <ExampleKeys />
        </div>
      </PageBody>
    </>
  );
}

function GenerateKeyPair() {
  const [passphrase, setPassphrase] = useState("");
  const [confirmPassphrase, setConfirmPassphrase] = useState("");
  const [mismatch, setMismatch] = useState(false);
  const generation = useRequest<KeyPair>();

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const isMismatch = passphrase !== confirmPassphrase;
    setMismatch(isMismatch);
    if (isMismatch) return;
    void generation.run((signal) => api.generateKeyPair(passphrase, signal));
  }

  function clearKeys() {
    generation.reset();
    setPassphrase("");
    setConfirmPassphrase("");
  }

  if (generation.state.status === "success") {
    return <GeneratedKeys keys={generation.state.data} onClear={clearKeys} />;
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      <Card
        title="Your key pair"
        description="An X25519 key pair. The public key is for sharing; the private key opens messages sent to you."
        footer={
          <>
            <span>Nothing is stored. You download both files once.</span>
            <Button
              type="submit"
              variant="primary"
              size="sm"
              icon="key"
              isLoading={generation.state.status === "loading"}
              loadingLabel="Generating…"
            >
              Generate key pair
            </Button>
          </>
        }
      >
        <div className="grid-2">
          <Field id="key-passphrase" label="Passphrase" optional>
            {(describedBy) => (
              <PasswordInput
                id="key-passphrase"
                value={passphrase}
                onChange={setPassphrase}
                describedBy={describedBy ? `${describedBy} key-passphrase-advice` : "key-passphrase-advice"}
                autoComplete="new-password"
              />
            )}
          </Field>
          <Field
            id="key-passphrase-confirm"
            label="Confirm passphrase"
            optional
            error={mismatch ? "The passphrases don't match." : null}
          >
            {(describedBy) => (
              <PasswordInput
                id="key-passphrase-confirm"
                value={confirmPassphrase}
                onChange={setConfirmPassphrase}
                describedBy={describedBy}
                isInvalid={mismatch}
                autoComplete="new-password"
              />
            )}
          </Field>
        </div>
        <p className="field__hint" id="key-passphrase-advice">
          Encrypts the downloaded private key file, so a stolen copy is useless without it.
        </p>
        {generation.state.status === "error" && <ErrorAlert error={generation.state.error} />}
      </Card>
    </form>
  );
}

function GeneratedKeys({ keys, onClear }: { keys: KeyPair; onClear: () => void }) {
  return (
    <div className="stack-lg">
      <Alert tone="success" title="Key pair created" live>
        Download both files now. They are not stored anywhere, so this is your only chance.
      </Alert>
      <Card
        step="Share this"
        title="Public key"
        footer={
          <>
            <span>
              Fingerprint <code className="fingerprint">{keys.fingerprint}</code>
            </span>
            <div className="actions">
              <Button
                variant="secondary"
                size="sm"
                icon="download"
                onClick={() => saveFile(keys.public_key_pem, "stegoshield-public.pem", PEM_MIME_TYPE)}
              >
                Download .pem
              </Button>
              <CopyButton text={keys.public_key_base64} label="Copy" />
            </div>
          </>
        }
      >
        <pre className="code-block" role="region" tabIndex={0} aria-label="Your public key">
          <ScrambleText text={keys.public_key_base64} durationMs={700} />
        </pre>
        <p className="text-muted">Senders can compare the fingerprint to be sure they have your real key.</p>
      </Card>
      <Card
        step="Keep this secret"
        title="Private key"
        footer={
          <>
            <Button variant="ghost" size="sm" icon="trash" onClick={onClear}>
              Clear keys from screen
            </Button>
            <Button
              variant="primary"
              size="sm"
              icon="download"
              onClick={() => saveFile(keys.private_key_pem, "stegoshield-private.pem", PEM_MIME_TYPE)}
            >
              Download private key
            </Button>
          </>
        }
      >
        <Alert tone="warning" title="Anyone with this file can read messages sent to you">
          Store it somewhere safe and never send it to anyone. If you lose it, messages sent to this key can't be
          recovered.
          {!keys.is_private_key_encrypted && " It has no passphrase, so protect the file itself."}
        </Alert>
      </Card>
    </div>
  );
}

function RecipientKey() {
  const { recipientKey, setRecipientKey } = useAppState();
  const [keyText, setKeyText] = useState("");
  const inspection = useRequest<PublicKeyInfo>();

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!keyText.trim()) return;
    void inspection.run((signal) => api.inspectPublicKey(keyText, signal));
  }

  function saveChecked(info: PublicKeyInfo) {
    setRecipientKey({ publicKeyBase64: info.public_key_base64, fingerprint: info.fingerprint });
    setKeyText("");
    inspection.reset();
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      <Card
        title="Someone else's public key"
        description={
          <>
            Check a key someone gave you, then use it on the <Link to="/hide">Hide</Link> page. It's kept only until you
            close this tab.
          </>
        }
        footer={
          <>
            <span>PEM, Base64 or hex</span>
            <Button
              type="submit"
              variant="secondary"
              size="sm"
              icon="check"
              disabled={!keyText.trim()}
              isLoading={inspection.state.status === "loading"}
              loadingLabel="Checking…"
            >
              Check key
            </Button>
          </>
        }
      >
        {recipientKey && (
          <div className="file-chip">
            <span>
              In use for hiding <code className="fingerprint">{recipientKey.fingerprint}</code>
            </span>
            <Button variant="ghost" size="sm" icon="trash" onClick={() => setRecipientKey(null)}>
              Remove
            </Button>
          </div>
        )}
        <Field id="recipient-key" label="Public key">
          {(describedBy) => (
            <textarea
              id="recipient-key"
              className="input textarea textarea--mono"
              rows={3}
              value={keyText}
              onChange={(event) => {
                setKeyText(event.target.value);
                inspection.reset();
              }}
              aria-describedby={describedBy}
              spellCheck={false}
            />
          )}
        </Field>
        {inspection.state.status === "error" && <ErrorAlert error={inspection.state.error} />}
        {inspection.state.status === "success" && (
          <Alert
            tone="success"
            title="Valid public key"
            live
            action={
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  if (inspection.state.status === "success") saveChecked(inspection.state.data);
                }}
              >
                Use for hiding messages
              </Button>
            }
          >
            Fingerprint <code className="fingerprint">{inspection.state.data.fingerprint}</code>. Confirm it with the
            key's owner before relying on it.
          </Alert>
        )}
      </Card>
    </form>
  );
}

function ExampleKeys() {
  const { recipientKey, setRecipientKey } = useAppState();
  const example = useRequest<ExampleKeyPair>();
  const keys = example.state.status === "success" ? example.state.data : null;
  const isInUse = keys !== null && recipientKey?.fingerprint === keys.fingerprint;

  return (
    <Card
      step="Testing only"
      title="Just trying it out?"
      description="Use the built-in example key pair to try public-key hiding without creating or saving keys. It is the same pair for everyone, and its private key is shown right here."
      footer={
        keys ? (
          <>
            <span>
              Fingerprint <code className="fingerprint">{keys.fingerprint}</code>
            </span>
            <Button
              variant="secondary"
              size="sm"
              icon="check"
              disabled={isInUse}
              onClick={() => setRecipientKey({ publicKeyBase64: keys.public_key_base64, fingerprint: keys.fingerprint })}
            >
              {isInUse ? "In use for hiding" : "Use for hiding messages"}
            </Button>
          </>
        ) : (
          <>
            <span>Nothing to download or keep.</span>
            <Button
              variant="secondary"
              size="sm"
              icon="key"
              isLoading={example.state.status === "loading"}
              loadingLabel="Loading…"
              onClick={() => void example.run((signal) => api.exampleKeyPair(signal))}
            >
              Show example keys
            </Button>
          </>
        )
      }
    >
      {example.state.status === "error" && <ErrorAlert error={example.state.error} />}
      {keys && (
        <div className="stack">
          <Alert tone="warning" title="Anyone can read messages hidden with this key">
            Everyone has the example private key, so use it only to see how public-key mode works. For real messages,
            generate your own key pair above.
          </Alert>
          <ExampleKeyBlock half="public" text={keys.public_key_base64} pem={keys.public_key_pem} />
          <ExampleKeyBlock half="private" text={keys.private_key_pem} pem={keys.private_key_pem} />
          <p className="text-muted">
            Hide a message with the public key, then open it on the <Link to="/reveal">Reveal</Link> page with{" "}
            <em>Use the example private key</em>. No files needed.
          </p>
        </div>
      )}
    </Card>
  );
}

function ExampleKeyBlock({ half, text, pem }: { half: "public" | "private"; text: string; pem: string }) {
  const label = `Example ${half} key`;
  return (
    <div className="stack-sm">
      <div className="example-key__header">
        <h3 className="subsection-title">{label}</h3>
        <div className="actions">
          <Button
            variant="ghost"
            size="sm"
            icon="download"
            onClick={() => saveFile(pem, `stegoshield-example-${half}.pem`, PEM_MIME_TYPE)}
          >
            Download {half} key
          </Button>
          <CopyButton text={text} label={`Copy ${half} key`} />
        </div>
      </div>
      <pre className="code-block" role="region" tabIndex={0} aria-label={label}>
        {text}
      </pre>
    </div>
  );
}
