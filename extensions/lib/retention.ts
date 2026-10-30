import { evidenceSha256, objectRefKey, sha256Value } from "../json.ts";
import { messageRole } from "./canonical.ts";
import { projectActiveContext } from "./folding.ts";
import { exactMapped, pricedBytes } from "./measurement.ts";
import { flattenFoldRefs } from "./persistence.ts";
import {
  addPendingMark, commitPendingMarks, consolidationMarks, markSpanRefs,
  pendingMarks, toolClipAdditions, withPendingMarks,
} from "./scheduling.ts";
import type { ActiveContextSnapshot, ActiveContextState, PendingMark } from "./policy.ts";

export type Relevance = "ordinary" | "useful" | "keep-original";
export interface RetentionCandidate {
  id: string;
  sourceHash: string;
  sourceIds: string[];
  brief: string;
  originalVisible: boolean;
}
export interface RetentionJudgment {
  id: string;
  sourceHash: string;
  relevance: Relevance;
  reason: string;
}
export interface RetentionRequest {
  key: string;
  candidates: RetentionCandidate[];
  /** Adapters choose a suitable source view; no separate task record is maintained. */
  messages: readonly unknown[];
}
export interface RetentionService {
  enabled?: () => boolean;
  assess: (request: RetentionRequest, signal: AbortSignal) => Promise<RetentionJudgment[]>;
  onError?: (error: unknown) => void;
}

export function assessmentKey(snapshot: ActiveContextSnapshot, generation: number): string {
  const user = snapshot.messages.findLast((message) => messageRole(message) === "user");
  return sha256Value({ session: snapshot.sessionId, generation, user: user ? evidenceSha256(user) : null });
}

export function retentionCandidates(snapshot: ActiveContextSnapshot, state: ActiveContextState): RetentionCandidate[] {
  const clipped = new Set((state.clips ?? []).map((clip) => clip.entryId));
  const collapsed = new Set(state.folds.filter((fold) => !state.expanded.includes(fold.id))
    .flatMap((fold) => flattenFoldRefs(fold, state).map(objectRefKey)));
  return pendingMarks(state).flatMap((mark) => {
    const span = markSpanRefs(state, mark);
    if (span.unresolved || !span.refs.length) return [];
    const current = span.refs.map((ref) => exactMapped(snapshot, ref)?.ref);
    if (current.some((ref) => !ref)) return [];
    return [{
      id: mark.id,
      sourceHash: sha256Value(current),
      sourceIds: span.refs.map((ref) => ref.entryId),
      brief: mark.mark === "fold" ? mark.brief : state.folds.find((fold) => fold.id === mark.id)?.brief ?? "",
      originalVisible: span.refs.every((ref) => !clipped.has(ref.entryId) && !collapsed.has(objectRefKey(ref))),
    }];
  });
}

/** One nonblocking inference per approach; an obsolete response cannot reopen a fold. */
export class RetentionAssessment {
  private epoch = 0;
  private latched = false;
  private key: string | null = null;
  private controller: AbortController | null = null;
  private ready: RetentionJudgment[] = [];
  private applied: RetentionJudgment[] = [];
  private failed = false;
  private error: string | null = null;

  constructor(private readonly service?: RetentionService) {}

  enabled(): boolean { return Boolean(this.service && (this.service.enabled?.() ?? true)); }

  observe(request: RetentionRequest, occupancy: number | null, approach: number, onFailure?: (error: unknown) => void): void {
    if (!this.enabled()) { this.reset(); return; }
    if (this.key !== request.key) {
      this.controller?.abort();
      this.controller = null;
      this.ready = [];
      this.applied = [];
      this.epoch += 1;
      this.key = request.key;
      // Invalidation does not schedule another inference in the same approach.
    }
    if (occupancy === null) return;
    if (occupancy < approach) {
      if (this.latched) {
        this.controller?.abort();
        this.controller = null;
        this.epoch += 1;
        this.ready = [];
      }
      this.latched = false;
      return;
    }
    if (this.latched || !request.candidates.length) return;
    this.latched = true;
    const epoch = this.epoch;
    const controller = new AbortController();
    this.controller = controller;
    const candidates = new Map(request.candidates.map((candidate) => [candidate.id, { ...candidate }]));
    void Promise.resolve().then(() => this.service!.assess(request, controller.signal)).then((rows) => {
      if (controller.signal.aborted || epoch !== this.epoch || this.key !== request.key || !this.enabled()) return;
      if (!Array.isArray(rows)) throw new Error("Decision backend returned no judgment array");
      const seen = new Set<string>();
      for (const row of rows) {
        const candidate = candidates.get(row?.id);
        if (!candidate || candidate.sourceHash !== row.sourceHash || seen.has(row.id) ||
            !["ordinary", "useful", "keep-original"].includes(row.relevance) || typeof row.reason !== "string") {
          throw new Error("Decision backend returned an invalid or mismatched judgment");
        }
        seen.add(row.id);
      }
      this.ready = rows.map((row) => ({ ...row }));
      this.failed = false;
      this.error = null;
    }).catch((error: unknown) => {
      if (controller.signal.aborted || epoch !== this.epoch) return;
      this.ready = [];
      this.error = error instanceof Error ? error.message : String(error);
      if (!this.failed) {
        this.failed = true;
        onFailure?.(error);
        this.service?.onError?.(error);
      }
    });
  }

