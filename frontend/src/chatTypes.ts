import type { AdviceResult } from './api/advice'

export type ChatMessage =
  | { id: string; kind: 'user'; text: string }
  | { id: string; kind: 'advice'; champA: string; champB: string; result: AdviceResult }
  | { id: string; kind: 'assistant-text'; text: string; streaming: boolean }
  | { id: string; kind: 'error'; text: string }
  | { id: string; kind: 'help' }
