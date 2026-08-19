import { useState } from 'react'
import type { FormEvent } from 'react'
import { REAL_RANKS, REAL_ROLES } from '../commands'
import './InputBox.css'

type Props = {
  onSubmit: (text: string) => void
  disabled?: boolean
}

// Recognized as already-present rank/role tokens in a typed /advice command,
// so the dropdowns don't double-append onto text the user already typed
// them into (REAL_ROLES no longer includes 'utility' -- see commands.ts --
// but it's still a real thing someone might type, so it's checked for here
// too).
const RANK_OR_ROLE_TOKEN = new RegExp(`\\b(${[...REAL_RANKS, ...REAL_ROLES, 'utility'].join('|')})\\b`, 'i')

export function InputBox({ onSubmit, disabled }: Props) {
  const [value, setValue] = useState('')
  const [rank, setRank] = useState<(typeof REAL_RANKS)[number]>('emerald')
  const [role, setRole] = useState<(typeof REAL_ROLES)[number]>('top')

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    let trimmed = value.trim()
    if (!trimmed) return
    // Only /advice takes rank/role -- append the dropdown picks so typing
    // them is optional, but leave alone if the user already typed them.
    if (/^\/advice\b/i.test(trimmed) && !RANK_OR_ROLE_TOKEN.test(trimmed)) {
      trimmed = `${trimmed} ${rank} ${role}`
    }
    onSubmit(trimmed)
    setValue('')
  }

  return (
    <form className="input-box" onSubmit={handleSubmit}>
      <label htmlFor="chat-input" className="input-box__label">
        Ask a follow-up question
      </label>
      <input
        id="chat-input"
        type="text"
        value={value}
        disabled={disabled}
        onChange={(event) => setValue(event.target.value)}
        placeholder="e.g. How do I trade in lane vs this matchup?"
        autoComplete="off"
      />
      <label htmlFor="rank-select" className="input-box__label">
        Rank (used for /advice)
      </label>
      <select
        id="rank-select"
        className="input-box__select"
        value={rank}
        disabled={disabled}
        onChange={(event) => setRank(event.target.value as (typeof REAL_RANKS)[number])}
      >
        {REAL_RANKS.map((r) => (
          <option key={r} value={r}>
            {r}
          </option>
        ))}
      </select>
      <label htmlFor="role-select" className="input-box__label">
        Role (used for /advice)
      </label>
      <select
        id="role-select"
        className="input-box__select"
        value={role}
        disabled={disabled}
        onChange={(event) => setRole(event.target.value as (typeof REAL_ROLES)[number])}
      >
        {REAL_ROLES.map((r) => (
          <option key={r} value={r}>
            {r}
          </option>
        ))}
      </select>
      <button type="submit" disabled={disabled || !value.trim()}>
        Send
      </button>
    </form>
  )
}
