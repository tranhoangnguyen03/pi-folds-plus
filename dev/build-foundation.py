from pathlib import Path
import json

def replace(path, before, after):
    p = Path(path)
    text = p.read_text()
    if before not in text:
        if after in text:
            return
        raise RuntimeError(f'Patch anchor missing: {path}: {before[:100]!r}')
    if text.count(before) != 1:
        raise RuntimeError(f'Ambiguous patch: {path}: {before[:100]!r}')
    p.write_text(text.replace(before, after, 1))

def section(path, start, end, content):
    p = Path(path)
    text = p.read_text()
    a, b = text.index(start), text.index(end, text.index(start) + len(start))
    p.write_text(text[:a] + content + '\n\n' + text[b:])

folding = 'extensions/lib/folding.ts'
replace(folding, '  refsProtected,\n} from "./measurement.ts";', '  refsProtected,\n  refsStructurallyProtected,\n} from "./measurement.ts";')
replace(folding, 'import { staleSpanMatureEnd } from "./transcript.ts";', 'import { staleSpanMatureEnd } from "./transcript.ts";\nimport { preserveProtectedInclusion, restoreProtectedSources } from "./visibility.ts";')
replace(folding, '  const mustReveal = state.expanded.includes(fold.id) || (refsProtected(refs, state, snapshot));', '  const mustReveal = state.expanded.includes(fold.id) || refsStructurallyProtected(refs, snapshot);')
replace(folding, '    const protectedSource = refsProtected(refs, state, snapshot);\n    if (!state.expanded.includes(fold.id) && !protectedSource)', '    const protectedSource = refsStructurallyProtected(refs, snapshot);\n    if (!state.expanded.includes(fold.id) && !protectedSource)')
replace(folding, '  } else {\n    expanded.delete(id);\n    for (const descendant of descendantIds(state, id)) expanded.delete(descendant);', '  } else {\n    const protectedKeys = new Set(state.protected.map(objectRefKey));\n    if (flattenFoldRefs(fold, state).some((ref) => protectedKeys.has(objectRefKey(ref)))) {\n      throw new Error(`Release the keep on ${id} before refolding it`);\n    }\n    expanded.delete(id);\n    for (const descendant of descendantIds(state, id)) expanded.delete(descendant);')
replace(folding, '  const refs = ids.flatMap((id) => {\n    const fold = state.folds.find((item) => item.id === id);', '  // Preserve legacy inclusion before changing protection.\n  state = preserveProtectedInclusion(state);\n  const refs = ids.flatMap((id) => {\n    const fold = state.folds.find((item) => item.id === id);')
replace(folding, '    ...state,\n    revision: state.revision + 1,\n    protected: [...byKey.values()],', '    ...(protect ? restoreProtectedSources(snapshot, state, ids) : state),\n    revision: state.revision + 1,\n    protected: [...byKey.values()],')
measurement = 'extensions/lib/measurement.ts'
replace(measurement, 'export function refsProtected(\n', '''export function refsStructurallyProtected(
  refs: EvidenceRef[],
  snapshot: ActiveContextSnapshot,
): boolean {
  return refs.some((ref) => {
    const item = exactMapped(snapshot, ref);
    return !item || snapshot.protectedIndices.has(item.index);
  });
}

export function refsProtected(
''')
presentation = '''export type FoldPresentation = "original" | "clipped" | "folded" | "mixed";

export function foldPresentation(
  fold: ActiveFold,
  state: ActiveContextState,
  snapshot: ActiveContextSnapshot,
): FoldPresentation {
  const byId = foldMap(state);
  const revealed = (item: ActiveFold) => state.expanded.includes(item.id) ||
    refsStructurallyProtected(flattenFoldRefs(item, state), snapshot);
  for (let id = fold.parentId; id;) {
    const parent = byId.get(id);
    if (!parent || !revealed(parent)) return "folded";
    id = parent.parentId;
  }
  const clips = new Set((state.clips ?? []).map((clip) => clip.entryId));
  const states = new Set<FoldPresentation>();
  const visit = (item: ActiveFold): void => {
    if (!revealed(item)) { states.add("folded"); return; }
    for (const part of item.parts) {
      if (part.kind === "fold") {
        const child = byId.get(part.foldId);
        if (child) visit(child);
      } else {
        const message = exactMapped(snapshot, part.ref)?.message;
        const clipped = clips.has(part.ref.entryId) && messageRole(message) === "toolResult" &&
          typeof ownValue(ownValue(message, "details"), "projection") !== "string" &&
          contentText(message).length > snapshot.policy.toolClipFloorChars;
        states.add(clipped ? "clipped" : "original");
      }
    }
  };
  visit(fold);
  return states.size === 1 ? [...states][0] : "mixed";
}

'''
replace(folding, 'export function foldStatusRow(', presentation + 'export function foldStatusRow(')
replace(folding, '    state: projection,\n    active: Boolean(interval),', '    state: projection,\n    presentation: foldPresentation(fold, state, snapshot),\n    active: Boolean(interval),')
replace(folding, '    state: state.expanded.includes(fold.id) ? "expanded" : "folded",\n    peekable: true,', '    state: state.expanded.includes(fold.id) ? "expanded" : "folded",\n    presentation: foldPresentation(fold, state, snapshot),\n    peekable: true,')
replace(folding, '    state: state.expanded.includes(fold.id) ? "expanded" : "folded",\n    startId:', '    state: state.expanded.includes(fold.id) ? "expanded" : "folded",\n    presentation: foldPresentation(fold, state, snapshot),\n    startId:')
scheduling = 'extensions/lib/scheduling.ts'
replace(scheduling, '  applyTargetBytes?: number;\n}): Promise<CommitEpochResult>', '  applyTargetBytes?: number;\n  /** Optional relevance order; equal priorities retain native source order. */\n  priority?: (mark: PendingMark) => number;\n}): Promise<CommitEpochResult>')
replace(scheduling, '  const base = [...marks].sort((left, right) =>\n    applyStart.get(pendingMarkKey(left))!', '  const base = [...marks].sort((left, right) =>\n    (input.priority ? input.priority(left) - input.priority(right) : 0) ||\n    applyStart.get(pendingMarkKey(left))!')
replace(scheduling, '    return state.expanded.includes(mark.id) ? "eligible" : "unfulfillable";', '    if (fold && (refsProtected(flattenFoldRefs(fold, state), state, snapshot) || state.leases[mark.id])) return "protected";\n    return state.expanded.includes(mark.id) ? "eligible" : "unfulfillable";')
active = 'extensions/active-context.ts'
replace(active, '  foldIndexRow,\n', '  foldIndexRow,\n  foldPresentation,\n')
replace(active, 'import { buildActiveContextCommands, buildActiveContextTool }', 'import { preserveProtectedInclusion, restoreProtectedSources } from "./lib/visibility.ts";\nimport { RetentionAssessment, assessmentKey, retentionCandidates, selectCommit, type RetentionService } from "./lib/retention.ts";\nimport { buildActiveContextCommands, buildActiveContextTool }')
replace(active, '  thresholds?: ActiveContextThresholds;', '  /** Adapter seam; backend settings follow in a later milestone. */\n  retention?: RetentionService;\n  thresholds?: ActiveContextThresholds;')
replace(active, '  let preCommitNotice = resolvedPreCommitNotice(options.preCommitNotice);', '  const retention = new RetentionAssessment(options.retention);\n  let preCommitNotice = resolvedPreCommitNotice(options.preCommitNotice);')
replace(active, '    persistence.state = durableRestored.prepared ? clearPrepared(durableRestored) : clone(durableRestored);', '    persistence.state = preserveProtectedInclusion(durableRestored.prepared ? clearPrepared(durableRestored) : clone(durableRestored));')
replace(active, '  const load = (ctx: any, preserveThresholdDecision = false, forkedSessionHint = false): void => {\n    lifecycle.generation', '  const load = (ctx: any, preserveThresholdDecision = false, forkedSessionHint = false): void => {\n    retention.reset();\n    lifecycle.generation')
replace(active, '  const attributionChanged = async (_event: unknown, ctx: any): Promise<void> => {\n    lifecycle.generation', '  const attributionChanged = async (_event: unknown, ctx: any): Promise<void> => {\n    retention.reset();\n    lifecycle.generation')
replace(active, '      advanceFoldFrontier(snapshot);\n      if (curation.restoreRevisionGap', '''      advanceFoldFrontier(snapshot);
      if (retention.enabled()) {
        const capacity = servingCapacity(snapshot.contextWindow);
        retention.observe({
          key: assessmentKey(snapshot, lifecycle.generation),
          candidates: retentionCandidates(snapshot, persistence.state!),
          messages: snapshot.messages,
        }, capacity.usedTokens === null || capacity.budgetTokens <= 0 ? null : capacity.usedTokens / capacity.budgetTokens,
        Math.max(0, thresholds.maxTarget - noticeLeadShare), (error) => safeNotify(ctx,
          `Decision service failed; regular folding continues. ${String(error)}`, "error"));
      } else retention.reset();
      if (curation.restoreRevisionGap''')
