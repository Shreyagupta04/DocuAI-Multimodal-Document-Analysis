import { useState } from 'react'

export default function Composer({ disabled, onAsk }) {
  const [question, setQuestion] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    const q = question.trim()
    if (!q || disabled) return
    onAsk(q)
    setQuestion('')
  }

  return (
    <div className="composer">
      <form onSubmit={handleSubmit}>
        <input
          type="text"
          placeholder="Ask about the active document…"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={disabled}
          autoComplete="off"
        />
        <button type="submit" disabled={disabled || !question.trim()}>Ask</button>
      </form>
      <div className="composer-hint">
        Retrieval matches pages by description, then answers grounded on the actual page image.
      </div>
    </div>
  )
}
