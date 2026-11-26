import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { CopyButton } from "../components/CopyButton";
import { ErrorAlert } from "../components/ErrorAlert";
import { Field } from "../components/Field";
import { PageHeader } from "../components/PageHeader";
import { PasswordInput } from "../components/PasswordInput";
import { api, type KeyPair, type PublicKeyInfo } from "../lib/api";
import { saveFile } from "../lib/download";
import { useRequest } from "../lib/useRequest";
import { useAppState } from "../state/AppState";

const PEM_MIME_TYPE = "application/x-pem-file";

export function KeysPage() {
  return (
    <>
      <PageHeader
        title="Keys"
        description="Public-key protection lets people send you messages without sharing a password. Create your key pair once, then give your public key to anyone who should be able to write to you."
      />
      <div className="stack-lg">
        <GenerateKeyPair />
        <RecipientKey />
      </div>
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

  return (
    <section className="card stack" aria-labelledby="generate-heading">
      <h2 id="generate-heading" className="section__title">
        Your key pair
      </h2>
      {generation.state.status === "success" ? (
        <GeneratedKeys keys={generation.state.data} onClear={clearKeys} />
      ) : (
        <form className="stack" onSubmit={handleSubmit} noValidate>
          <div className="grid-2">
            <Field
              id="key-passphrase"
              label="Passphrase for the private key file"
              optional
              hint="Encrypts the downloaded private key, so a stolen file is useless without it."
            >
              {(describedBy) => (
                <PasswordInput
                  id="key-passphrase"
                  value={passphrase}
                  onChange={setPassphrase}
                  describedBy={describedBy}
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
          {generation.state.status === "error" && <ErrorAlert error={generation.state.error} />}
          <div className="form__actions">
            <Button
              type="submit"
              variant="primary"
              icon="key"
              isLoading={generation.state.status === "loading"}
              loadingLabel="Generating…"
            >
              Generate key pair
            </Button>
          </div>
        </form>
      )}
    </section>
  );
}

function GeneratedKeys({ keys, onClear }: { keys: KeyPair; onClear: () => void }) {
  return (
    <div className="stack">
      <Alert tone="success" title="Key pair created" live>
        Download both files now. They are not stored anywhere, so this is your only chance.
      </Alert>

      <div className="stack-sm">
        <h3 className="subsection-title">Public key: share this</h3>
        <pre className="code-block" role="region" tabIndex={0} aria-label="Your public key">
          {keys.public_key_base64}
        </pre>
        <p className="text-muted">
          Fingerprint <code className="fingerprint">{keys.fingerprint}</code>. Senders can compare it to make sure they
          have your real key.
        </p>
        <div className="form__actions">
          <CopyButton text={keys.public_key_base64} label="Copy public key" />
          <Button
            variant="secondary"
            icon="download"
            onClick={() => saveFile(keys.public_key_pem, "stegoshield-public.pem", PEM_MIME_TYPE)}
          >
            Download public key
          </Button>
        </div>
      </div>

      <div className="stack-sm">
        <h3 className="subsection-title">Private key: keep this secret</h3>
        <Alert tone="warning" title="Anyone with this file can read messages sent to you">
          Store it somewhere safe and never send it to anyone. If you lose it, messages sent to this key can't be
          recovered.
          {!keys.is_private_key_encrypted && " It has no passphrase, so protect the file itself."}
        </Alert>
        <div className="form__actions">
          <Button
            variant="secondary"
            icon="download"
            onClick={() => saveFile(keys.private_key_pem, "stegoshield-private.pem", PEM_MIME_TYPE)}
          >
            Download private key
          </Button>
          <Button variant="ghost" icon="trash" onClick={onClear}>
            Clear keys from screen
          </Button>
        </div>
      </div>
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
    <section className="card stack" aria-labelledby="recipient-heading">
      <h2 id="recipient-heading" className="section__title">
        Someone else's public key
      </h2>
      <p className="text-muted">
        Check a key someone gave you, then use it on the <Link to="/hide">Hide</Link> page. It is kept only until you
        close this tab.
      </p>

      {recipientKey && (
        <div className="file-chip">
          <span>
            Saved for this session: <code className="fingerprint">{recipientKey.fingerprint}</code>
          </span>
          <Button variant="ghost" icon="trash" onClick={() => setRecipientKey(null)}>
            Remove
          </Button>
        </div>
      )}

      <form className="stack" onSubmit={handleSubmit} noValidate>
        <Field id="recipient-key" label="Public key" hint="Paste it as PEM, Base64 or hex.">
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
        <div className="form__actions">
          <Button
            type="submit"
            variant="secondary"
            icon="check"
            disabled={!keyText.trim()}
            isLoading={inspection.state.status === "loading"}
            loadingLabel="Checking…"
          >
            Check key
          </Button>
        </div>
      </form>
    </section>
  );
}
