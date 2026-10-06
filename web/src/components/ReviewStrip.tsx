import { useState } from "react";

import type { RegenerateResult, ReviewItem } from "@/api";
import { Pill } from "@/components/Pill";

const COST_DECIMALS = 4;
const SECONDS_DECIMALS = 1;
const CONFIDENCE_DECIMALS = 2;

// Everything below is rendered as React text nodes: model-written evidence
// is never parsed as Markdown or HTML.
function Row({ item }: { item: ReviewItem }) {
  return (
    <li className="flex flex-col gap-(--spacing-8) border-t border-silver py-(--spacing-12) first:border-t-0">
      <div className="flex flex-wrap items-center gap-(--spacing-8)">
        <Pill>{`.puml:${item.line}`}</Pill>
        <span className="font-mono text-caption">{item.source}</span>
        <Pill tone="ink">{item.kind}</Pill>
        <span className="font-mono text-caption">{item.target}</span>
        <span className="ml-auto text-caption text-smoke">{item.confidence.toFixed(CONFIDENCE_DECIMALS)}</span>
      </div>
      {item.evidence ? (
        <p className="text-body-sm text-carbon">{item.evidence}</p>
      ) : (
        <p className="text-body-sm text-smoke">No evidence recorded.</p>
      )}
    </li>
  );
}

// One-line bar at the bottom; the detail expands on demand so it doesn't
// take room from the code and diagram panes.
export function ReviewStrip({ result }: { result: RegenerateResult }) {
  const [open, setOpen] = useState(false);
  const { review } = result;

  return (
    <section className="relative shrink-0 rounded-(--radius-cards) bg-bone">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex w-full flex-wrap items-center justify-between gap-(--spacing-8) p-(--spacing-12) text-left"
      >
        <span className="text-caption font-medium tracking-(--tracking-caption)">
          {result.class_count} classes · {result.relationship_count} relationships · $
          {result.cost_usd.toFixed(COST_DECIMALS)} · {result.latency_seconds.toFixed(SECONDS_DECIMALS)}s ·{" "}
          {review.items.length} flagged · {result.warnings.length} warnings
        </span>
        <span className="text-caption font-medium underline">{open ? "Hide review" : "Show review"}</span>
      </button>

      {open ? (
        <div className="z-10 flex max-h-(--review-max-height) flex-col gap-(--spacing-12) overflow-auto border-t border-silver bg-bone p-(--spacing-16) lg:absolute lg:inset-x-0 lg:bottom-full lg:border lg:border-ink-black">
          {result.warnings.length > 0 ? (
            <>
              <ul className="list-disc pl-(--spacing-20) text-body-sm">
                {result.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
              <hr className="border-t border-silver" />
            </>
          ) : null}

          <div className="flex flex-wrap items-baseline justify-between gap-(--spacing-8)">
            <h2 className="text-body-sm font-medium">Review</h2>
            <p className="text-caption text-smoke">
              Confidence threshold {review.threshold.toFixed(CONFIDENCE_DECIMALS)}
            </p>
          </div>

          {review.items.length === 0 ? (
            <p className="text-body-sm">No relationships below the confidence threshold.</p>
          ) : (
            <ul>
              {review.items.map((item) => (
                <Row key={`${item.line}`} item={item} />
              ))}
            </ul>
          )}

          <p className="text-caption text-smoke">
            Confidence doesn&apos;t reliably track correctness. Check every relationship, flagged or not.
          </p>
        </div>
      ) : null}
    </section>
  );
}
