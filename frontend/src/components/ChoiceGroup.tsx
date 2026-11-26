import type { ReactNode } from "react";

export interface Choice<T extends string> {
  value: T;
  label: string;
  description?: ReactNode;
  badge?: string;
}

interface ChoiceGroupProps<T extends string> {
  name: string;
  legend: string;
  choices: Choice<T>[];
  value: T;
  onChange: (value: T) => void;
  layout?: "row" | "stack";
  /** Hide the legend visually when a heading right above already says the same thing. */
  isLegendVisible?: boolean;
}

/** Native radio buttons styled as cards: keyboard and screen-reader behaviour come for free. */
export function ChoiceGroup<T extends string>({
  name,
  legend,
  choices,
  value,
  onChange,
  layout = "row",
  isLegendVisible = true,
}: ChoiceGroupProps<T>) {
  return (
    <fieldset className="choice-group">
      <legend className={isLegendVisible ? "field__label" : "visually-hidden"}>{legend}</legend>
      <div className={`choice-group__options choice-group__options--${layout}`}>
        {choices.map((choice) => {
          const id = `${name}-${choice.value}`;
          return (
            <label key={choice.value} className="choice" htmlFor={id}>
              <input
                id={id}
                type="radio"
                name={name}
                value={choice.value}
                checked={value === choice.value}
                onChange={() => onChange(choice.value)}
              />
              <span className="choice__text">
                <span className="choice__label">
                  {choice.label}
                  {choice.badge && <span className="tag">{choice.badge}</span>}
                </span>
                {choice.description && <span className="choice__description">{choice.description}</span>}
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
