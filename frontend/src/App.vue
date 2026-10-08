<script setup lang="ts">
import { onMounted } from 'vue'
import ChatPanel from './components/ChatPanel.vue'
import TracePanel from './components/TracePanel.vue'
import { useChat } from './composables/useChat'

const {
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
} = useChat()

onMounted(loadHealth)

const MODES = [
  { value: 'bm25', label: 'BM25', hint: '纯词法检索' },
  { value: 'vector', label: '向量', hint: '纯语义检索' },
  { value: 'hybrid', label: '混合', hint: 'BM25 + 向量 + RRF 融合' },
  { value: 'agent', label: 'Agent', hint: '查询分解 + 自评补检 + 上下文压缩' },
] as const
</script>

<template>
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <span class="pulse" />
        <strong>Agentic RAG</strong>
        <span class="tag">自建评测 · 消融实验 · 全链路 Trace</span>
      </div>

      <div class="meta">
        <template v-if="health">
          <span class="badge ok">{{ health.provider }} / {{ health.model }}</span>
          <span v-if="health.code_version" class="mono muted" :title="'后端进程加载的代码版本'">
            {{ health.code_version }}
          </span>
        </template>
        <span v-else class="badge warn">后端未连接</span>
      </div>
    </header>

    <!-- 检索策略切换：演示时能当场对比不同策略的 trace 与答案 -->
    <div class="toolbar">
      <span class="toolbar-label">检索策略</span>
      <div class="segmented">
        <button
          v-for="mode in MODES"
          :key="mode.value"
          :class="{ active: options.retrievalMode === mode.value }"
          :title="mode.hint"
          @click="options.retrievalMode = mode.value"
        >
          {{ mode.label }}
        </button>
      </div>

      <label class="switch" :class="{ disabled: options.retrievalMode !== 'agent' }">
        <input
          v-model="options.compress"
          type="checkbox"
          :disabled="options.retrievalMode !== 'agent'"
        />
        <span>上下文压缩</span>
      </label>

      <template v-if="options.retrievalMode === 'agent'">
        <label class="switch">
          <span class="muted">给模型</span>
          <input v-model.number="options.agentTopK" type="number" min="1" max="20" class="num" />
          <span class="muted">块</span>
        </label>
      </template>

      <span class="toolbar-hint muted">
        {{ MODES.find((m) => m.value === options.retrievalMode)?.hint }}
      </span>
    </div>

    <main class="layout">
      <ChatPanel
        :messages="messages"
        :streaming="streaming"
        :error="error"
        :citation-warning="citationWarning"
        @send="send"
        @stop="stop"
        @reset="reset"
      />
      <TracePanel :trace="trace" :retrieved="retrieved" />
    </main>
  </div>
</template>