start = '    let result = await commitPendingMarks({\n      snapshot,\n      state,\n      generation: lifecycle.generation,\n      retainIneligible: true,'
end = '    // A RE-CUT SPAN ADOPTS ITS DURABLE RECORD'
if start in Path(active).read_text():
    section(active, start, end, '''    const selection = await selectCommit({
      snapshot, state, generation: lifecycle.generation, ordinal,
      ...(backstopFired || waiverRatio !== null ? {} : {
        applyTargetBytes: Math.ceil(freeingTarget * budgetTokens * projectionCharsPerToken()),
      }),
      clipThreshold: toolFoldThreshold,
      blacklist: blacklistAutoFoldTools,
      judgments: retention.judgments(assessmentKey(snapshot, lifecycle.generation), userRequested),
    });
    let result = selection.result;
    closingAdded += selection.closingAdded;
    const clippedResults = selection.clippedResults;
    retention.committed(selection.held);''')
replace(active, '      closing_consolidation_marks: closingAdded,', '      closing_consolidation_marks: closingAdded,\n      retention_kept: selection.held.map((item) => item.id),')
section(active, '  const setFoldExpansion = async (', '  /**\n   * THE PIN CHANGE PATH', '''  const setFoldExpansion = async (
    snapshot: ActiveContextSnapshot,
    id: string,
    expand: boolean,
    ctx: any,
  ): Promise<unknown[]> => {
    const before = persistence.state!;
    let candidate = before;
    let epochApplied: unknown[] = [];
    if (expand && pendingMarks(candidate).length) {
      const result = await commitPendingMarks({ snapshot, state: candidate,
        generation: lifecycle.generation, retainIneligible: true });
      candidate = result.state;
      epochApplied = result.applied;
    }
    requireActiveFold(snapshot, candidate, id);
    let next = setFoldProjectionState(candidate, id, expand ? "expanded" : "folded");
    if (expand) {
      // Preserve one-level expansion while restoring clipped results in that source.
      const expanded = next.expanded;
      next = { ...restoreProtectedSources(snapshot, next, [id]), expanded };
      next = withExpandLease(next, id);
      const additional = Math.max(0,
        pricedBytes(projectActiveContext(snapshot, next)) - pricedBytes(projectActiveContext(snapshot, before)));
      admit({ action: "expand", ctx, foldId: id, requestedBytes: additional, children: [] });
    } else {
      const leases = { ...next.leases };
      delete leases[id];
      next = { ...next, leases };
    }
    // Failed admission leaves queued marks and the current projection unchanged.
    await persistManual(next, ctx);
    updateStatus(ctx);
    return epochApplied;
  };''')
