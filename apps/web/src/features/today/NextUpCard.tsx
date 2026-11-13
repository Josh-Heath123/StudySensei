import { StartSessionButton } from "../session/StartSessionButton";
import { NO_PLAN_YET } from "./copy";

/**
 * docs/DESIGN.md "Next-up card": the ink card. It will name the next planned block
 * once the planner exists (Phase 4); until then it says so.
 */
export function NextUpCard() {
  return (
    <section aria-labelledby="next-up-heading" className="bg-ink text-paper rounded-lg p-7">
      <p className="type-label text-on-dark-muted mb-3">Next up</p>
      <h2 id="next-up-heading" className="type-h2">
        Nothing planned yet
      </h2>
      <p className="text-on-dark-muted mt-3">{NO_PLAN_YET}</p>
      <div className="mt-6">
        <StartSessionButton />
      </div>
    </section>
  );
}
