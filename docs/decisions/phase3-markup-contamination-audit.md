# Phase 3: Markup Contamination Audit — the 82 Real Written Rows

**Status: DONE.** Checked every row from the real top-109 eager-tier batch
(`docs/decisions/phase3-eager-tier-precompute.md`) that actually made it
into the live `advice` table. Result: **4 contaminated rows, across 2
distinct pairs**, out of 246 rows checked.

## Scope: how the 82 pairs were identified for real, not assumed

The live `advice` table currently holds 96 distinct (champ_a, champ_b,
role) pairs (288 rows, 3 phases each), not just the 82 from the batch this
audit is about — it also has the original 10-pair slice
(`qualitative_advice_heldout.jsonl`, per `phase3-precompute-and-advice-
endpoint.md`) and 4 synthetic test-fixture pairs (`MultiRole/Opponent`,
`ThinData/Opponent`, `WiderRankChamp/Opponent` — obviously not real
champions, left over from the integration test suite writing to the same
persistent DB).

To isolate the real 82 without trusting an assumption, `rank_real_
candidate_pairs()` (unmodified, deterministic against the same cached HF
match CSV the original run used) was re-run to reproduce the exact top-109
candidate ranking, then intersected against the live table's distinct
pairs:

```
db distinct pairs: 96
db pairs in top109 (should be 82): 82   <- matches the doc's written=82 exactly
db pairs in orig10: 10
unaccounted db pairs: 4                 <- the synthetic test fixtures above
```

82 exactly, confirming the intersection correctly isolates this run's real
written pairs. 82 pairs x 3 phases (early/mid/late, one generation call per
pair per `phase3-eager-tier-precompute.md`) = **246 rows checked**, not 82
rows — "82 written" in the source doc counts pairs, not rows, per `run_
precompute_batch`'s own counter.

## Method

General HTML-tag-like scan, not just `<font>`:
```python
tag_re = re.compile(r"<[^>]+>|&[a-zA-Z]+;")
```
Run against every row's `text` field for the 246 rows in scope. Candidates
named in the task (`<br>`, `<li>`, `<status>`, `<scaleAP>`, `<scaleAD>`,
`<passive>`, `<spellPassive>`, `&nbsp;`) are all covered by this pattern;
none of them appeared except `<status>`.

## Real result: 4 contaminated rows, 2 pairs

```
rows_checked: 246
contaminated_count: 4
```

| champ_a | champ_b | role | phase | markup found |
|---|---|---|---|---|
| Caitlyn | Samira | bottom | mid | `<status>Dash</status>`, `<status>Blade Whirl</status>` |
| Caitlyn | Samira | bottom | late | `<status>Blade Whirl</status>` |
| Briar | Viego | jungle | mid | `<font color='#FFF673'>Heartbreaker</font>`, `<font color='#FF5555'>Head Rush</font>`, `<font color='#FF5555'>Blood Frenzy</font>` |
| Briar | Viego | jungle | late | `<font color='#FFF673'>Sovereign's Domination</font>`, `<font color='#FF5555'>Blood Fren` (text truncated at column limit, tag itself intact) |

Real snippets, verbatim from the live rows:

```
Caitlyn/Samira, mid: "...Avoid letting Samira gain a combo—her reliance on
<status>Dash</status> and <status>Blade Whirl</status> makes her
predictable in fights..."

Caitlyn/Samira, late: "...be ready to counter with a well-timed
<status>Blade Whirl</status> or use your headshot to pick her off."

Briar/Viego, mid: "...Viego's <font color='#FFF673'>Heartbreaker</font> can
turn the tide if Briar is caught in a net of fear. Instead, Briar should
focus on disrupting Viego's positioning with <font color='#FF5555'>Head
Rush</font> and <font color='#FF5555'>Blood Frenzy</font>..."

Briar/Viego, late: "...Viego's <font color='#FFF673'>Sovereign's
Domination</font> allows him to adapt to Briar's presence...use <font
color='#FF5555'>Blood Fren[text cut off at DB column limit]"
```

The `early`-phase rows for both pairs are clean (checked directly, no tag
match) — contamination isn't uniform across a pair's three phases, matching
the pattern already seen in the Kayn/Warwick skipped-pair case (font tags
appear only where the model happened to quote a specific ability name in
that phase's text).

This is the same root cause already identified in `phase3-eager-tier-
precompute.md`'s incidental finding on Kayn/Warwick: `champion_text()` in
`backend/app/retrieval/index.py` doesn't strip Data Dragon's embedded
markup (`<font color=...>`, `<status>`, etc.) from ability descriptions
before the text reaches the model, so the model occasionally echoes it
back verbatim when quoting an ability name. Confirms the Kayn/Warwick leak
was not an isolated case limited to a never-persisted pair — it reached
live, already-served rows too, at a real (if low) rate: 2 of 82 pairs
(2.4%), 4 of 246 rows (1.6%).

## The other 242 rows: clean

All remaining 78 pairs (234 rows) had zero regex matches — no `<font>`,
`<status>`, `<br>`, `<li>`, `<scaleAP>`, `<scaleAD>`, `<passive>`,
`<spellPassive>`, or `&nbsp;`/HTML-entity contamination found.

## Not done here

This is a read-only audit — no rows were modified, no fix applied. Fixing
`champion_text()` to strip Data Dragon markup before it reaches the model
(already flagged as a known gap in `phase3-eager-tier-precompute.md`'s
"Next step") and deciding whether to regenerate the 2 affected pairs are
both left for a separate task.

## Files

- `docs/decisions/phase3-markup-contamination-audit.md` (this file)
- No code or DB changes.
