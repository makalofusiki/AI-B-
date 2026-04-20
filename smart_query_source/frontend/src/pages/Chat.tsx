import React, { useEffect, useState } from 'react'
import { postChat } from '../api'

type Msg = { role: 'user'|'assistant'|'system', text: string, charts?: string[], meta?: any }

const EXAMPLES = [
  '金花股份2024年利润总额是多少？',
  '2024年营业收入最高的前10家公司',
  '太极集团2023年净利润同比增长',
  '资产负债率最低的中药公司',
  '每股收益率最高的前5家企业'
]

export default function Chat(){
  const [apiKey, setApiKey] = useState(localStorage.getItem('service_api_key')||'')
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState<Msg[]>(() => {
    try{ return JSON.parse(localStorage.getItem('chat_messages') || '[]') }catch{ return [] }
  })
  const [loading, setLoading] = useState(false)

  useEffect(()=>{ localStorage.setItem('chat_messages', JSON.stringify(messages)) }, [messages])

  function saveKey(k:string){
    setApiKey(k); localStorage.setItem('service_api_key', k)
  }

  function clearChat(){
    setMessages([]); localStorage.removeItem('chat_messages')
  }

  function useExample(q: string){
    setQuestion(q)
  }

  async function send(){
    if(!question.trim()) return
    const q = question.trim()
    setQuestion('')
    const userMsg: Msg = {role:'user', text: q}
    setMessages(m=>[...m, userMsg])
    setLoading(true)

      try{
      const body = { question: q, session_id: 'web', question_id: Date.now().toString(), turn_index: 1 }
      const j = await postChat(body, apiKey)

      let text = ''
      const charts: string[] = []
      // Prefer structured answer if available
      if (j && j.answer && j.answer.final_answer) {
        const fa = j.answer.final_answer
        if (fa.analysis) text += '📊 分析: ' + fa.analysis + '\n\n'
        if (fa.sql) text += '🔍 SQL:\n```sql\n' + fa.sql + '\n```\n\n'
        if (fa.result) {
          text += '📈 结果:\n'
          text += typeof fa.result === 'string' ? fa.result : JSON.stringify(fa.result, null, 2)
        }
        if (fa.clarification) text += '\n💡 澄清: ' + fa.clarification
        if (fa.charts && Array.isArray(fa.charts)) {
          for (const c of fa.charts) {
            let p = String(c || '').replace(/\\/g, '/')
            if (!p.startsWith('http') && !p.startsWith('/')) p = '/' + p
            charts.push(p)
          }
        }
      } else if (j && j.error) {
        // Top-level error from backend
        text = `错误: ${j.error}` + (j.raw ? `\n${j.raw}` : '')
      } else if (j && j.answer && j.answer.error) {
        // Nested error inside answer
        text = `错误: ${j.answer.error}` + (j.answer.raw ? `\n${j.answer.raw}` : '')
      } else if (j && j.answer && j.answer.text) {
        // Fallback: show plain answer text if provided
        text = j.answer.text
      } else {
        text = typeof j === 'string' ? j : JSON.stringify(j, null, 2)
      }

      const assistantMsg: Msg = { role: 'assistant', text: text || '（无文本回答）', charts: charts, meta: j }
      setMessages(m=>[...m, assistantMsg])
    }catch(e:any){
      const errMsg: Msg = { role: 'system', text: '❌ 请求失败: ' + (e?.message||String(e)) }
      setMessages(m=>[...m, errMsg])
    }finally{ setLoading(false) }
  }

  function handleKeyDown(e: React.KeyboardEvent){
    if (e.key === 'Enter' && e.ctrlKey) send()
  }

  return (
    <div className="panel">
      <div className="controls">
        <input
          type="password"
          value={apiKey}
          onChange={e=>saveKey(e.target.value)}
          placeholder="可选: Service API Key"
          style={{flex:1, maxWidth:'300px'}}
        />
        <button onClick={clearChat}>清空会话</button>
      </div>

      <div className="examples">
        <span style={{fontSize:'13px', color:'#64748b'}}>试试:</span>
        {EXAMPLES.map((q, i) => (
          <button key={i} onClick={()=>useExample(q)}>{q}</button>
        ))}
      </div>

      <div className="query-input">
        <textarea
          value={question}
          onChange={e=>setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入你的问题... (Ctrl+Enter 发送)"
          rows={3}
        />
        <button onClick={send} disabled={loading}>
          {loading ? '查询中...' : '发送'}
        </button>
      </div>

      {loading && (
        <div className="loading">
          <div className="spinner"></div>
        </div>
      )}

      <div className="messages">
        {messages.length === 0 && (
          <div className="empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
            </svg>
            <h3>欢迎使用智能问数</h3>
            <p>输入关于中药上市公司财务数据的问题，我会帮你查询并生成分析</p>
          </div>
        )}
        {messages.map((m, i)=> (
          <div key={i} className={`msg ${m.role}`}>
            <strong>{m.role === 'user' ? '你' : m.role === 'assistant' ? 'AI助手' : '系统'}</strong>
            <pre>{m.text}</pre>
            {m.charts && m.charts.length > 0 && (
              <div className="charts">
                {m.charts.map((c, idx) => (
                  <img key={idx} src={c} alt={`chart-${idx}`} />
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
