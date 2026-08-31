import { useEffect, useState } from 'react'
import Sidebar from './components/Sidebar'
import QueryThread from './components/QueryThread'
import Composer from './components/Composer'
import './App.css'

export default function App() {
  const [documents, setDocuments] = useState({})   // document_name -> { page_count }
  const [activeDoc, setActiveDoc] = useState(null)
  const [threads, setThreads] = useState({})        // document_name -> [{ question, data?, error? }]
  const [uploading, setUploading] = useState(false)
  const [asking, setAsking] = useState(false)
  const [toast, setToast] = useState(null)

  // Pick up any documents already parsed this server session (e.g. after a
  // page refresh, since the FastAPI registry lives in memory server-side).
  useEffect(() => {
    fetch('/api/documents')
      .then((res) => (res.ok ? res.json() : []))
      .then((docs) => {
        const map = {}
        docs.forEach((d) => { map[d.document_name] = { page_count: d.page_count } })
        setDocuments(map)
      })
      .catch(() => { /* backend not up yet — fine, sidebar just stays empty */ })
  }, [])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 3600)
    return () => clearTimeout(t)
  }, [toast])

  async function handleUpload(file, documentName) {
    setUploading(true)
    const form = new FormData()
    form.append('file', file)
    if (documentName) form.append('document_name', documentName)

    try {
      const res = await fetch('/api/documents/upload', { method: 'POST', body: form })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `Upload failed (${res.status})`)
      }
      const data = await res.json()
      setDocuments((prev) => ({ ...prev, [data.document_name]: { page_count: data.page_count } }))
      setThreads((prev) => ({ ...prev, [data.document_name]: prev[data.document_name] || [] }))
      setActiveDoc(data.document_name)
      setToast(`Parsed ${data.page_count} pages from ${data.document_name}`)
    } catch (e) {
      setToast(e.message)
    } finally {
      setUploading(false)
    }
  }

  async function handleAsk(question) {
    if (!activeDoc) return
    setThreads((prev) => ({
      ...prev,
      [activeDoc]: [...(prev[activeDoc] || []), { question }],
    }))
    setAsking(true)

    try {
      const res = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ document_name: activeDoc, question }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `Query failed (${res.status})`)
      }
      const data = await res.json()
      setThreads((prev) => {
        const entries = [...prev[activeDoc]]
        entries[entries.length - 1] = { question, data }
        return { ...prev, [activeDoc]: entries }
      })
    } catch (e) {
      setThreads((prev) => {
        const entries = [...prev[activeDoc]]
        entries[entries.length - 1] = { question, error: e.message }
        return { ...prev, [activeDoc]: entries }
      })
    } finally {
      setAsking(false)
    }
  }

  return (
    <div className="app">
      <Sidebar
        documents={documents}
        activeDoc={activeDoc}
        onSelectDoc={setActiveDoc}
        onUpload={handleUpload}
        uploading={uploading}
      />

      <div className="main">
        <div className="main-header">
          <div className="main-header-title">{activeDoc || 'No document selected'}</div>
          <div className="main-header-count">
            {activeDoc ? `${documents[activeDoc]?.page_count ?? 0} pages` : ''}
          </div>
        </div>

        <QueryThread
          activeDoc={activeDoc}
          entries={activeDoc ? (threads[activeDoc] || []) : []}
          asking={asking}
        />

        <Composer disabled={!activeDoc || asking} onAsk={handleAsk} />
      </div>

      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}
