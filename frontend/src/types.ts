export type Role = 'user' | 'assistant'

export interface ChatMessage {
  role: Role
  content: string
}

export interface Usage {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}

export interface TraceSpan {
  name: string
  duration_ms: number
  /**
   * 相对本次请求起点的偏移（毫秒）。
   *
   * 有了它才能画**甘特图** —— 看出各阶段是串行还是并行、
   * 哪个父 span 套了哪些子 span。
   * 只有 duration_ms 的话，最多只能画"谁耗时最长"的条形列表。
   */
  start_ms?: number
  attributes: Record<string, unknown>
  error: string | null
}

/** 一次请求里用到的检索配置（会随请求发给后端）。 */
export interface ChatOptions {
  retrievalMode: 'bm25' | 'vector' | 'hybrid' | 'agent'
  compress: boolean
  agentTopK: number
}

export const DEFAULT_OPTIONS: ChatOptions = {
  retrievalMode: 'agent',
  compress: true,
  agentTopK: 10,
}

export interface CompressionStats {
  chunks_before: number
  chunks_after: number
  chars_before: number
  chars_after: number
  ratio: number
}

export interface RetrievedChunk {
  index: number
  chunk_id: number
  doc_id: number
  score: number
  text: string
}

export interface RetrievedEvent {
  chunks: RetrievedChunk[]
  compression: CompressionStats | null
}

export interface StartEvent {
  trace_id: string
  provider: string
  model: string
}

export interface DoneEvent {
  trace_id: string
  duration_ms: number
  usage: Usage
  spans: TraceSpan[]
  citation_audit?: {
    status: 'valid' | 'missing' | 'invalid'
    references: number[]
    invalid_references: number[]
    source_count: number
    message: string
  }
}

export interface ErrorEvent {
  message: string
  retryable?: boolean
}

export interface HealthInfo {
  status: string
  provider: string
  model: string
  mock_mode?: boolean
  trace_enabled?: boolean
  /** 进程实际加载的代码版本（按 app/*.py 修改时间算）。 */
  code_version?: string
}

export interface DisplayMessage extends ChatMessage {
  id: number
  /** 正在流式接收中，用来渲染光标 */
  pending?: boolean
}
