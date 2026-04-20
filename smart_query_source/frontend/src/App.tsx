import React, { useState } from 'react'
import Chat from './pages/Chat'
import Results from './pages/Results2'

export default function App(){
  const [route, setRoute] = useState<'chat'|'results'>('chat')
  return (
    <div className="app">
      <header>
        <h1>📊 智能问数</h1>
        <nav>
          <button className={route === 'chat' ? 'active' : ''} onClick={()=>setRoute('chat')}>💬 问答</button>
          <button className={route === 'results' ? 'active' : ''} onClick={()=>setRoute('results')}>📋 结果</button>
        </nav>
      </header>
      <main>
        {route === 'chat' ? <Chat/> : <Results/>}
      </main>
    </div>
  )
}
