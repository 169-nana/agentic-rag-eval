import type {
  ChatMessage,
  ChatOptions,
  DoneEvent,
  ErrorEvent,
  HealthInfo,
  RetrievedEvent,
  StartEvent,
} from '../types'

/** 默认直连后端。后端已开 CORS，不走 Vite 代理是为了避免代理缓冲吃掉流式效果。 */
export const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

export interface StreamHandlers {
  onStart?: (event: StartEvent) => void
  onToken?: (text: string) => void
  /** 检索结果。前端以前忽略它，现在用它来渲染"这次用了哪几块资料"。 */
  onRetrieved?: (event: RetrievedEvent) => void
  onDone?: (event: DoneEvent) => void
  onError?: (event: ErrorEvent) => void
}

interface Frame {
  event: string
  data: string
}

/**
 * 向 /api/chat 发起请求并按 SSE 逐块消费。
 *
 * 不用原生 EventSource 的原因：它只支持 GET，而聊天要 POST 对话历史。
 * 所以这里用 fetch + ReadableStream 手动解析 SSE 分帧。
 */
export async function streamChat(
  messages: ChatMessage[],
  options: ChatOptions,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      messages,
      // 前端的 camelCase → 后端的 snake_case。
      // 后端这些参数本来是为消融实验留的，前端接上之后
      // 就能在界面上直接切换检索策略、当场看到 trace 的变化。
      retrieval_mode: options.retrievalMode,
      compress: options.compress,
      agent_top_k: options.agentTopK,
    }),
    signal,
  })

  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new Error(`HTTP ${response.status} ${detail.slice(0, 300)}`)
  }
  if (!response.body) {
    throw new Error('响应没有 body，无法流式读取')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // SSE 以空行分帧；一个网络分片里可能含多个事件，也可能只有半个
      let separator = buffer.indexOf('\n\n')
      while (separator !== -1) {
        const raw = buffer.slice(0, separator)
        buffer = buffer.slice(separator + 2)
        dispatch(parseFrame(raw), handlers)
        separator = buffer.indexOf('\n\n')
      }
    }
    // 处理末尾没有空行结尾的残留帧
    if (buffer.trim()) {
      dispatch(parseFrame(buffer), handlers)
    }
  } finally {
    reader.releaseLock()
  }
}

function parseFrame(raw: string): Frame | null {
  let event = 'message'
  const dataLines: string[] = []

  for (const line of raw.split('\n')) {
    if (line.startsWith(':')) continue // 注释行（心跳）
    if (line.startsWith('event:')) {
      event = line.slice('event:'.length).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).trimStart())
    }
  }

  if (dataLines.length === 0) return null
  return { event, data: dataLines.join('\n') }
}

function dispatch(frame: Frame | null, handlers: StreamHandlers): void {
  if (!frame) return

  let payload: unknown
  try {
    payload = JSON.parse(frame.data)
  } catch {
    console.warn('[sse] 无法解析的 data 帧', frame.data)
    return
  }

  switch (frame.event) {
    case 'start':
      handlers.onStart?.(payload as StartEvent)
      break
    case 'retrieved':
      handlers.onRetrieved?.(payload as RetrievedEvent)
      break
    case 'token':
      handlers.onToken?.((payload as { text: string }).text)
      break
    case 'done':
      handlers.onDone?.(payload as DoneEvent)
      break
    case 'error':
      handlers.onError?.(payload as ErrorEvent)
      break
  }
}

export async function fetchHealth(): Promise<HealthInfo> {
  const response = await fetch(`${API_BASE}/api/health`)
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return (await response.json()) as HealthInfo
}
