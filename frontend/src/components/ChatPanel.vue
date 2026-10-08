<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import type { DisplayMessage } from '../types'

const props = defineProps<{
  messages: DisplayMessage[]
  streaming: boolean
  error: string | null
  citationWarning: string | null
}>()

const emit = defineEmits<{
  send: [text: string]
  stop: []
  reset: []
}>()

const draft = ref('')
const scroller = ref<HTMLElement | null>(null)

function submit(): void {
  if (!draft.value.trim() || props.streaming) return
  emit('send', draft.value)
  draft.value = ''
}

function onKeydown(event: KeyboardEvent): void {
  // isComposing：中文输入法选词时的回车不能当发送
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    submit()
  }
}

// 只依赖"消息条数 + 最后一条长度"，避免每个 token 都做一次深比较
watch(
  () => `${props.messages.length}:${props.messages.at(-1)?.content.length ?? 0}`,
  async () => {
    await nextTick()
    const el = scroller.value
    if (el) el.scrollTop = el.scrollHeight
  },
)
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>对话</h2>
      <button class="ghost" :disabled="streaming || messages.length === 0" @click="emit('reset')">
        清空
      </button>
    </div>

    <div ref="scroller" class="messages">
      <p v-if="messages.length === 0" class="empty">
        先问一个关于知识库的问题。<br />
        检索策略和执行过程会显示在右侧 Trace 面板。
      </p>

      <article v-for="m in messages" :key="m.id" class="msg" :class="m.role">
        <div class="role">{{ m.role === 'user' ? '我' : '模型' }}</div>
        <div class="bubble">
          <span class="text">{{ m.content }}</span>
          <span v-if="m.pending" class="caret" />
        </div>
      </article>
    </div>

    <p v-if="error" class="error">⚠ {{ error }}</p>
    <p v-if="citationWarning" class="error">引用检查：{{ citationWarning }}</p>

    <div class="composer">
      <textarea
        v-model="draft"
        rows="3"
        placeholder="输入问题，Enter 发送，Shift + Enter 换行"
        @keydown="onKeydown"
      />
      <button v-if="streaming" class="danger" @click="emit('stop')">停止</button>
      <button v-else class="primary" :disabled="!draft.trim()" @click="submit">发送</button>
    </div>
  </section>
</template>
