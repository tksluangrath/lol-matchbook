# Phase 3: Data Dragon Markup Stripping Fix

**Status: DONE.**

## The bug

Real data-quality bug found during a precompute run: `champion_text()` in
`backend/app/retrieval/index.py` flattens a Data Dragon champion entry
into embedding/prompt text but never stripped Data Dragon's own
HTML-like markup out of the passive/spell description and tooltip
fields. Confirmed leak in a real generated Kayn/Warwick matchup:

```
<font color='#8484fb'>Shadow Assassin</font>
```

verbatim in the model's context, sourced from the real Data Dragon
champion detail endpoint (`DDRAGON_DETAIL_URL`, patch `16.15.1`) via
`app.finetune.qualitative_advice.fetch_champion_detail()`.

## Real markup inventory

Fetched real Data Dragon detail JSON for `Kayn`, `Warwick`, `Ahri`,
`Yasuo`, and `Vel'Koz` (patch `16.15.1`) and scanned `blurb`,
`passive.description`, and every `spells[].description` /
`spells[].tooltip` for `<[^>]+>` matches. No assumptions going in beyond
"probably more than `<font>`" -- here's exactly what was actually
present:

```
<br>, <br />
<font color='#6655CC'>, <font color='#8484fb'>, <font color='#99FF99'>, <font color='#fe5c50'>
</font>
<status>, </status>
<scaleArmor>, </scaleArmor>
<scaleMana>, </scaleMana>
<healing>, </healing>
<hold>, </hold>
<keywordMajor>, </keywordMajor>
<keywordName>, </keywordName>
<magicDamage>, </magicDamage>
<physicalDamage>, </physicalDamage>
<trueDamage>, </trueDamage>
<recast>, </recast>
<speed>, </speed>
<spellActive>, </spellActive>
<spellName>, </spellName>
<spellPassive>, </spellPassive>
<tap>, </tap>
<factionIonia1>, </factionIonia1>
```

No HTML entities (`&nbsp;` etc.) showed up in this real 5-champion
sample, but the fix handles them anyway (`html.unescape`) since the
vocabulary clearly isn't a fixed, guessable set (`<factionIonia1>` is
not a tag anyone would have predicted).

Kayn's real passive description, confirming the exact reported leak:

```
"Either the <font color='#fe5c50'>Darkin</font> will triumph, or Kayn
will master Rhaast and become the <font color='#8484fb'>Shadow
Assassin</font>. ... <br><br><font color='#fe5c50'>Darkin:</font> Heal
for a percentage of spell damage dealt to champions.<br><br><font
color='#8484fb'>Shadow Assassin:</font> For the first few seconds in
combat with enemy champions, deal bonus damage."
```

## The fix

Generic tag-stripping in the one shared function every caller routes
through (`backend/app/retrieval/index.py::champion_text()`), not a
`<font>`-specific patch:

```python
_TAG_RE = re.compile(r"<[^>]+>")

def _strip_markup(text: str) -> str:
    return html.unescape(_TAG_RE.sub("", text))
```

applied to every text part (name/blurb/passive/spell text) before
joining. Callers of `champion_text()` --
`app.finetune.qualitative_advice.build_generation_prompt()` and
`app.data_pipeline.precompute.py` (both import it directly, per
`grep -rn champion_text`) -- get the fix automatically since they all
route through this one function.

## Confirmation: Kayn's case resolved

```python
>>> champion_text(kayn_detail)
```
now contains `Shadow Assassin` with no surrounding `<font ...>`/`</font>`
tags. Verified in
`backend/tests/unit/test_champion_text_markup_stripping.py::test_kayn_passive_font_tags_stripped`,
which asserts against the raw fetched JSON's real tag (not a synthetic
fixture) and confirms it is gone from the flattened text while the real
substring it wrapped survives.

## No regression

`backend/tests/integration/test_retrieval_index.py` (real semantic
nearest-neighbor checks against Ashe/Garen/Lux/Zed/Jinx/Leona) run
**unmodified** alongside the new unit test:

```
tests/unit/test_champion_text_markup_stripping.py::test_kayn_passive_font_tags_stripped PASSED
tests/unit/test_champion_text_markup_stripping.py::test_no_html_like_tags_survive_for_any_fetched_champion[Kayn] PASSED
tests/unit/test_champion_text_markup_stripping.py::test_no_html_like_tags_survive_for_any_fetched_champion[Warwick] PASSED
tests/unit/test_champion_text_markup_stripping.py::test_no_html_like_tags_survive_for_any_fetched_champion[Ahri] PASSED
tests/unit/test_champion_text_markup_stripping.py::test_no_html_like_tags_survive_for_any_fetched_champion[Yasuo] PASSED
tests/unit/test_champion_text_markup_stripping.py::test_no_html_like_tags_survive_for_any_fetched_champion[Velkoz] PASSED
tests/unit/test_champion_text_markup_stripping.py::test_real_markup_vocabulary_found_this_session_is_all_stripped PASSED
tests/integration/test_retrieval_index.py::test_champion_text_includes_real_ability_text PASSED
tests/integration/test_retrieval_index.py::test_nearest_neighbor_is_the_correct_champion PASSED
tests/integration/test_retrieval_index.py::test_unrelated_query_does_not_match_ashe PASSED

10 passed in 7.97s
```
