import type { ChatMessage } from '../chatTypes'
import { HELP_COMMANDS } from '../commands'
import { AdviceMessage, splitIntoSentences } from './AdviceMessage'
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
                {message.streaming ? (
                  message.text
                ) : (
                  <ul className="assistant-bullets">
                    {splitIntoSentences(message.text).map((sentence, i) => (
                      // eslint-disable-next-line react/no-array-index-key -- sentences aren't stable identities
                      <li key={i}>{sentence}</li>
                    ))}
                  </ul>
                )}
              </article>
            )
          case 'error':
            return (
              <article key={message.id} className="chat-message chat-message--error" role="alert">
                {message.text}
              </article>
            )
          case 'help':
            return (
              <article key={message.id} className="chat-message chat-message--help" aria-label="Assistant">
                <ul className="help-command-list">
                  {HELP_COMMANDS.map(({ command, description }) => (
                    <li key={command}>
                      <code>{command}</code> -- {description}
                    </li>
                  ))}
                </ul>
              </article>
            )
        }
      })}
    </div>
  )
}
