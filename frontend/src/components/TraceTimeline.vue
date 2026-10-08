<script setup lang="ts">
import { computed } from 'vue'
import type { TraceSpan } from '../types'

const props = defineProps<{ spans: TraceSpan[]; totalMs: number }>()

/** 阶段分类。父 span 要单独处理，否则会盖住它的子 span。 */
function kind(name: string): string {
  if (name.includes('assess+compress')) return 'merged'
  if (name.startsWith('planner.decompose')) return 'plan'
  if (name.startsWith('planner.assess')) return 'grade'
  if (name.startsWith('compress')) return 'compress'
  if (name.startsWith('retrieve.round')) return 'search'
  if (name.startsWith('retrieve.')) return 'total'
  if (name.startsWith('llm.')) return 'generate'
  return 'other'
}

/** 父 span：覆盖了其他阶段的那些（检索总计）。它们画成细线，不挡子阶段。 */
function isParent(span: TraceSpan): boolean {
  return kind(span.name) === 'total'
}

const KIND_LABEL: Record<string, string> = {
  plan: '问题分解',
  search: '检索',
  grade: '资料自评',
  merged: '自评+压缩',
  compress: '上下文压缩',
  total: '检索总计',
  generate: '生成回答',
  other: '其他',
}

/** 时间轴刻度（0 / 25% / 50% / 75% / 100%）。 */
const ticks = computed(() => {
  const total = props.totalMs || 1
  return [0, 0.25, 0.5, 0.75, 1].map((f) => ({
    pct: f * 100,
    label: `${(total * f / 1000).toFixed(2)}s`,
  }))
})

/** 按开始时间排序；没有 start_ms 的排最后（兼容旧后端）。 */
const rows = computed(() =>
  [...props.spans].sort((a, b) => (a.start_ms ?? 1e9) - (b.start_ms ?? 1e9)),
)

const scale = computed(() => Math.max(props.totalMs, ...props.spans.map((s) => (s.start_ms ?? 0) + s.duration_ms), 1))

function left(span: TraceSpan): string {
  return `${(((span.start_ms ?? 0) / scale.value) * 100).toFixed(2)}%`
}

function width(span: TraceSpan): string {
  return `${Math.max((span.duration_ms / scale.value) * 100, 0.4).toFixed(2)}%`
}

/**
 * 判断这几个阶段是串行还是并行。
 * 演示时这一句很有用：它把"流程是不是真的按预期串起来"直接摆出来。
 */
const parallelism = computed(() => {
  const real = props.spans.filter((s) => !isParent(s) && s.start_ms != null)
  for (let i = 0; i < real.length; i++) {
    for (let j = i + 1; j < real.length; j++) {
      const a = real[i]!
      const b = real[j]!
      const aEnd = (a.start_ms ?? 0) + a.duration_ms
      const bEnd = (b.start_ms ?? 0) + b.duration_ms
      if ((a.start_ms ?? 0) < bEnd && (b.start_ms ?? 0) < aEnd) return '部分阶段并行'
    }
  }
  return '全部串行'
})

/** 各阶段合计，用来看"时间主要花在哪一类"。 */
const kindTotals = computed(() => {
  const acc: Record<string, number> = {}
  for (const s of props.spans) {
    if (isParent(s)) continue
    const k = kind(s.name)
    acc[k] = (acc[k] ?? 0) + s.duration_ms
  }
  return Object.entries(acc).sort((a, b) => b[1] - a[1])
})
</script>

<template>
  <div class="timeline">
    <div class="tl-head">
      <span class="section-title" style="margin: 0">执行时间线</span>
      <span class="tl-mode mono muted">{{ parallelism }}</span>
    </div>

    <!-- 时间轴刻度 -->
    <div class="tl-axis">
      <span class="tl-axis-label" />
      <div class="tl-axis-track">
        <span v-for="t in ticks" :key="t.pct" class="tl-tick" :style="{ left: `${t.pct}%` }">
          {{ t.label }}
        </span>
      </div>
    </div>

    <!-- 每个阶段一行 -->
    <ul class="tl-rows">
      <li v-for="(span, i) in rows" :key="i" class="tl-row" :class="`k-${kind(span.name)}`">
        <span class="tl-label" :title="span.name">
          <i class="tl-dot" />
          {{ KIND_LABEL[kind(span.name)] ?? span.name }}
        </span>
        <div class="tl-track">
          <div
            class="tl-bar"
            :class="{ 'tl-bar-parent': isParent(span) }"
            :style="{ left: left(span), width: width(span) }"
            :title="`${span.name} · ${span.duration_ms.toFixed(0)} ms`"
          />
          <span v-if="!isParent(span)" class="tl-ms mono" :style="{ left: left(span), width: width(span) }">
            {{ span.duration_ms.toFixed(0) }}ms
          </span>
        </div>
      </li>
    </ul>

    <!-- 时间主要花在哪一类 -->
    <div class="tl-legend">
      <span
        v-for="[k, ms] in kindTotals"
        :key="k"
        class="tl-legend-item"
        :class="`k-${k}`"
      >
        <i class="tl-dot" />
        {{ KIND_LABEL[k] ?? k }}
        <b class="mono">{{ ((ms / (totalMs || 1)) * 100).toFixed(0) }}%</b>
      </span>
    </div>

    <!-- 明细（默认收起，避免面板太长） -->
    <details class="tl-detail">
      <summary>阶段明细（{{ spans.length }} 个 span）</summary>
      <table class="tl-table mono">
        <thead>
          <tr><th>阶段</th><th>起点</th><th>耗时</th><th>属性</th></tr>
        </thead>
        <tbody>
          <tr v-for="(span, i) in rows" :key="i">
            <td>{{ span.name }}</td>
            <td>{{ span.start_ms != null ? `${span.start_ms.toFixed(0)}ms` : '—' }}</td>
            <td>{{ span.duration_ms.toFixed(0) }}ms</td>
            <td class="muted">{{ Object.keys(span.attributes || {}).length ? JSON.stringify(span.attributes) : '' }}</td>
          </tr>
        </tbody>
      </table>
    </details>
  </div>
</template>
