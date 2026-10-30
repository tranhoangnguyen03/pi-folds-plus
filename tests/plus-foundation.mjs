import assert from "node:assert/strict";
import { setImmediate as nextTick } from "node:timers/promises";
import { test } from "node:test";
import { createJiti } from "jiti";
const jiti = createJiti(import.meta.url);
const json = await jiti.import("../extensions/json.ts");
const canonical = await jiti.import("../extensions/lib/canonical.ts");
const folding = await jiti.import("../extensions/lib/folding.ts");
const measurement = await jiti.import("../extensions/lib/measurement.ts");
const persistence = await jiti.import("../extensions/lib/persistence.ts");
const policy = await jiti.import("../extensions/lib/policy.ts");
const scheduling = await jiti.import("../extensions/lib/scheduling.ts");
const visibility = await jiti.import("../extensions/lib/visibility.ts");
const retention = await jiti.import("../extensions/lib/retention.ts");

function fixture(messages) {
  const sessionId = "plus-fixture";
  const refs = messages.map((message, index) => json.evidenceRef(sessionId, `entry-${index}`, message));
  return {
    sessionId, messages,
    mapped: messages.map((message, index) => ({ index, message, ref: refs[index] })),
    branchObjects: messages.map((message, index) => ({ branchIndex: index, message, ref: refs[index] })),
    completeTurns: [{ start: 0, end: messages.length }],
    freshBoundary: messages.length, protectedIndices: new Set(),
    policy: policy.ACTIVE_CONTEXT_POLICY, thresholds: { ...policy.DEFAULT_THRESHOLDS },
    budgetTokens: 100000, contextWindow: 100000, windowSource: "reported",
    toolName: "pi_fold_context", brandNoun: "pi-fold", entryTypePrefix: "pi-fold-active-context",
    blacklistAutoFoldTools: new Set(), readOnlyContextActions: policy.PEEK_READ_ONLY_CONTEXT_ACTIONS,
  };
}
const user = (text) => ({ role: "user", content: [{ type: "text", text }], timestamp: 1 });
const reply = (text) => ({ role: "assistant", content: [{ type: "text", text }], stopReason: "stop", timestamp: 2 });
function candidate(snapshot, start = 0, end = snapshot.messages.length) {
  const refs = snapshot.mapped.slice(start, end).map((item) => item.ref);
  return { kind: "chapter", parts: refs.map((ref) => ({ kind: "raw", ref })), sourceRefs: refs };
}
async function commit(snapshot, state, source) {
  const prepared = await folding.prepareFold({ snapshot, state, candidate: source, generation: 0 });
  return folding.commitPreparedFold({ snapshot, state, prepared, generation: 0 });
}
const projection = (snapshot, state) => JSON.stringify(folding.projectActiveContext(snapshot, state));
const bytes = (snapshot, state) => measurement.pricedBytes(folding.projectActiveContext(snapshot, state));
function staged(snapshot, state, sources) {
  return scheduling.withPendingMarks(state, sources.map((source, ordinal) => scheduling.foldMarkFor({
    candidate: source, brief: `Source group ${ordinal}: exact originals available`,
    briefProvenance: { kind: "deterministic" }, origin: "ladder", ordinal,
  })));
}
const select = (snapshot, state, extra = {}) => retention.selectCommit({
  snapshot, state, generation: 0, ordinal: 1, clipThreshold: 0, blacklist: new Set(), ...extra,
});

test("keep restores original detail; release changes eligibility without hiding", async () => {
  const snapshot = fixture([user("Keep the rollback rule."), reply("Shared profiles stay. ".repeat(600))]);
  const folded = await commit(snapshot, canonical.emptyActiveContextState(snapshot.sessionId), candidate(snapshot));
  const id = folded.folds[0].id;
  assert.equal(folding.foldPresentation(folded.folds[0], folded, snapshot), "folded");
  const kept = folding.protectEvidence(snapshot, folded, [id], true);
  assert.equal(folding.foldPresentation(kept.folds[0], kept, snapshot), "original");
  assert.ok(projection(snapshot, kept).includes("Shared profiles stay."));
  assert.throws(() => folding.setFoldProjectionState(kept, id, "folded"), /Release the keep/);
  const released = folding.protectEvidence(snapshot, kept, [id], false);
  assert.equal(projection(snapshot, released), projection(snapshot, kept));
  assert.equal(released.protected.length, 0);
  const roundTrip = persistence.parseActiveContextState(JSON.parse(JSON.stringify(released)), snapshot.sessionId);
  assert.equal(projection(snapshot, roundTrip), projection(snapshot, kept));
  const refolded = folding.setFoldProjectionState(roundTrip, id, "folded");
  assert.equal(folding.foldPresentation(refolded.folds[0], refolded, snapshot), "folded");
});

