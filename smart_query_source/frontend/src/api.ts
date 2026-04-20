const API_BASE = (import.meta.env.VITE_BACKEND_URL as string) ?? ''

export async function postChat(body: any, apiKey?: string){
  const res = await fetch(`${API_BASE}/chat`,{
    method:'POST',
    headers: {
      'Content-Type':'application/json',
      ...(apiKey ? {'X-API-Key': apiKey} : {})
    },
    body: JSON.stringify(body)
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    return { error: `HTTP ${res.status}`, raw: text };
  }
  try {
    return await res.json()
  } catch (e) {
    const text = await res.text().catch(() => '');
    return { error: 'Invalid JSON', raw: text };
  }
}