replace(active, '    await persistManual(nextProtection, ctx);\n    emit("context.pin", {', '''    if (pin) {
      const additional = Math.max(0, pricedBytes(projectActiveContext(snapshot, nextProtection)) -
        pricedBytes(projectActiveContext(snapshot, persistence.state!)));
      admit({ action: "expand", ctx, foldId: ids.join(", "), requestedBytes: additional, children: [] });
    }
    await persistManual(nextProtection, ctx);
    if (pin) {
      // A kept peek becomes an ordinary recoverable result.
      const held = new Set(nextProtection.protected.map(objectRefKey));
      for (const item of snapshot.mapped) {
        if (!item.ref || !held.has(objectRefKey(item.ref))) continue;
        const callId = ownValue(item.message, "toolCallId");
        if (typeof callId === "string") ephemeralPeeks.delete(callId);
      }
    }
    emit("context.pin", {''')
replace(active, '            expandedInContext: state.expanded.includes(fold.id),', '            expandedInContext: state.expanded.includes(fold.id),\n            presentation: foldPresentation(fold, state, snapshot),')
editor = 'extensions/lib/editor-ui.ts'
replace(editor, '\texpandedInContext?: boolean;', '\texpandedInContext?: boolean;\n\tpresentation?: "original" | "clipped" | "folded" | "mixed";')
replace(editor, '\t\t\tprovenance?: string; expandedInContext?: boolean;', '\t\t\tprovenance?: string; expandedInContext?: boolean;\n\t\t\tpresentation?: "original" | "clipped" | "folded" | "mixed";')
replace(editor, '\t\t\texpandedInContext: row.expandedInContext,', '\t\t\texpandedInContext: row.expandedInContext,\n\t\t\tpresentation: row.presentation,')
replace(editor, '\t\tconst contextBadge = block.expandedInContext\n\t\t\t? ` ${this.color("warning", "· raw in the model\'s window")}`\n\t\t\t: "";', '\t\tconst presentation = block.presentation ?? (block.expandedInContext ? "original" : "folded");\n\t\tconst contextBadge = ` ${this.color("warning", `· agent sees ${presentation}`)}`;')
surface = 'extensions/lib/tool-surface.ts'
replace(surface, ' Pin with ids holds folds or entries against automatic folding, consolidation and refolding until unpin releases them, so an expanded span you still need stays expanded. Pin reveals nothing on its own: a folded span stays folded, just held. Pinning moves no context bytes, and fold receipts report how much mass you have pinned.', ' Pin with ids restores the requested original source, including clipped output, and keeps it visible against automatic reduction. Restoration checks available context space. Unpin releases that protection while leaving the original text visible; a later commit may fold it. Status reports actual presentation separately from protection.')
replace('extensions/index.js', '  "preCommitNotice", "noticeLeadShare", "palette",', '  "preCommitNotice", "noticeLeadShare", "palette", "retention",')
p = Path('package.json')
data = json.loads(p.read_text())
data.update(name='pi-folds-plus', version='0.1.0-alpha.0', description='Pi context folding with explicit visibility controls and a near-commit retention planner.')
data['repository']['url'] = 'git+https://github.com/tranhoangnguyen03/pi-folds-plus.git'
data['bugs'] = 'https://github.com/tranhoangnguyen03/pi-folds-plus/issues'
data['homepage'] = 'https://github.com/tranhoangnguyen03/pi-folds-plus#readme'
data['scripts']['test:plus'] = 'node --test tests/plus-foundation.mjs'
p.write_text(json.dumps(data, indent=2)+'\n')
p = Path('package-lock.json')
data = json.loads(p.read_text())
data['name'] = data['packages']['']['name'] = 'pi-folds-plus'
data['version'] = data['packages']['']['version'] = '0.1.0-alpha.0'
p.write_text(json.dumps(data, indent=2)+'\n')
p = Path('README.md')
original = p.read_text()
if not original.startswith('# Pi Folds Plus'):
    intro = Path('docs/plus-foundation.md').read_text().replace('(UPSTREAM.md)', '(docs/UPSTREAM.md)')
    p.write_text(intro+'\n---\n\n## Upstream reference: pi-fold 4.3.0\n\n'+original)
