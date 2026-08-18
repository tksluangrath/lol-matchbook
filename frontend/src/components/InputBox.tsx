import { useState } from 'react'
import type { FormEvent } from 'react'
import './InputBox.css'

type Props = {
  onSubmit: (text: string) => void
  disabled?: boolean
}

export function InputBox({ onSubmit, disabled }: Props) {
  const [value, setValue] = useState('')

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = value.trim()
    if (!trimmed) return
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
      <button type="submit" disabled={disabled || !value.trim()}>
        Send
      </button>
    </form>
  )
}
