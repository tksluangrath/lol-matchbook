import type { ChatMessage } from '../chatTypes'
import { AdviceMessage } from './AdviceMessage'
import './MessageList.css'

type Props = {
  messages: ChatMessage[]
}

export function MessageList({ messages }: Props) {
  return (
    <div className="message-list" role="log" aria-live="polite" aria-label="Conversation">
      {messages.map((message) => {
        switch (message.kind) {
          case 'user':
            return (
              <article key={message.id} className="chat-message chat-message--user" aria-label="You">
                {message.text}
              </article>
            )
          case 'advice':
            return <AdviceMessage key={message.id} champA={message.champA} champB={message.champB} result={message.result} />
          case 'assistant-text':
            return (
              <article
                key={message.id}
                className="chat-message chat-message--assistant"
                aria-label="Assistant"
                aria-busy={message.streaming}
              >
                {message.text}
              </article>
            )
          case 'error':
            return (
              <article key={message.id} className="chat-message chat-message--error" role="alert">
                {message.text}
              </article>
            )
        }
      })}
    </div>
  )
}
