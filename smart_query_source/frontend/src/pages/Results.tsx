import React, { useEffect, useState } from 'react'

type FileItem = { name: string; url: string; size?: number; mtime?: string; content_type?: string }
type Preview = { name: string; url: string; kind: 'json'|'image'|'other'; content?: string }

function formatBytes(bytes?: number){
  if (bytes === undefined || bytes === null) return ''
  if (bytes < 1024) return `${bytes} B`
  const kb = bytes / 1024
  if (kb < 1024) return `${kb.toFixed(1)} KB`
  const mb = kb / 1024
  return `${mb.toFixed(2)} MB`
}

export default function Results(){
  const [files, setFiles] = useState<FileItem[]>([]) 
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [apiKey, setApiKey] = useState(localStorage.getItem('service_api_key') || '')
  const [preview, setPreview] = useState<Preview | null>(null)
  const [metaLoading, setMetaLoading] = useState<string | null>(null)
  const [batchRunning, setBatchRunning] = useState(false)
  const [batchStatus, setBatchStatus] = useState<string | null>(null)

  useEffect(()=>{ loadFiles() }, [])

  async function loadFiles(){
    setLoading(true); setError(null)
    try{
      const headers: Record<string,string> = {}
      if (apiKey) headers['X-API-Key'] = apiKey
      const res = await fetch('/results/list', { headers })
      if (!res.ok) {
        const txt = await res.text()
        throw new Error(`${res.status} ${txt}`)
      }
      const j = await res.json()
      setFiles(j.files || [])
    }catch(e:any){
      setError(e?.message || String(e))
    }finally{ setLoading(false) }
  }

  function onKeyChange(v:string){
    setApiKey(v); localStorage.setItem('service_api_key', v)
  }

  function extOf(name:string){
    const m = name.match(/\.([^.]+)$/)
    return m ? m[1].toLowerCase() : ''
  }

  async function previewFile(f: FileItem){    
    const ext = extOf(f.name)
    if (['json'].includes(ext)){
      setMetaLoading(f.name)
      try{        const headers: Record<string,string> = {}        if (apiKey) headers['X-API-Key'] = apiKey        const res = await fetch(f.url, { headers })        if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)        const txt = await res.text()        try{ const parsed = JSON.parse(txt); setPreview({ name: f.name, url: f.url, kind: 'json', content: JSON.stringify(parsed, null, 2) }) }        catch{ setPreview({ name: f.name, url: f.url, kind: 'json', content: txt }) }      }catch(e:any){ setError('预览失败: ' + (e?.message||String(e))) }      finally{ setMetaLoading(null) }      return    }
    if (['png','jpg','jpeg','gif'].includes(ext)){      setPreview({ name: f.name, url: f.url, kind: 'image' })      return    }
    // Fallback: open other files in new tab (likely xlsx)    window.open(f.url, '_blank')  }

  async function startBatch(){
    if (batchRunning) return
    if (!window.confirm('开始全量批处理？该操作可能需要较长时间并且会阻塞请求（后端 /batch 目前为同步）。继续吗？')) return
    setBatchRunning(true); setBatchStatus('开始请求后端...'); setError(null)
    try{
      const headers: Record<string,string> = {'Content-Type':'application/json'}
      if (apiKey) headers['X-API-Key'] = apiKey
      const res = await fetch('/batch', { method: 'POST', headers, body: JSON.stringify({}) })
      if (!res.ok){
        const txt = await res.text()
        throw new Error(`${res.status} ${txt}`)
      }
      const j = await res.json()
      setBatchStatus('后端返回: ' + (j.status || 'ok'))
      setTimeout(()=>{ loadFiles(); setBatchStatus('完成，已刷新结果列表') }, 1500)
    }catch(e:any){
      setError('启动批处理失败: ' + (e?.message||String(e)))
      setBatchStatus(null)
    }finally{ setBatchRunning(false) }
  }

  function closePreview(){ setPreview(null) }

  return (
    <div className="panel">
      <h2>批量结果</h2>

      <div className="controls" style={{display:'flex',gap:8,alignItems:'center'}}>
        <input
          type="password"
          placeholder="Service API Key（可留空）"
          value={apiKey}
          onChange={e=>onKeyChange(e.target.value)}
          style={{flex:1, maxWidth:320}}
        />
        <button onClick={loadFiles} disabled={batchRunning}>刷新</button>
        <button onClick={startBatch} disabled={batchRunning} style={{marginLeft:8}}>{batchRunning ? '运行中...' : '开始全量跑'}</button>
      </div>

      <div style={{display:'flex',gap:8,marginTop:12,alignItems:'center'}}>
        <input placeholder="按文件名搜索" value={searchTerm} onChange={e=>setSearchTerm(e.target.value)} style={{flex:1, maxWidth:320}} />
        <select value={filterType} onChange={e=>setFilterType(e.target.value as any)}>
          <option value="all">全部</option>
          <option value="json">JSON</option>
          <option value="image">图片</option>
          <option value="xlsx">表格 (xls/csv)</option>
          <option value="other">其他</option>
        </select>
      </div>
      {loading && <p>加载中...</p>}
      {error && <p style={{color:'crimson'}}>错误: {error}</p>}

      {!loading && !error && files.length === 0 && (
        <div>
          <p>未找到结果文件。后端应将结果目录挂载为 /results/files 并启用 /results/list 列表接口。</p>
          <p>若已有静态文件，也可直接访问 <a href="/results/files/">/results/files/</a></p>
        </div>
      )}

      {!loading && !error && files.length > 0 && (
        <div>
          <p>点击文件名可预览 JSON 或图片，其他格式将在新标签页打开。</p>
          <ul>
            {files.map(f=> (
              <li key={f.name} style={{marginBottom:6}}>                <a href="#" onClick={(e)=>{ e.preventDefault(); previewFile(f) }}>{f.name}</a>                {' '}                <a href={f.url} target="_blank" rel="noreferrer" style={{marginLeft:8}}>下载</a>                {metaLoading === f.name && <span style={{marginLeft:8}}>加载...</span>}              </li>            ))}
          </ul>
        </div>
      )}

      {preview && (
        <div style={{position:'fixed',left:0,top:0,right:0,bottom:0,background:'rgba(0,0,0,0.6)',display:'flex',alignItems:'center',justifyContent:'center'}} onClick={closePreview}>
          <div style={{background:'#fff',padding:16,borderRadius:6,maxWidth:'90%',maxHeight:'90%',overflow:'auto'}} onClick={e=>e.stopPropagation()}>
            <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:8}}>              <strong>{preview.name}</strong>              <button onClick={closePreview}>关闭</button>            </div>            {preview.kind === 'image' && (
              <img src={preview.url} alt={preview.name} style={{maxWidth:'90vw',maxHeight:'80vh'}} />
            )}            {preview.kind === 'json' && (
              <pre style={{whiteSpace:'pre-wrap',fontSize:12}}>{preview.content}</pre>
            )}            {preview.kind === 'other' && (
              <p>无法预览此格式，已打开下载链接。</p>            )}
          </div>
        </div>
      )}

      <p style={{marginTop:12, fontSize:12, color:'#64748b'}}>注: API Key 可留空以使用开发模式（当后端未配置 SERVICE_API_KEY 时）。</p>
    </div>
  )
}
