# Upstream sync

This repository preserves the history of `shaneconner/fold`. The imported baseline is pi-fold 4.3.0, commit `1f739edab42f3ba34ec22c4fcf24c8b0a4ad9664`. The `upstream/pi-fold-4.3.0` branch records that revision. The repository's existing issues remain in place.

Prepare an upstream update on a separate branch:

```sh
git remote add upstream https://github.com/shaneconner/fold.git # once
git fetch upstream
git switch -c sync/pi-fold-<version> main
git merge --no-ff <reviewed-upstream-commit>
npm ci
npm run test:plus
npm test
npm run lint
```

Open a PR for that sync. Resolve the Plus integration points in `active-context.ts`, `folding.ts`, `scheduling.ts` and the status UI; keep the added modules separate from upstream's physical chunk selection. Preserve imported history rather than copying a fresh source snapshot over the fork.

Runtime entry types and `pi_fold_context` retain upstream identities so existing session evidence stays readable. Run either pi-fold or Pi Folds Plus, not both copies in the same Pi process. Package naming distinguishes installation without renaming stored evidence.

The bootstrap workflow imports the baseline only when the repository has no runtime code. Once imported, it makes no changes.
