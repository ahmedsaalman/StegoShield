import { useEffect } from "react";
import { Link } from "react-router-dom";

import { Card } from "../components/Card";
import { Icon } from "../components/Icon";
import { HeroVisual } from "../components/illustrations/HeroVisual";
import { StepArt, type StepArtName } from "../components/illustrations/StepArt";
import { ToolArt, type ToolArtName } from "../components/illustrations/ToolArt";

const TOOLS: { to: string; art: ToolArtName; title: string; description: string }[] = [
  {
    to: "/hide",
    art: "hide",
    title: "Hide a message",
    description: "Encrypt a message and hide it inside an image that looks unchanged.",
  },
  {
    to: "/reveal",
    art: "reveal",
    title: "Reveal a message",
    description: "Recover a hidden message with the password or your private key.",
  },
  {
    to: "/preflight",
    art: "preflight",
    title: "Pre-flight check",
    description: "Before hiding, see how much fits and how likely a detector is to notice.",
  },
  {
    to: "/detect",
    art: "detect",
    title: "Detect hidden data",
    description: "Scan any image for the statistical traces that hidden messages leave.",
  },
];

const STEPS: { art: StepArtName; title: string; text: string }[] = [
  {
    art: "encrypt",
    title: "Encrypt",
    text: "The message is sealed with AES-256-GCM, using a password or the recipient's public key.",
  },
  {
    art: "scatter",
    title: "Scatter",
    text: "Encrypted bits go into the lowest bit of pixels, at positions only the key can compute.",
  },
  {
    art: "verify",
    title: "Verify",
    text: "On reveal, a wrong key or an edited pixel is caught. You get the message or a clear error, never garbage.",
  },
];

const PRIVACY_POINTS = [
  "Nothing is saved. Images, messages and keys are processed in memory and discarded after each request.",
  "Private keys are generated for you and shown once. Keep the file safe; it can't be recovered.",
  "Send the result as a file, not as a photo. Chat apps recompress photos, which erases the message.",
];

function formatIndex(index: number): string {
  return String(index + 1).padStart(2, "0");
}

export function HomePage() {
  useEffect(() => {
    document.title = "StegoShield";
  }, []);

  return (
    <>
      <section className="hero" aria-labelledby="hero-title">
        <div className="container hero__layout">
          <div className="hero__inner">
            <p className="page-header__eyebrow">Encrypted steganography · Steganalysis</p>
            <h1 id="hero-title" className="hero__title" tabIndex={-1}>
              Hide messages in plain sight.
            </h1>
            <p className="hero__lead">
              Encrypt a message, hide it inside an ordinary image, check how detectable it is, and scan images for
              hidden data.
            </p>
            <div className="actions">
              <Link to="/hide" className="btn btn--primary btn--lg">
                Hide a message
              </Link>
              <Link to="/detect" className="btn btn--secondary btn--lg">
                Scan an image
              </Link>
            </div>
          </div>
          <HeroVisual />
        </div>
      </section>

      <div className="container">
        <section className="section" aria-labelledby="tools-heading">
          <div className="section__header">
            <h2 id="tools-heading" className="section-title">
              Tools
            </h2>
            <p className="text-muted">
              Everything runs on this server. Nothing leaves it, and nothing is kept. Want the evidence? See the{" "}
              <Link to="/lab">Evaluation Lab</Link>.
            </p>
          </div>
          <ul className="feature-grid">
            {TOOLS.map((tool, index) => (
              <li key={tool.to}>
                <Link to={tool.to} className="feature">
                  <span className="feature__art">
                    <ToolArt name={tool.art} />
                  </span>
                  <span className="feature__index">{formatIndex(index)}</span>
                  <span className="feature__title">
                    {tool.title}
                    <Icon name="arrowRight" />
                  </span>
                  <span className="feature__description">{tool.description}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>

        <section className="section" aria-labelledby="how-heading">
          <div className="section__header">
            <h2 id="how-heading" className="section-title">
              How it works
            </h2>
          </div>
          <ol className="steps">
            {STEPS.map((step, index) => (
              <li key={step.title} className="steps__item">
                <StepArt name={step.art} />
                <span className="steps__number">{formatIndex(index)}</span>
                <span className="steps__title">{step.title}</span>
                <span className="steps__text">{step.text}</span>
              </li>
            ))}
          </ol>
        </section>

        <div className="section">
          <Card title="Your data stays yours" step="Privacy">
            <ul className="check-list">
              {PRIVACY_POINTS.map((point) => (
                <li key={point}>
                  <Icon name="check" />
                  <span>{point}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}
