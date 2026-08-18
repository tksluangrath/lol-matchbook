noteId: "frontend-readme-phase5"
tags: []

---

# frontend

React + Vite chat UI for the champ-select and follow-up paths (see `docs/build-plan.md` Phase 5, `docs/system-design.md`).

## What's scaffolded

- `src/api/advice.ts` — real client for `GET /advice` (backend/app/routers/advice.py). `classifyAdviceResponse()` is a pure function that turns the real 5-shape response contract (confirmed by reading advice.py + its integration tests, not assumed) into a discriminated `AdviceResult` union: `hit`, `wider_rank_fallback`, `abstention`, `archetype_fallback`, `not_precomputed`.
- `src/components/AdviceMessage.tsx` — renders each `AdviceResult` state with its mapped accent color and explicit copy.
- `src/components/MessageList.tsx`, `src/components/InputBox.tsx`, `src/App.tsx` — the chat shell: message list (`role="log"`, `aria-live="polite"`), streaming assistant text, and a keyboard-submittable input box.
- `src/theme.ts` / `src/theme.css` — the fixed color tokens and the state-to-color mapping.
- `src/contrast.ts` — real WCAG relative-luminance/contrast-ratio math, used by `src/contrast.test.ts` to verify (not assume) the grey states pass AA.

## Palette / state-to-color mapping

Dark mode only, non-negotiable per the design brief:

| Token | Hex | Used for |
|---|---|---|
| `--color-bg` | `#0A0E16` | page background |
| `--color-surface` | `#10161F` | card/message surfaces |
| `--color-border` | `#1C2530` | borders/dividers |
| `--color-teal` | `#0AC8B9` | primary input action + **precomputed-hit** advice state |
| `--color-gold` | `#C8AA6E` | **wider-rank-fallback** advice state only |
| `--color-grey-strong` | `#5A6472` | chrome only (borders/icons) for low-confidence states — 3.22:1 against the navy background, passes AA's large-text/UI floor but **not** normal-text AA, so it is never used for body copy |
| `--color-grey-text` | `#8A95A3` | body copy for low-confidence states — 6.35:1 against the navy background, passes WCAG AA normal-text contrast (verified in `src/contrast.test.ts`) |

The real `GET /advice` endpoint has **five** distinct response shapes, one more than the four named in the original design brief (precomputed hit / wider-rank fallback / abstention / not-precomputed). The fifth, `archetype_fallback` (a 200 with real Data Dragon champion blurbs, returned when nothing's precomputed for a pair at any rank but the champions themselves are real), has no color of its own in the brief. It's grouped into the same grey tier as `abstention` and `not_precomputed` (all three are low-confidence, non-matchup-specific outcomes) but keeps its own distinct copy ("general champion info only") so it's never confused with the other two by text alone.

## Mocked interfaces (swap points)

Two things are unbuilt on the backend and mocked here behind small, named interfaces so replacing them later touches one file:

- **`POST /ask`** (the streamed follow-up path) — mocked in `src/api/ask.mock.ts` behind the `AskClient` interface (`ask(req): AsyncGenerator<string>`), yielding words incrementally to mimic real chunked streaming. Swap: write `src/api/ask.ts` exporting a real `AskClient` that reads a real streamed HTTP response, then change the one import in `src/App.tsx`.
- **LCU auto-detection** (League client champ-select push) — mocked in `src/api/lcu.mock.ts` behind the `LcuClient` interface (`onChampSelect(callback): unsubscribe`). Swap: write `src/api/lcu.ts` exporting a real `LcuClient` that subscribes to the backend's real push channel, then change the one import in `src/App.tsx`.

## Testing

```
npm test        # vitest run
npm run build   # tsc -b && vite build
```

18 tests cover: all 5 real `/advice` response shapes rendering with the correct accent color and distinct copy, keyboard navigation and submission on the input box, ARIA roles on chat messages (`log`/`article`/`alert`), and the grey-state WCAG AA contrast ratios (calculated, not assumed — see `src/contrast.test.ts`).
