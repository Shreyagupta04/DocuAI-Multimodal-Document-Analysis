import { useEffect, useRef } from 'react'

function AnswerBlock({ activeDoc, data }) {
  if (!data.matched_pages || data.matched_pages.length === 0) {
    return (
      <div className="entry-answer">
        <div className="no-match">No relevant page found for this question.</div>
      </div>
    )
  }

  return (
    <div className="entry-answer">
      <div className="answer-block">
        {data.matched_pages.map((tag) => (
          <span className="answer-page-tag" key={tag}>PAGE {tag}</span>
        ))}
        <div>
          {data.results.map((r, i) => (
            <div key={i}>
              <div className="answer-text">{r.answer}</div>
              <div className="answer-page-thumb">
                <img
                  src={`/api/pages/${encodeURIComponent(activeDoc)}/${r.page_no}`}
                  loading="lazy"
                  onError={(e) => { e.currentTarget.parentElement.style.display = 'none' }}
                  alt={`Page ${r.page_no}`}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function QueryThread({ activeDoc, entries, asking }) {
  const threadRef = useRef(null)

  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight
    }
  }, [entries, asking])

  if (!activeDoc) {
    return (
      <div className="thread" ref={threadRef}>
        <div className="thread-empty">
          <div className="thread-empty-icon">⌗</div>
          <p>
            Upload a document on the left, then ask questions about it here. Answers are
            grounded on the actual matched page image, with page references cited.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="thread" ref={threadRef}>
      {entries.length === 0 && (
        <div className="thread-empty">
          <div className="thread-empty-icon">⌗</div>
          <p>Ask a question about <strong>{activeDoc}</strong> below.</p>
        </div>
      )}

      {entries.map((entry, i) => (
        <div key={i}>
          <div className="entry-question">{entry.question}</div>
          {entry.error ? (
            <div className="entry-answer">
              <div className="no-match">{entry.error}</div>
            </div>
          ) : entry.data ? (
            <AnswerBlock activeDoc={activeDoc} data={entry.data} />
          ) : null}
        </div>
      ))}

      {asking && (
        <div className="thinking">
          <span className="thinking-dot" /><span className="thinking-dot" /><span className="thinking-dot" />
          matching pages and reading the grounded image…
        </div>
      )}
    </div>
  )
}
