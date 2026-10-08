import { ref, watch } from 'vue'
import { fetchHealth, streamChat } from '../api/client'
import { DEFAULT_OPTIONS } from '../types'
import type {
  ChatMessage,
  ChatOptions,
  DisplayMessage,
  DoneEvent,
  HealthInfo,
  RetrievedEvent,
} from '../types'

let nextId = 0

const STORAGE_KEY = 'agent-rag-options'

/** 从 localStorage 恢复上次选的检索配置 —— 演示时不用每次重设。 */
function loadOptions(): ChatOptions {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULT_OPTIONS }
    return { ...DEFAULT_OPTIONS, ...(JSON.parse(raw) as Partial<ChatOptions>) }
  } catch {
    return { ...DEFAULT_OPTIONS }
  }
}

export function useChat() {
  const messages = ref<DisplayMessage[]>([])
  const streaming = ref(false)
  const error = ref<string | null>(null)
  const trace = ref<DoneEvent | null>(null)
  const citationWarning = ref<string | null>(null)
  const retrieved = ref<RetrievedEvent | null>(null)
  const health = ref<HealthInfo | null>(null)
  const options = ref<ChatOptions>(loadOptions())

  let controller: AbortController | null = null

  watch(
    options,
    (value) => {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
      } catch {
        /* 隐私模式下写不进去，不影响使用 */
      }
    },
    { deep: true },
  )

  async function loadHealth(): Promise<void> {
    try {
      health.value = await fetchHealth()
    } catch {
      health.value = null
    }
  }

  async function send(text: string): Promise<void> {
    const content = text.trim()
    if (!content || streaming.value) return

    error.value = null
    trace.value = null
    citationWarning.value = null
    retrieved.value = null

    messages.value.push({ id: ++nextId, role: 'user', content })
    messages.value.push({ id: ++nextId, role: 'assistant', content: '', pending: true })

    // Vue 3 的坑：push 进去的是原始对象，直接改它不会触发更新。
    // 从响应式数组里再读一次拿到的才是 proxy，改这个才有响应。
    const assistant = messages.value[messages.value.length - 1]!

    // pending 的那条要排除掉，否则会把空的助手消息也发回给后端
    const history: ChatMessage[] = messages.value
      .filter((m) => !m.pending)
      .map((m) => ({ role: m.role, content: m.content }))
      .slice(-20)

    streaming.value = true
    controller = new AbortController()

    try {
      await streamChat(
        history,
        options.value,
        {
          onToken: (token) => {
            assistant.content += token
          },
          onRetrieved: (event) => {
            retrieved.value = event
          },
          onDone: (event) => {
            trace.value = event
            const audit = event.citation_audit
            citationWarning.value = audit && audit.status !== 'valid' ? audit.message : null
          },
          onError: (event) => {
            error.value = event.message
          },
        },
        controller.signal,
      )
    } catch (err) {
      if ((err as Error)?.name !== 'AbortError') {
        error.value = err instanceof Error ? err.message : String(err)
      }
    } finally {
      assistant.pending = false
      streaming.value = false
      controller = null
    }
  }

  function stop(): void {
    controller?.abort()
    controller = null
    streaming.value = false
  }

  function reset(): void {
    stop()
    messages.value = []
    trace.value = null
    citationWarning.value = null
    retrieved.value = null
    error.value = null
  }

  return {
    messages,
    streaming,
    error,
    trace,
    citationWarning,
    retrieved,
    health,
    options,
    loadHealth,
    send,
    stop,
    reset,
  }
}
