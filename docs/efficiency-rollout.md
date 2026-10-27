# Efficiency gates: turning them on and scheduling the nightly report

The gates (size, frame hazards, duplication, perf smoke) are opt-in per caller and ratchet: a baseline under `ci/efficiency/` or `ci/perf/smoke.json` is committed first, then the caller sets `efficiency: true` (and `perf: true`). Callers pin `@v1`, which does not have those inputs until the tag moves, so the flags stay off until then.

## Steps, in order (a human does the tag and the pushes)

1. In dot-ci, confirm `scripts/check.sh` and the tests pass, then push `main`.
2. Move the tag: `git tag -f v1 && git push -f origin v1` (the tag is the interface callers pin).
3. In each caller that has committed baselines, add `efficiency: true` (and `perf: true` for a game with `ci/perf/smoke.json`) under `with:` in `.github/workflows/ci.yml`, then push.
4. Watch the first run per caller. A failure on the first run means the baseline is stale: re-run the gate with `--update` locally (it only ever lowers entries), never edit the `.tsv` by hand.

Baselines are made once with `scripts/check-size.py --init`, `scripts/check-frame-hazards.py --init`, `scripts/check-duplication.py --init` and `scripts/perf-smoke.sh --init <project>`, each refusing to overwrite.

## Nightly report

`scripts/efficiency-nightly.sh` prints the table and the trend, and exits non-zero when anything grew. A crontab line (documented, not installed), run on the box that holds the checkouts:

```
30 3 * * * cd $HOME/godot && EFFICIENCY_PANEL_FILE=$HOME/.efficiency-panel.txt heavy -- timeout 1500 dot-ci/scripts/efficiency-nightly.sh >> $HOME/.efficiency-nightly.log 2>&1
```

The panel text lands in `EFFICIENCY_PANEL_FILE`; whatever posts to the nightly panel reads it from there.
