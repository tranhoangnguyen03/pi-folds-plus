from pathlib import Path


def edit(path, old, new):
    p = Path(path)
    text = p.read_text()
    if new in text:
        return
    if text.count(old) != 1:
        raise RuntimeError(f'Expected one source anchor in {path}: {old[:80]}')
    p.write_text(text.replace(old, new, 1))


active = 'extensions/active-context.ts'
edit(active, '  toolClipAdditions,\n', '')
edit(active, '      judgments: retention.judgments(assessmentKey(snapshot, lifecycle.generation), userRequested),', '      judgments: retention.judgments(assessmentKey(snapshot, lifecycle.generation), userRequested),\n      preserveHolds: userRequested,')
edit(active, '      retention_kept: selection.held.map((item) => item.id),', '      retention_kept: selection.held.map((item) => item.id).join(","),')
edit(active, '    let candidate = before;', '    let candidate = clone(before);')
edit(active, '      admit({ action: "expand", ctx, foldId: id, requestedBytes: additional, children: [] });', '      if (additional > 0) admit({ action: "expand", ctx, foldId: id, requestedBytes: additional, children: [] });')
edit(active, '      admit({ action: "expand", ctx, foldId: ids.join(", "), requestedBytes: additional, children: [] });', '      if (additional > 0) admit({ action: "expand", ctx, foldId: ids.join(", "), requestedBytes: additional, children: [] });')
edit(active, '    await persistManual(nextProtection, ctx);\n    if (pin)', '    await persistManual(nextProtection, ctx);\n    if (!pin) retention.invalidate();\n    if (pin)')
edit(active, '            presentation: foldPresentation(fold, state, snapshot),', '              presentation: foldPresentation(fold, state, snapshot),')

p = 'extensions/lib/retention.ts'
edit(p, 'import { messageRole }', 'import { clone, messageRole }')
edit(p, 'const guarded = { ...state, protected: [...protectedRefs.values()] };', 'const guarded = { ...clone(state), protected: [...protectedRefs.values()] };')
edit(p, '        onFailure?.(error);\n        this.service?.onError?.(error);', '        try { onFailure?.(error); } catch { /* UI failure must not reject the helper promise. */ }\n        try { this.service?.onError?.(error); } catch { /* The recorded error remains inspectable. */ }')
edit(p, '  status() {', '''  /** Explicit release cancels this approach's inference without starting another. */
  invalidate(): void {
    this.controller?.abort();
    this.controller = null;
    this.epoch += 1;
    this.ready = [];
    this.applied = [];
  }

  status() {''')
edit(p, '  judgments?: RetentionJudgment[];', '  judgments?: RetentionJudgment[];\n  preserveHolds?: boolean;')
edit(p, '  const baseline = await evaluate([]);', '  if (input.preserveHolds && keep.length) return { ...(await evaluate(keep)), held: keep.map((mark) => judgments.get(mark.id)!) };\n  const baseline = await evaluate([]);')
edit('extensions/lib/tool-surface.ts', ' Pin with ids restores the requested original source, including clipped output, and keeps it visible against automatic reduction. Restoration checks available context space. Unpin releases that protection while leaving the original text visible; a later commit may fold it. Status reports actual presentation separately from protection.', ' Pin with ids holds original source against automatic folding, consolidation, refolding and clipping. Folded or clipped sources are restored in the same admitted operation. unpin releases protection while leaving original text visible until a later reduction. Status reports actual presentation separately from protection.')

p = 'tests/verify.mjs'
edit(p, '  packageRegistration = false,\n', '  packageRegistration = false,\n  retention,\n')
edit(p, '    ...(noticeLeadShare === undefined ? {} : { noticeLeadShare }),', '    ...(noticeLeadShare === undefined ? {} : { noticeLeadShare }),\n    ...(retention === undefined ? {} : { retention }),')
edit(p, '  const expandRefusal = await toolCall(runtime, { action: "expand", id: big.id })', '''  // Expansion validates parent order before admission. Use a root to test capacity.
  const bigRoot = folds.find((fold) => fold.parentId === null && fold.sourceChars / bytesPerToken > headroom);
  assert(bigRoot, "The admission fixture needs an expandable root larger than headroom");
  const beforeRefusedExpand = json.stableStringify(materialized(runtime));
  const expandRefusal = await toolCall(runtime, { action: "expand", id: bigRoot.id })''')
edit(p, '  assert.match(expandRefusal, /expand of .* was refused/);', '  assert.match(expandRefusal, /expand of .* was refused/);\n  assert.equal(json.stableStringify(materialized(runtime)), beforeRefusedExpand,\n    "Refused expansion must not apply queued marks or change inclusion");')
edit(p, '  const snapHold = [...built.turnEntries[5]];\n  await toolCall(runtime, { action: "pin", ids: snapHold });', '  const snapHold = [...built.turnEntries[5]];\n  // Keep now restores its source, so provide room for that restoration.\n  await measure(runtime, 40_000, 100_000, "room-for-instrumented-keep");\n  await toolCall(runtime, { action: "pin", ids: snapHold });')
edit(p, '  await toolCall(runtime, { action: "pin", ids: [smallest.id] });', '  await measure(runtime, 40_000, 100_000, "room-for-under-cap-keep");\n  await toolCall(runtime, { action: "pin", ids: [smallest.id] });')
edit(p, '  assert.deepEqual(rebasedFolds.expanded, [rebasedParent.id], "expanded state was not re-keyed");', '''  // Plus materializes legacy protection-driven visibility into explicit inclusion.
  const protectedKeys = new Set(rebasedFolds.protected.map(json.objectRefKey));
  const expectedExpanded = new Set([rebasedParent.id]);
  for (const fold of rebasedFolds.folds) {
    if (context.flattenFoldRefs(fold, rebasedFolds).some((ref) => protectedKeys.has(json.objectRefKey(ref)))) expectedExpanded.add(fold.id);
  }
  assert.deepEqual([...rebasedFolds.expanded].sort(), [...expectedExpanded].sort(),
    "fork inclusion must preserve both expansion and legacy protected visibility");''')