test("keep clears an existing clip; release does not recreate it", () => {
  const result = { role: "toolResult", toolName: "read", toolCallId: "call-a", isError: false,
    content: [{ type: "text", text: "Exact output. ".repeat(1000) }], timestamp: 3 };
  const snapshot = fixture([user("Read file"), { role: "assistant", stopReason: "toolUse", timestamp: 2,
    content: [{ type: "toolCall", id: "call-a", name: "read", arguments: { path: "file.txt" } }] }, result, reply("Done")]);
  const state = { ...canonical.emptyActiveContextState(snapshot.sessionId), clips: [{ callId: "call-a", entryId: "entry-2" }] };
  assert.ok(projection(snapshot, state).includes("clipped"));
  const kept = folding.protectEvidence(snapshot, state, ["entry-2"], true);
  assert.ok(!kept.clips?.length);
  assert.ok(!projection(snapshot, kept).includes("more chars clipped"));
  const released = folding.protectEvidence(snapshot, kept, ["entry-2"], false);
  assert.equal(projection(snapshot, kept), projection(snapshot, released));
});

test("nested keep restores its source closure; siblings remain folded and the card says mixed", async () => {
  const snapshot = fixture([user("First question"), reply("First source ".repeat(800)), user("Second"), reply("Second source ".repeat(800))]);
  let state = canonical.emptyActiveContextState(snapshot.sessionId);
  state = await commit(snapshot, state, candidate(snapshot, 0, 2));
  state = await commit(snapshot, state, candidate(snapshot, 2, 4));
  const children = [...state.folds];
  state = await commit(snapshot, state, { kind: "consolidation", parts: children.map((fold) => ({ kind: "fold", foldId: fold.id })),
    sourceRefs: snapshot.mapped.map((item) => item.ref) });
  const parent = state.folds.find((fold) => fold.kind === "consolidation");
  const kept = folding.protectEvidence(snapshot, state, ["entry-1"], true);
  assert.equal(folding.foldPresentation(parent, kept, snapshot), "mixed");
  assert.equal(folding.foldPresentation(children[0], kept, snapshot), "original");
  assert.equal(folding.foldPresentation(children[1], kept, snapshot), "folded");
  assert.equal(folding.foldStatusRow(parent, kept, snapshot).presentation, "mixed");
  const released = folding.protectEvidence(snapshot, kept, ["entry-1"], false);
  assert.equal(projection(snapshot, kept), projection(snapshot, released));
});

test("legacy protected visibility migrates once without mutating the checkpoint", async () => {
  const snapshot = fixture([user("Legacy"), reply("Original detail ".repeat(800))]);
  const folded = await commit(snapshot, canonical.emptyActiveContextState(snapshot.sessionId), candidate(snapshot));
  const old = { ...folded, protected: [snapshot.mapped[1].ref] };
  const saved = JSON.stringify(old);
  const migrated = visibility.preserveProtectedInclusion(old);
  assert.equal(JSON.stringify(old), saved);
  assert.equal(folding.foldPresentation(migrated.folds[0], migrated, snapshot), "original");
  assert.equal(visibility.preserveProtectedInclusion(migrated), migrated);
  const released = folding.protectEvidence(snapshot, migrated, ["entry-1"], false);
  assert.equal(projection(snapshot, migrated), projection(snapshot, released));
});

test("a queued refold respects a later keep and a live expansion lease", async () => {
  const snapshot = fixture([user("Lease"), reply("Lease original ".repeat(800))]);
  let state = await commit(snapshot, canonical.emptyActiveContextState(snapshot.sessionId), candidate(snapshot));
  const id = state.folds[0].id;
  state = folding.setFoldProjectionState(state, id, "expanded");
  state = scheduling.withPendingMarks(state, [{ mark: "refold", id, origin: "ladder", ordinal: 1 }]);
  const leased = folding.withExpandLease(state, id);
  assert.equal(scheduling.markEligibility(snapshot, leased, leased.pendingMarks[0]), "protected");
  const kept = folding.protectEvidence(snapshot, state, [id], true);
  const result = await scheduling.commitPendingMarks({ snapshot, state: kept, generation: 0, retainIneligible: true });
  assert.equal(result.applied.length, 0);
  assert.equal(projection(snapshot, result.state), projection(snapshot, kept));
});

