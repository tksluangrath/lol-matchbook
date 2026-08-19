import type { AdviceResult } from '../api/advice'
import { ADVICE_STATE_BADGE_LABEL, ADVICE_STATE_COLOR } from '../theme'
import './AdviceMessage.css'

type Props = {
  champA: string
  champB: string
  result: AdviceResult
}

const PHASE_LABELS = { early: 'Early', mid: 'Mid', late: 'Late' } as const

/**
 * Splits real generated phase prose into sentence-level bullets. Splits
 * only after sentence-ending punctuation (. ! ?) followed by whitespace --
 * semicolon-joined clauses ("Avoid X; do Y.") stay together as one bullet,
 * not split on every clause. Render-only: does not touch stored text.
 */
export function splitIntoSentences(text: string): string[] {
  return text
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => sentence.trim())
    .filter(Boolean)
}

/**
 * Renders literal "**bold**" markdown that sometimes leaks into generated
 * text (the model isn't instructed to avoid it) as real emphasis instead of
 * showing raw asterisks. Only handles bold -- the only markdown syntax
 * observed in real generated text so far.
 */
export function renderInlineMarkdown(sentence: string): React.ReactNode {
  const parts = sentence.split(/\*\*(.+?)\*\*/g)
  if (parts.length === 1) return sentence
  return parts.map((part, i) =>
    // eslint-disable-next-line react/no-array-index-key -- parts aren't stable identities
    i % 2 === 1 ? <strong key={i}>{part}</strong> : part,
  )
}

function PhaseBreakdown({ phases }: { phases: { early: string; mid: string; late: string } }) {
  return (
    <dl className="advice-phases">
      {(Object.keys(PHASE_LABELS) as Array<keyof typeof PHASE_LABELS>).map((phase) => (
        <div key={phase} className="advice-phase">
          <dt>{PHASE_LABELS[phase]}</dt>
          <dd>
            <ul className="advice-phase-bullets">
              {splitIntoSentences(phases[phase]).map((sentence, i) => (
                // eslint-disable-next-line react/no-array-index-key -- sentences aren't stable identities
                <li key={i}>{renderInlineMarkdown(sentence)}</li>
              ))}
            </ul>
          </dd>
        </div>
      ))}
    </dl>
  )
}

export function AdviceMessage({ champA, champB, result }: Props) {
  const accent = ADVICE_STATE_COLOR[result.kind]

  let heading: string
  let body: React.ReactNode

  switch (result.kind) {
    case 'hit':
      heading = `${champA} vs ${champB}`
      body = <PhaseBreakdown phases={result.phases} />
      break
    case 'wider_rank_fallback':
      heading = `${champA} vs ${champB} -- fallback from a wider rank bracket`
      body = (
        <>
          <p className="advice-note">
            No data at your exact rank yet, so this is pulled from a nearby rank bracket instead.
          </p>
          <PhaseBreakdown phases={result.phases} />
        </>
      )
      break
    case 'abstention':
      heading = `${champA} vs ${champB} -- not enough data`
      body = <p className="advice-note">Not enough data at this rank to give matchup-specific advice yet.</p>
      break
    case 'archetype_fallback':
      heading = `${champA} vs ${champB} -- general champion info only`
      body = (
        <>
          <p className="advice-note">
            No matchup-specific advice computed for this pair yet -- here's general info on each champion instead.
            Only a portion of real matchups are precomputed so far, so this is expected for less-common pairs, not a
            sign anything is broken.
          </p>
          <p>
            <strong>{champA}:</strong> {result.champABlurb}
          </p>
          <p>
            <strong>{champB}:</strong> {result.champBBlurb}
          </p>
        </>
      )
      break
    case 'not_precomputed':
      heading = `${champA} vs ${champB} -- not yet computed`
      body = (
        <p className="advice-note">
          This matchup hasn't been computed yet. Run a refresh, or check back after the next patch update.
        </p>
      )
      break
  }

  return (
    <article
      className="advice-message"
      style={{ borderColor: accent, ['--advice-accent' as string]: accent }}
      data-advice-kind={result.kind}
      aria-label={`Advice: ${heading}`}
    >
      <div className="advice-heading-row">
        <h3 className="advice-heading">{heading}</h3>
        <span className="advice-badge" style={{ ['--badge-accent' as string]: accent }}>
          {ADVICE_STATE_BADGE_LABEL[result.kind]}
        </span>
      </div>
      {body}
    </article>
  )
}
