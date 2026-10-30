# Pi Folds Plus

A history-preserving fork of [pi-fold](https://github.com/shaneconner/fold), developed from the [approved blueprint](https://github.com/tranhoangnguyen03/pi-folds-plus/issues/1).

## Runtime foundation

This PR implements the first runtime layer:

- **Keep** restores original source, including clipped output, and protects it. Context admission prices the complete restoration.
- **Release** removes protection while leaving the source visible for later automatic folding.
- Fold records expose **original / clipped / folded / mixed** presentation separately from expansion and protection flags.
- A nonblocking near-commit assessment runs once per approach, rejecting stale or late results. No helper runs with the service disabled.
- The planner uses the existing post-fold target, source validity, native leases, consolidation and tool clipping. Relevance changes selection without a task tracker or another commit clock.

The foundation provides an internal `retention` adapter seam on `registerPiFold`. Production backend adapters, the `/folds` home/settings redesign, semantic topic cards and global usage exports are subsequent blueprint milestones. They are not part of this foundation and are not needed to exercise its visibility fixes.

## Compatibility

Existing fold evidence and upstream tool/command names remain. The visibility repair is intentional: unlike upstream's implicit protection rendering, Release no longer hides source text immediately. Existing explicit keeps are materialized into inclusion on resume. Existing clipped content remains reported as clipped until restored.

Automatic retention is a per-commit choice, separate from explicit persisted keeps. The initial adapter controller is session-local; restart uses base selection until the next near-commit assessment. Existing original text is not erased on restart.

No spending, token or call-count quotas are added. Upstream's context-size, source-validity and explicit-pin constraints remain in force.

## Development

```sh
npm ci
npm run test:plus
npm test
npm run lint
```

Focused tests import real runtime modules and exercise keep/release, clipping, nested presentation, legacy state, queued refolds, unchanged base selection, target-sized retention, stale results and disabled services. See [upstream sync](UPSTREAM.md) for maintaining the fork.

## Verification scope

The inherited runtime suite and the focused Plus suite test this fork. The old
experiment harness also binds published measurements to an exact historical runtime
hash; those measurements remain upstream evidence, not results for Plus. CI checks
that their archived report files still match the audited upstream commit. New Plus
cost/recall claims require new runs once the provider adapters are ready.

Run only one folding extension in a Pi session. No npm publication is part of this PR.