edit(p, '  assert.deepEqual(durable().expanded, [], "the fixture began with a fold already expanded");', '''  assert.equal(durable().expanded.length, 1, "Release must leave the kept original visible");
  const releasedView = json.stableStringify((await project(folded)).messages);
  foldView.handleInput("e"); // Explicitly refold before exercising the independent restore action.
  while (foldView.staging) await new Promise((r) => setTimeout(r, 5));
  await settle();
  assert.deepEqual(durable().expanded, []);
  assert.notEqual(json.stableStringify((await project(folded)).messages), releasedView);
''')
edit(p, '  assert(/raw in the model\'s window/.test(foldView.render(140).join("\\n")),', '  assert(/agent sees original/.test(foldView.render(140).join("\\n")),')
edit(p, '  [188, "One tool result cannot wedge the session", gateOneToolResultCannotWedgeTheSession],', '  [188, "One tool result cannot wedge the session", gateOneToolResultCannotWedgeTheSession],\n  [189, "Plus retention follows upstream timing without blocking", gatePlusRetentionRuntime],')
edit(p, 'const gateFilter =', '''async function gatePlusRetentionRuntime() {
  let enabled = true;
  const requests = [];
  const runtime = makeRuntime(makeFixture({ turns: 14, resultChars: 9000, contextWindow: 100_000 }), {
    packageRegistration: true,
    retention: {
      enabled: () => enabled,
      assess: async (request) => {
        requests.push(request);
        return request.candidates.map((candidate, index) => ({
          id: candidate.id, sourceHash: candidate.sourceHash,
          relevance: index === 0 ? "keep-original" : "ordinary", reason: "Fixture evidence",
        }));
      },
    },
  });
  await startRuntime(runtime);
  await measure(runtime, 60_000, 100_000, "below-approach");
  await project(runtime); await settle();
  assert.equal(requests.length, 0);
  // Descriptor capacity reserves 10%, so 70% of its serving budget is 63,000.
  await measure(runtime, 64_000, 100_000, "approaching");
  await project(runtime); await settle();
  assert.equal(requests.length, 1);
  await project(runtime); await settle();
  assert.equal(requests.length, 1, "unchanged approach must not repeat inference");
  assert(requests[0].candidates.length > 0);
  assert(requests[0].candidates.every((candidate) => candidate.sourceHash && candidate.sourceIds.length));
  await measure(runtime, 73_000, 100_000, "ordinary-commit");
  await project(runtime); await settle();
  assert(contextEvents(runtime).some((event) => event.kind === "context.commit" && !event.deferred),
    "Retention must not block upstream's ordinary commit");
  assert(!contextEvents(runtime).some((event) => event.kind === "context.suspend"));
  const beforeOff = requests.length;
  enabled = false;
  await measure(runtime, 75_000, 100_000, "disabled");
  await project(runtime); await settle();
  assert.equal(requests.length, beforeOff, "disabled service must not issue calls");

  let finish;
  const slow = makeRuntime(makeFixture({ turns: 14, resultChars: 9000, contextWindow: 100_000 }), {
    retention: { assess: () => new Promise((resolve) => { finish = resolve; }) },
  });
  await startRuntime(slow);
  await measure(slow, 73_000, 100_000, "jump-over-approach");
  await project(slow); await settle();
  const committed = materialized(slow);
  assert(committed.folds.length > 0, "An unfinished helper must not prevent folding");
  finish?.([]); await settle();
  assert.deepEqual(materialized(slow).expanded, committed.expanded,
    "A late response must not restore committed source");
  return { oncePerApproach: true, disabledNoCalls: true, slowHelperNonblocking: true, exactSourceBinding: true };
}

const gateFilter =''')

p = 'tests/plus-foundation.mjs'
edit(p, '  const planned = await select(snapshot, state, { applyTargetBytes, judgments: [judgment] });', '  const originalState = JSON.stringify(state);\n  const planned = await select(snapshot, state, { applyTargetBytes, judgments: [judgment] });\n  assert.equal(JSON.stringify(state), originalState, "trial plans must not mutate the live queue");')
edit(p, '  const emergency = await select(snapshot, state, { judgments });', '  const manual = await select(snapshot, state, { judgments, preserveHolds: true });\n  assert.equal(manual.held.length, 2, "manual commits preserve current automatic holds");\n  const emergency = await select(snapshot, state, { judgments });')
edit('docs/plus-foundation.md', 'Run only one folding extension', '''## Verification scope

The inherited runtime suite and the focused Plus suite test this fork. The old
experiment harness also binds published measurements to an exact historical runtime
hash; those measurements remain upstream evidence, not results for Plus. CI checks
that their archived report files still match the audited upstream commit. New Plus
cost/recall claims require new runs once the provider adapters are ready.

Run only one folding extension''')
edit('README.md', '\n---\n\n## Upstream reference:', '\nThe inherited benchmark tables below describe upstream pi-fold, not measurements of Plus.\n\n---\n\n## Upstream reference:')
