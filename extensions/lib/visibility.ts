import { objectRefKey } from "../json.ts";
import { clearPrepared, flattenFoldRefs } from "./persistence.ts";
import { exactMapped } from "./measurement.ts";
import type { ActiveContextSnapshot, ActiveContextState } from "./policy.ts";

/** Preserve what the old renderer exposed through explicit protection on resume. */
export function preserveProtectedInclusion(state: ActiveContextState): ActiveContextState {
  const keys = new Set(state.protected.map(objectRefKey));
  if (!keys.size) return state;
  const expanded = new Set(state.expanded);
  for (const fold of state.folds) {
    if (flattenFoldRefs(fold, state).some((ref) => keys.has(objectRefKey(ref)))) expanded.add(fold.id);
  }
  if (expanded.size === state.expanded.length) return state;
  return clearPrepared({ ...state, revision: state.revision + 1, expanded: [...expanded] });
}

/** Restore the requested source closure, including enclosing folds and old clips. */
export function restoreProtectedSources(
  snapshot: ActiveContextSnapshot,
  state: ActiveContextState,
  ids: string[],
): ActiveContextState {
  const keys = new Set<string>();
  for (const id of ids) {
    const fold = state.folds.find((item) => item.id === id);
    const refs = fold ? flattenFoldRefs(fold, state)
      : snapshot.mapped.flatMap((item) => item.ref?.entryId === id ? [item.ref] : []);
    if (!refs.length || refs.some((ref) => !exactMapped(snapshot, ref))) {
      throw new Error(`Source ${id} is not present in this context`);
    }
    for (const ref of refs) keys.add(objectRefKey(ref));
  }
  const expanded = new Set(state.expanded);
  for (const fold of state.folds) {
    if (flattenFoldRefs(fold, state).some((ref) => keys.has(objectRefKey(ref)))) expanded.add(fold.id);
  }
  const entryIds = new Set(snapshot.mapped.flatMap((item) =>
    item.ref && keys.has(objectRefKey(item.ref)) ? [item.ref.entryId] : []));
  const clips = (state.clips ?? []).filter((clip) => !entryIds.has(clip.entryId));
  const next = { ...state, expanded: [...expanded] };
  if (clips.length) next.clips = clips;
  else delete next.clips;
  return next;
}