  status() { return { enabled: this.enabled(), error: this.error, judgments: this.ready.length, held: this.applied.length }; }

  judgments(key: string, manual = false): RetentionJudgment[] {
    if (!this.enabled() || key !== this.key) return [];
    return (manual ? this.applied : this.ready).map((row) => ({ ...row }));
  }

  committed(held: RetentionJudgment[] = []): void {
    this.controller?.abort();
    this.controller = null;
    this.epoch += 1;
    this.latched = false;
    this.ready = [];
    this.applied = held.map((row) => ({ ...row }));
  }

  reset(): void {
    this.committed();
    this.key = null;
    this.failed = false;
    this.error = null;
  }
}

/** Execute the existing fold/consolidate/clip sequence on an isolated state. */
export async function selectCommit(input: {
  snapshot: ActiveContextSnapshot;
  state: ActiveContextState;
  generation: number;
  ordinal: number;
  applyTargetBytes?: number;
  clipThreshold: number;
  blacklist: ReadonlySet<string>;
  judgments?: RetentionJudgment[];
}) {
  const { snapshot, state } = input;
  const candidates = new Map((input.judgments?.length ? retentionCandidates(snapshot, state) : [])
    .map((candidate) => [candidate.id, candidate]));
  const judgments = new Map((input.judgments ?? []).filter((row) =>
    candidates.get(row.id)?.sourceHash === row.sourceHash).map((row) => [row.id, row]));
  const grade = { ordinary: 0, useful: 1, "keep-original": 2 };
  const priority = (mark: PendingMark) => grade[judgments.get(mark.id)?.relevance ?? "ordinary"];
  const keep = pendingMarks(state).filter((mark) =>
    judgments.get(mark.id)?.relevance === "keep-original" && candidates.get(mark.id)?.originalVisible);

  const evaluate = async (holds: PendingMark[]) => {
    const protectedRefs = new Map(state.protected.map((ref) => [objectRefKey(ref), ref]));
    for (const mark of holds) for (const ref of markSpanRefs(state, mark).refs) protectedRefs.set(objectRefKey(ref), ref);
    const guarded = { ...state, protected: [...protectedRefs.values()] };
    let result = await commitPendingMarks({
      snapshot, state: guarded, generation: input.generation, retainIneligible: true,
      ...(input.applyTargetBytes === undefined ? {} : { applyTargetBytes: input.applyTargetBytes }),
      ...(judgments.size ? { priority } : {}),
    });
    let closingAdded = 0;
    for (;;) {
      let closing = result.state;
      const heldBack = pendingMarks(closing);
      let seeded = withPendingMarks(closing, []);
      let added = 0;
      for (const mark of consolidationMarks({ snapshot, state: closing, ordinal: input.ordinal })) {
        const addition = addPendingMark(closing, mark);
        if (!addition.added) continue;
        closing = addition.state;
        const carried = addPendingMark(seeded, mark);
        if (carried.added) { seeded = carried.state; closingAdded += 1; added += 1; }
      }
      if (!added) break;
      const closed = await commitPendingMarks({ snapshot, state: seeded, generation: input.generation, retainIneligible: true });
      if (!closed.applied.length) break;
      result = {
        ...closed,
        state: withPendingMarks(closed.state, [...pendingMarks(closed.state), ...heldBack]),
        applied: [...result.applied, ...closed.applied],
        refused: [...result.refused.filter((mark) => !mark.retained), ...closed.refused],
        retained: [...result.retained.filter((mark) => !closed.applied.some((applied) => applied.id === mark.id)), ...closed.retained],
      };
    }
    const clips = result.applied.length ? toolClipAdditions({
      snapshot, state: result.state, threshold: input.clipThreshold, blacklist: input.blacklist,
    }) : [];
    if (clips.length) result = { ...result, state: { ...result.state, clips: [...(result.state.clips ?? []), ...clips] } };
    // Automatic protection belongs to the plan, not the persisted explicit-pin set.
    result = { ...result, state: { ...result.state, protected: state.protected } };
    return { result, closingAdded, clippedResults: clips.length,
      bytes: pricedBytes(projectActiveContext(snapshot, result.state)) };
  };

  const baseline = await evaluate([]);
  if (input.applyTargetBytes === undefined || !keep.length) return { ...baseline, held: [] as RetentionJudgment[] };
  const target = Math.max(0, pricedBytes(projectActiveContext(snapshot, state)) - input.applyTargetBytes);
  const ceiling = Math.max(target, baseline.bytes);
  while (keep.length) {
    const planned = await evaluate(keep);
    if (planned.bytes <= ceiling) return { ...planned, held: keep.map((mark) => judgments.get(mark.id)!) };
    // Equal-grade keeps release oldest first, retaining native recency preference.
    keep.shift();
  }
  return { ...baseline, held: [] as RetentionJudgment[] };
}