test("base selection stays chronological; assessed selection keeps useful detail within the target", async () => {
  const snapshot = fixture([user("Fix the bug"), reply("Bug evidence. ".repeat(120)), user("Read old logs"), reply("Old test log. ".repeat(3000)), user("Current work"), reply("Continue")]);
  const state = staged(snapshot, canonical.emptyActiveContextState(snapshot.sessionId), [candidate(snapshot, 0, 2), candidate(snapshot, 2, 4)]);
  const applyTargetBytes = bytes(snapshot, state) - 6000;
  const vanilla = await scheduling.commitPendingMarks({ snapshot, state, generation: 0, retainIneligible: true, applyTargetBytes });
  const base = await select(snapshot, state, { applyTargetBytes });
  assert.equal(projection(snapshot, base.result.state), projection(snapshot, vanilla.state));
  const first = retention.retentionCandidates(snapshot, state)[0];
  const judgment = { id: first.id, sourceHash: first.sourceHash, relevance: "keep-original", reason: "Current bug evidence" };
  const planned = await select(snapshot, state, { applyTargetBytes, judgments: [judgment] });
  assert.equal(planned.held.length, 1);
  assert.ok(projection(snapshot, planned.result.state).includes("Bug evidence."));
  assert.ok(planned.bytes <= Math.max(6000, base.bytes));
  assert.equal(planned.result.state.protected.length, 0, "automatic holds do not become explicit persisted pins");
  const stale = await select(snapshot, state, { applyTargetBytes, judgments: [{ ...judgment, sourceHash: "old-source" }] });
  assert.equal(stale.held.length, 0);
  assert.equal(projection(snapshot, stale.result.state), projection(snapshot, base.result.state));
});

test("automatic holds yield to the target and emergency selection; explicit protection survives", async () => {
  const snapshot = fixture([user("A"), reply("A source ".repeat(3000)), user("B"), reply("B source ".repeat(3000)), user("Live"), reply("Working")]);
  const state = staged(snapshot, canonical.emptyActiveContextState(snapshot.sessionId), [candidate(snapshot, 0, 2), candidate(snapshot, 2, 4)]);
  const judgments = retention.retentionCandidates(snapshot, state).map((row) => ({ ...row, relevance: "keep-original", reason: "Useful" }));
  const plan = await select(snapshot, state, { applyTargetBytes: bytes(snapshot, state) - 4000, judgments });
  assert.equal(plan.held.length, 0);
  assert.ok(plan.bytes < 4000);
  const emergency = await select(snapshot, state, { judgments });
  assert.equal(emergency.held.length, 0);
  const explicit = folding.protectEvidence(snapshot, state, ["entry-1"], true);
  const protectedPlan = await select(snapshot, explicit, { applyTargetBytes: bytes(snapshot, explicit), judgments });
  assert.equal(protectedPlan.result.state.protected.length, explicit.protected.length);
  assert.ok(projection(snapshot, protectedPlan.result.state).includes("A source"));
});

test("assessment is once per approach, nonblocking, and rejects late, disabled or mismatched results", async () => {
  let calls = 0;
  let enabled = true;
  let resolve;
  const errors = [];
  const helper = new retention.RetentionAssessment({ enabled: () => enabled,
    assess: () => { calls += 1; return new Promise((done) => { resolve = done; }); }, onError: (error) => errors.push(error) });
  const request = { key: "branch-a", candidates: [{ id: "F1", sourceHash: "s1", sourceIds: ["entry-1"], brief: "Bug", originalVisible: true }], messages: [] };
  const row = { id: "F1", sourceHash: "s1", relevance: "keep-original", reason: "Needed" };
  helper.observe(request, .60, .70);
  await nextTick(); assert.equal(calls, 0);
  helper.observe(request, .71, .70);
  helper.observe(request, .75, .70);
  await nextTick(); assert.equal(calls, 1);
  assert.deepEqual(helper.judgments(request.key), []);
  helper.committed(); resolve([row]); await nextTick();
  assert.deepEqual(helper.judgments(request.key), []);
  helper.observe(request, .73, .70); await nextTick(); resolve([row]); await nextTick();
  assert.equal(helper.judgments(request.key).length, 1);
  enabled = false; helper.observe(request, .76, .70);
  assert.deepEqual(helper.judgments(request.key), []);
  enabled = true; helper.observe(request, .76, .70); await nextTick(); resolve([{ ...row, sourceHash: "wrong" }]); await nextTick();
  assert.equal(errors.length, 1);
  assert.deepEqual(helper.judgments(request.key), []);
  helper.reset();
});
