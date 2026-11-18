import { StartSessionButton } from "../session/StartSessionButton";
import { NO_PLAN_YET } from "./copy";

/**
 * docs/DESIGN.md "Screens: Today": the hero. The signature gradient is its background
 * and every word sits on the inner `glass-hero` layer, never on the gradient itself.
 * It will name the next planned block once the planner exists (Phase 4); until then
 * it says so.
 */
export function NextUpCard() {
  return (
    <section
      aria-labelledby="next-up-heading"
      className="rounded-xl bg-[image:var(--gradient)] p-3 shadow-md sm:p-4"
    >
      <div className="glass-hero rounded-lg p-6 sm:p-7">
        <p className="type-label text-muted mb-3">Next up</p>
        <h2 id="next-up-heading" className="type-h2">
          Nothing planned yet
        </h2>
        <p className="text-muted mt-2">{NO_PLAN_YET}</p>
        <div className="mt-6">
          <StartSessionButton />
        </div>
      </div>
    </section>
  );
}
