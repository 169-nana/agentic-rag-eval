<script setup lang="ts">
import { computed } from 'vue'
import TraceTimeline from './TraceTimeline.vue'
import type { DoneEvent, RetrievedEvent } from '../types'

const props = defineProps<{ trace: DoneEvent | null; retrieved: RetrievedEvent | null }>()

/** 压缩统计优先从 retrieved 事件拿（那里是权威来源）。 */
const compression = computed(() => props.retrieved?.compression ?? null)

const savedPct = computed(() => {
  const c = compression.value
  if (!c || !c.chars_before) return 0
  return Math.round((1 - c.chars_after / c.chars_before) * 100)
})
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>Trace</h2>
      <span v-if="trace" class="mono muted">{{ trace.trace_id }}</span>
    </div>

    <div v-if="!trace" class="empty small">
      发一条消息后，这里会显示本次请求的<br />
      <b>执行时间线</b>：每个阶段几时开始、花了多久、<br />
      是串行还是并行，一眼可见。<br /><br />
      试试右上角切换检索策略 —— <br />
      纯 BM25 和多跳分解的差别是看得见的。
    </div>

    <div v-else class="trace-body">
      <div class="stats">
        <div class="stat">
          <span class="stat-label">端到端</span>
          <span class="stat-value">{{ trace.duration_ms.toFixed(0) }}<i>ms</i></span>
        </div>
        <div class="stat">
          <span class="stat-label">输入 token</span>
          <span class="stat-value">{{ trace.usage.prompt_tokens }}</span>
        </div>
        <div class="stat">
          <span class="stat-label">输出 token</span>
          <span class="stat-value">{{ trace.usage.completion_tokens }}</span>
        </div>
        <div class="stat">
          <span class="stat-label">合计</span>
          <span class="stat-value accent">{{ trace.usage.total_tokens }}</span>
        </div>
      </div>

      <div v-if="trace.citation_audit" class="compress-row">
        <span class="stat-label">引用编号检查</span>
        <span
          class="badge"
          :class="trace.citation_audit.status === 'valid' ? 'ok' : 'warn'"
        >
          {{ trace.citation_audit.status === 'valid' ? '编号有效' : '需检查' }}
        </span>
        <span class="muted small">{{ trace.citation_audit.message }}</span>
      </div>

      <!-- 上下文压缩：这一行是"用同样的预算看更多资料"的直接证据 -->
      <div v-if="compression" class="compress-row">
        <span class="stat-label">上下文压缩</span>
        <span class="mono">
          {{ compression.chunks_before }} 块 → <b>{{ compression.chunks_after }}</b> 块 ·
          {{ compression.chars_before }} 字 → <b>{{ compression.chars_after }}</b> 字
        </span>
        <span class="badge ok">省 {{ savedPct }}%</span>
      </div>

      <TraceTimeline
        v-if="trace.spans.length"
        :spans="trace.spans"
        :total-ms="trace.duration_ms"
      />

      <h3 class="section-title">检索到的资料（{{ retrieved?.chunks.length ?? 0 }} 块）</h3>
      <ul v-if="retrieved" class="chunks">
        <li v-for="chunk in retrieved.chunks" :key="chunk.index" class="chunk">
          <span class="chunk-index mono">[{{ chunk.index }}]</span>
          <span class="chunk-text">{{ chunk.text.slice(0, 120) }}<span v-if="chunk.text.length > 120">…</span></span>
        </li>
      </ul>
      <p v-else class="muted small">本次没有 retrieved 事件</p>
    </div>
  </section>
</template>
