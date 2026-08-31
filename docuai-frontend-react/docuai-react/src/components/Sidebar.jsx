import { useRef, useState } from 'react'

export default function Sidebar({ documents, activeDoc, onSelectDoc, onUpload, uploading }) {
  const fileInputRef = useRef(null)
  const [dragOver, setDragOver] = useState(false)
  const [docName, setDocName] = useState('')

  const docNames = Object.keys(documents)

  function handleFiles(files) {
    if (files && files.length) {
      onUpload(files[0], docName.trim() || null)
    }
  }

  return (
    <div className="sidebar">
      <div className="brand">
        <div className="brand-mark"><span className="dot" />DocuAI</div>
        <div className="brand-sub">STRUCTURED DOCUMENT INTELLIGENCE</div>
      </div>

      <label
        className={`upload-zone${dragOver ? ' dragover' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={(e) => { e.preventDefault(); setDragOver(false) }}
        onDrop={(e) => {
          e.preventDefault()
          setDragOver(false)
          handleFiles(e.dataTransfer.files)
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,.html,.md,.csv"
          onChange={(e) => handleFiles(e.target.files)}
          disabled={uploading}
        />
        <div className="upload-zone-label">
          {uploading ? 'Parsing… this can take a while' : 'Drop a document, or click to upload'}
        </div>
        <div className="upload-zone-hint">PDF · DOCX · HTML · MD · CSV</div>
      </label>

      <div className="doc-name-field">
        <input
          type="text"
          placeholder="Document name (optional)"
          value={docName}
          onChange={(e) => setDocName(e.target.value)}
        />
      </div>

      <div className="section-label">Parsed documents</div>
      <div className="doc-list">
        {docNames.length === 0 ? (
          <div className="empty-dock">
            Nothing parsed yet in this session. Upload a document above — it'll be split into
            pages, described by the vision model, and written into Neo4j.
          </div>
        ) : (
          docNames.map((name) => (
            <div
              key={name}
              className={`doc-card${name === activeDoc ? ' active' : ''}`}
              onClick={() => onSelectDoc(name)}
            >
              <div className="doc-card-title">{name}</div>
              <div className="doc-card-meta">
                {documents[name].page_count} page{documents[name].page_count === 1 ? '' : 's'} parsed
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
