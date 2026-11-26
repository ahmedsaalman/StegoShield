import { Link } from "react-router-dom";

import { Icon, type IconName } from "../components/Icon";
import { PageHeader } from "../components/PageHeader";

interface Task {
  to: string;
  icon: IconName;
  title: string;
  description: string;
}

const TASKS: Task[] = [
  {
    to: "/hide",
    icon: "hide",
    title: "Hide a message",
    description: "Encrypt a message and hide it inside an image that looks unchanged.",
  },
  {
    to: "/reveal",
    icon: "reveal",
    title: "Reveal a message",
    description: "Recover a hidden message with the password or your private key.",
  },
  {
    to: "/preflight",
    icon: "gauge",
    title: "Pre-flight check",
    description: "Before hiding, see how much fits and how likely a detector is to notice.",
  },
  {
    to: "/detect",
    icon: "scan",
    title: "Detect hidden data",
    description: "Scan any image and get the probability that it carries a hidden message.",
  },
];

const STEPS = [
  {
    title: "Encrypt",
    text: "Your message is encrypted with AES-256-GCM using a password or the recipient's public key.",
  },
  {
    title: "Scatter",
    text: "The encrypted bits replace the lowest bit of pixels at positions only the key can find.",
  },
  {
    title: "Verify",
    text: "On reveal, any wrong key or edited pixel is caught. You get the message or a clear error, never garbage.",
  },
];

export function HomePage() {
  return (
    <>
      <PageHeader
        title="Hide messages in plain sight"
        description="StegoShield encrypts a message and hides it inside an ordinary-looking image, checks how detectable that would be, and scans images for hidden data."
      />

      <section aria-labelledby="tasks-heading" className="section">
        <h2 id="tasks-heading" className="visually-hidden">
          What do you want to do?
        </h2>
        <ul className="task-grid">
          {TASKS.map((task) => (
            <li key={task.to}>
              <Link to={task.to} className="task-card">
                <Icon name={task.icon} size={28} className="task-card__icon" />
                <span className="task-card__title">{task.title}</span>
                <span className="task-card__description">{task.description}</span>
                <span className="task-card__cta">
                  Start <Icon name="arrowRight" size={16} />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="how-heading" className="section">
        <h2 id="how-heading" className="section__title">
          How it works
        </h2>
        <ol className="steps">
          {STEPS.map((step) => (
            <li key={step.title} className="steps__item">
              <span className="steps__title">{step.title}</span>
              <span>{step.text}</span>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="privacy-heading" className="card section">
        <h2 id="privacy-heading" className="section__title">
          <Icon name="lock" /> Your data stays yours
        </h2>
        <ul className="list">
          <li>Nothing is saved. Images, messages and keys are processed in memory and discarded.</li>
          <li>Private keys are generated for you and shown once. Keep the file safe; it cannot be recovered.</li>
          <li>Send the result as a file, not as a photo. Chat apps recompress photos, which erases the message.</li>
        </ul>
      </section>
    </>
  );
}
