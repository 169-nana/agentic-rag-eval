# 评测集人工抽检清单

语料目录：`E:\Vue\Agent\backend\corpus\raw`
共 98 条。**发布前请至少抽检 20 条**，重点看下面三项：

1. 问题是否真的只能靠 gold 片段回答（有没有引入语料外知识）；
2. 不可回答题里被替换的实体，是不是真的在语料中不存在；
3. 多跳题是否确实需要跨两个片段（只用一段就能答的，应删除）。

抽检结论请回填到 `human_labels.jsonl`，用于校准判分器。

## `sh-001` · single_hop

- **问题**：在给出的代码中，ref 函数返回的 refObject 的 value 属性被访问时会调用哪个函数？
- **标准答案**：track
- **gold 片段 1**（doc `4fd541d79b`）：get value() {
      track(refObject, 'value')
- **备注**：来源 4fd541d79b#003（---）

## `sh-002` · single_hop

- **问题**：Vue 的单文件组件的英文缩写是什么？
- **标准答案**：SFC
- **gold 片段 1**（doc `8474dd60a7`）：英文 Single-File Components，缩写为 **SFC**
- **备注**：来源 8474dd60a7#004（---）

## `sh-003` · single_hop

- **问题**：在父组件的博客文章数组中，id 为 2 的文章标题是什么？
- **标准答案**：Blogging with Vue
- **gold 片段 1**（doc `4541c80bbc`）：{ id: 2, title: 'Blogging with Vue' }
- **备注**：来源 4541c80bbc#008（组件基础 {#components-basics}）

## `sh-004` · single_hop

- **问题**：在 Vue 3.5 和 @vue/language-tools 2.1 中，由 useTemplateRef() 创建的 ref 类型可以基于什么自动推断为静态类型？
- **标准答案**：匹配的 ref attribute 所在的元素
- **gold 片段 1**（doc `e69f4bf722`）：由 `useTemplateRef()` 创建的 ref 类型可以基于匹配的 ref attribute 所在的元素**自动推断**为静态类型。
- **备注**：来源 e69f4bf722#012（TypeScript 与组合式 API {#typescript-with-composition-api}）

## `sh-005` · single_hop

- **问题**：reactive() API 不能持有哪类值类型？
- **标准答案**：原始类型
- **gold 片段 1**（doc `aa32681cc6`）：它不能持有如 `string`、`number` 或 `boolean` 这样的[原始类型](https://developer.mozilla.org/en-US/docs/Glossary/Primitive)。
- **备注**：来源 aa32681cc6#014（---）

## `sh-006` · single_hop

- **问题**：Vue 3 的数据响应式是基于什么实现的？
- **标准答案**：JavaScript Proxy
- **gold 片段 1**（doc `aa32681cc6`）：数据是基于 [JavaScript Proxy (代理)](https://developer.mozilla.org/zh-CN/docs/Web/JavaScript/Reference/Global_Objects/Proxy) 实现响应式的。
- **备注**：来源 aa32681cc6#002（---）

## `sh-007` · single_hop

- **问题**：在 h 函数中，以 on 开头并跟着大写字母的 props 会被当作什么？
- **标准答案**：事件监听器
- **gold 片段 1**（doc `018c2c19cf`）：以 `on` 开头，并跟着大写字母的 props 会被当作事件监听器。
- **备注**：来源 018c2c19cf#009（---）

## `sh-008` · single_hop

- **问题**：在 Vue 中，`<Teleport>` 接收哪个 prop 来指定传送的目标？
- **标准答案**：to
- **gold 片段 1**（doc `a7aa95dc71`）：`<Teleport>` 接收一个 `to` prop 来指定传送的目标。
- **备注**：来源 a7aa95dc71#003（Teleport {#teleport}）

## `sh-009` · single_hop

- **问题**：在插件示例中，$translate 函数接收 'greetings.hello' 字符串后，在运行时会被替换为什么值？
- **标准答案**：Bonjour!
- **gold 片段 1**（doc `38e58fc868`）：这样，我们一开始的表达式 `$translate('greetings.hello')` 就会在运行时被替换为 `Bonjour!` 了。
- **备注**：来源 38e58fc868#002（插件 {#plugins}）

## `sh-010` · single_hop

- **问题**：当子组件的根元素已有 class 或 style attribute 时，它会和从父组件继承的值发生什么？
- **标准答案**：合并
- **gold 片段 1**（doc `03c77408aa`）：如果一个子组件的根元素已经有了 `class` 或 `style` attribute，它会和从父组件上继承的值合并。
- **备注**：来源 03c77408aa#001（---）

## `sh-011` · single_hop

- **问题**：在 watchEffect() 的示例中，用于加载远程资源的 API 请求 URL 是什么？
- **标准答案**：https://jsonplaceholder.typicode.com/todos/${todoId.value}
- **gold 片段 1**（doc `e7b44fede5`）：`https://jsonplaceholder.typicode.com/todos/${todoId.value}`
- **备注**：来源 e7b44fede5#010（侦听器 {#watchers}）

## `sh-012` · single_hop

- **问题**：使用插槽时，`<FancyButton>` 仅负责渲染外层的什么元素？
- **标准答案**：<button>
- **gold 片段 1**（doc `1c74220004`）：通过使用插槽，`<FancyButton>` 仅负责渲染外层的 `<button>` (以及相应的样式)
- **备注**：来源 1c74220004#002（插槽 Slots {#slots}）

## `sh-013` · single_hop

- **问题**：在 `<SubmitButton>` 组件中，当父组件没有提供任何插槽内容时，`<slot>` 标签之间写什么内容会被作为默认内容渲染？
- **标准答案**：Submit
- **gold 片段 1**（doc `1c74220004`）：只需要将“Submit”写在 `<slot>` 标签之间来作为默认内容
- **备注**：来源 1c74220004#006（插槽 Slots {#slots}）

## `sh-014` · single_hop

- **问题**：在表单元素中引入哪个属性可以使其应用于表单中的所有 input 框？
- **标准答案**：autocomplete='on'
- **gold 片段 1**（doc `39f0535c52`）：请注意这里我们是如何在表单元素中引入 `autocomplete='on'` 的，它将应用于表单中的所有 input 框。
- **备注**：来源 39f0535c52#005（无障碍访问 {#accessibility}）

## `sh-015` · single_hop

- **问题**：在 `<script setup>` 中，`defineProps()` 宏函数支持从它的什么中推导类型？
- **标准答案**：参数
- **gold 片段 1**（doc `e69f4bf722`）：当使用 `<script setup>` 时，`defineProps()` 宏函数支持从它的参数中推导类型
- **备注**：来源 e69f4bf722#000（TypeScript 与组合式 API {#typescript-with-composition-api}）

## `sh-016` · single_hop

- **问题**：在 Vue 中，一个子组件只会在什么条件下才会更新？
- **标准答案**：其至少一个 props 改变时
- **gold 片段 1**（doc `93012c4db3`）：在 Vue 之中，一个子组件只会在其至少一个 props 改变时才会更新。
- **备注**：来源 93012c4db3#005（---）

## `sh-017` · single_hop

- **问题**：浏览核心功能和常见用户界面的示例的标题是什么？
- **标准答案**：查看示例
- **gold 片段 1**（doc `8474dd60a7`）：查看示例</p>
    <p class="next-steps-caption">浏览核心功能和常见用户界面的示例。</p>
- **备注**：来源 8474dd60a7#011（---）

## `sh-018` · single_hop

- **问题**：在关于标题的无障碍访问实践中，推荐按什么顺序嵌套标题？
- **标准答案**：按级别顺序嵌套标题
- **gold 片段 1**（doc `39f0535c52`）：按级别顺序嵌套标题：`<h1>` - `<h6>`
- **备注**：来源 39f0535c52#002（无障碍访问 {#accessibility}）

## `sh-019` · single_hop

- **问题**：当一个组件同时接收默认插槽和具名插槽时，所有位于顶级的非 <template> 节点都被隐式地视为什么？
- **标准答案**：默认插槽的内容
- **gold 片段 1**（doc `1c74220004`）：所有位于顶级的非 `<template>` 节点都被隐式地视为默认插槽的内容
- **备注**：来源 1c74220004#010（插槽 Slots {#slots}）

## `sh-020` · single_hop

- **问题**：在示例中，父组件的 myRef 是 undefined，而子组件的 model 是多少？
- **标准答案**：1
- **gold 片段 1**（doc `74bfbc4c83`）：父组件的 `myRef` 是 undefined，而子组件的 `model` 是 1
- **备注**：来源 74bfbc4c83#003（组件 v-model {#component-v-model}）

## `sh-021` · single_hop

- **问题**：Vue 通过什么方式来校验 author prop 的值是否是 Person 类的一个实例？
- **标准答案**：instanceof Person
- **gold 片段 1**（doc `59a2d61653`）：Vue 会通过 `instanceof Person` 来校验 `author` prop 的值是否是 `Person` 类的一个实例。
- **备注**：来源 59a2d61653#019（Props {#props}）

## `sh-022` · single_hop

- **问题**：Vue 提供的哪个指令是上述双向绑定操作的语法糖？
- **标准答案**：v-model
- **gold 片段 1**（doc `a20ca8b2b1`）：为了简化双向绑定，Vue 提供了一个 `v-model` 指令，它实际上是上述操作的语法糖
- **备注**：来源 a20ca8b2b1#000（表单绑定 {#form-bindings}）

## `sh-023` · single_hop

- **问题**：计算属性的 getter 应该只做什么？
- **标准答案**：只做计算而没有任何其他的副作用
- **gold 片段 1**（doc `3c10033c51`）：计算属性的 getter 应只做计算而没有任何其他的副作用
- **备注**：来源 3c10033c51#011（计算属性 {#computed-properties}）

## `sh-024` · single_hop

- **问题**：在哪个网站的演练场中可以查看组件基础示例？
- **标准答案**：play.vuejs.org
- **gold 片段 1**（doc `4541c80bbc`）：[在演练场中查看示例](https://play.vuejs.org/#eNqNVMGOmzAQ/ZURe2BXCiHbrXpwk1X31mMPvS1V5RiTWAEb2SZNhPLvHdvggLZRE6TIM/P8/N5gpk/e2nZ57HhCkrVhWrQWDLdd+1pI0bRKW/iuGg6VVg2ky9wFDp7G8g9lrIl1H80Bb5rtxfFKMcRzUA+aV3AZQKEEhWRKGgus05pL+5NuYeNwj6mTkT4VckRYujVY63GT17twC6/Fr4YjC3kp5DoPNtEgBpY3bU0txwhgXYojsJoasymSkjeqSHweK9vOWoUbXIC/Y1YpjaDH3wt39hMI6TUUSYSQAz8jArPT5Mj+nmIhC6zpAu1TZlEhmXndbBwpXH5NGL6xWrADMsyaMj1lkAzQ92E7mvYe8nCcM24xZAp
- **备注**：来源 4541c80bbc#020（组件基础 {#components-basics}）

## `sh-025` · single_hop

- **问题**：推荐的 IDE 配置是什么？
- **标准答案**：Visual Studio Code + Vue - Official 扩展
- **gold 片段 1**（doc `0a66943b47`）：推荐的 IDE 配置是 [Visual Studio Code](https://code.visualstudio.com/) + [Vue - Official 扩展]
- **备注**：来源 0a66943b47#006（---）

## `sh-026` · single_hop

- **问题**：在 Vue 中，哪个 v-model 修饰符会在输入框有 type="number" 时自动启用？
- **标准答案**：.number
- **gold 片段 1**（doc `7d0eba3120`）：`number` 修饰符会在输入框有 `type="number"` 时自动启用。
- **备注**：来源 7d0eba3120#020（---）

## `sh-027` · single_hop

- **问题**：在匿名函数式组件的代码中，FComponent.emits 里 sendMessage 的验证函数返回什么？
- **标准答案**：typeof value === 'string'
- **gold 片段 1**（doc `018c2c19cf`）：FComponent.emits = {
  sendMessage: (value) => typeof value === 'string'
}
- **备注**：来源 018c2c19cf#022（---）

## `sh-028` · single_hop

- **问题**：Vue 使用哪个浏览器原生 API 完成 HTML 内容的转义？
- **标准答案**：textContent
- **gold 片段 1**（doc `3c7d3a28ba`）：这种转义是使用 `textContent` 这样的浏览器原生 API 完成的
- **备注**：来源 3c7d3a28ba#001（安全 {#security}）

## `sh-029` · single_hop

- **问题**：Vue 团队曾通过哪个实验性功能探索改变 JavaScript 语义的方向？
- **标准答案**：响应性语法糖
- **gold 片段 1**（doc `4fd541d79b`）：Vue 团队确实曾通过一个名为[响应性语法糖](/guide/extras/reactivity-transform)的实验性功能来探索这个方向
- **备注**：来源 4fd541d79b#008（---）

## `sh-030` · single_hop

- **问题**：当 v-if 和 v-for 同时存在于一个节点上时，哪个指令的优先级更高？
- **标准答案**：v-if
- **gold 片段 1**（doc `703feff2b5`）：当它们同时存在于一个节点上时，`v-if` 比 `v-for` 的优先级更高。
- **备注**：来源 703feff2b5#007（列表渲染 {#list-rendering}）

## `sh-031` · single_hop

- **问题**：对于大于 Number.MAX_SAFE_INTEGER 的输入值，由于 JavaScript 数字精度的限制，结果可能怎么样？
- **标准答案**：可能不准确
- **gold 片段 1**（doc `5e6ba578e4`）：注意：对于大于 Number.MAX_SAFE_INTEGER (9007199254740991) 的输入值，
  // 由于 JavaScript 数字精度的限制，结果可能不准确。
  watc
- **备注**：来源 5e6ba578e4#004（<script setup>）

## `sh-032` · single_hop

- **问题**：在 3.5 版本以前，使用模板引用需要声明一个与模板引用 attribute 同名的 ref，该 ref 的值需要是什么？
- **标准答案**：数组
- **gold 片段 1**（doc `7aca863509`）：在 3.5 版本以前，`useTemplateRef()` 尚未引入，需要声明一个与模板引用 attribute 同名的 ref。该 ref 的值需要是一个数组。
- **备注**：来源 7aca863509#007（模板引用 {#template-refs}）

## `sh-033` · single_hop

- **问题**：Vue 提供的哪个接口可以用来在提供者和消费者之间同步注入值的类型？
- **标准答案**：InjectionKey
- **gold 片段 1**（doc `e69f4bf722`）：Vue 提供了一个 `InjectionKey` 接口，它是一个继承自 `Symbol` 的泛型类型，可以用来在提供者和消费者之间同步注入值的类型
- **备注**：来源 e69f4bf722#010（TypeScript 与组合式 API {#typescript-with-composition-api}）

## `sh-034` · single_hop

- **问题**：在组件间过渡中，`<Transition>` 的 `mode` 属性可以设置为什么值来实现先出后进？
- **标准答案**：out-in
- **gold 片段 1**（doc `fdba4e4a51`）：<Transition name="fade" mode="out-in">
- **备注**：来源 fdba4e4a51#026（<script setup>）

## `sh-035` · single_hop

- **问题**：在知识库文本中，哪个组件被举例说明包含多个插槽出口？
- **标准答案**：BaseLayout
- **gold 片段 1**（doc `1c74220004`）：在一个 `<BaseLayout>` 组件中，有如下模板：
- **备注**：来源 1c74220004#007（插槽 Slots {#slots}）

## `sh-036` · single_hop

- **问题**：从哪个版本开始，WebStorm 和 Vue 插件内置了对 Vue 语言服务器的支持？
- **标准答案**：2023.2 版
- **gold 片段 1**（doc `8093b28e32`）：从 2023.2 版开始，WebStorm 和 Vue 插件内置了对 Vue 语言服务器的支持。
- **备注**：来源 8093b28e32#002（---）

## `sh-037` · single_hop

- **问题**：当自定义指令应用到一个多根组件时，会发生什么？
- **标准答案**：指令将会被忽略且抛出一个警告
- **gold 片段 1**（doc `fef67863ad`）：当应用到一个多根组件时，指令将会被忽略且抛出一个警告。
- **备注**：来源 fef67863ad#007（自定义指令 {#custom-directives}）

## `sh-038` · single_hop

- **问题**：在给出的代码片段中，当 fetch 请求失败时，this.answer 被设置为什么？
- **标准答案**：'Error! Could not reach the API. ' + error
- **gold 片段 1**（doc `e7b44fede5`）：this.answer = 'Error! Could not reach the API. ' + error
- **备注**：来源 e7b44fede5#001（侦听器 {#watchers}）

## `sh-039` · single_hop

- **问题**：在 server.js 中，为了在浏览器中加载客户端文件，需要添加哪一行代码来托管客户端文件？
- **标准答案**：server.use(express.static('.'))
- **gold 片段 1**（doc `2d9d0680a7`）：在 `server.js` 中添加 `server.use(express.static('.'))` 来托管客户端文件。
- **备注**：来源 2d9d0680a7#007（---）

## `sh-040` · single_hop

- **问题**：在无障碍访问中，添加哪个属性可以使内容对屏幕阅读器隐藏，但对其他可视用户仍然可见？
- **标准答案**：aria-hidden="true"
- **gold 片段 1**（doc `39f0535c52`）：添加 `aria-hidden="true"` 在无障碍访问时被隐藏，但对其他可视用户仍然是可见的。
- **备注**：来源 39f0535c52#014（无障碍访问 {#accessibility}）

## `sh-041` · single_hop

- **问题**：Vue 与 Laravel 搭配使用时，Laravel 自带了什么官方插件？
- **标准答案**：Vite 插件
- **gold 片段 1**（doc `651df88968`）：该框架自带了官方的 [Vite 插件](https://laravel.com/docs/vite)
- **备注**：来源 651df88968#010（<script setup>）

## `sh-042` · single_hop

- **问题**：在示例中，计算属性 ref 的名称是什么？
- **标准答案**：publishedBooksMessage
- **gold 片段 1**（doc `3c10033c51`）：const publishedBooksMessage = computed(() => {
- **备注**：来源 3c10033c51#004（计算属性 {#computed-properties}）

## `sh-043` · single_hop

- **问题**：在 event.js 中，useEventListener 组合式函数在组件卸载时调用什么来移除事件监听器？
- **标准答案**：onUnmounted
- **gold 片段 1**（doc `7d5b818cfb`）：onUnmounted(() => target.removeEventListener(event, callback))
- **备注**：来源 7d5b818cfb#004（组合式函数 {#composables}）

## `sh-044` · single_hop

- **问题**：在演练场中尝试一下的链接指向哪个网站？
- **标准答案**：play.vuejs.org
- **gold 片段 1**（doc `fdba4e4a51`）：[在演练场中尝试一下](https://play.vuejs.org/#eNp9U8tu2zAQ/JUFTwkSyw6aXlQ7QB85pIe2aHPUhZHWDhOKJMiVYtfwv3dJSpbbBgEMWJydndkdUXvx0bmi71CUYhlqrxzdVAa3znqCBtey0wT7ygA0kuTZeX4G8EidN+MJoLadoRKuLkdAGULfS12C6bSGDB/i3yFx2tiAzaRIjyoUYxesICDdDaczZq1uJrNETY4XFx8G5Uu4WiwW55PBA66txy8YyNvdZFNrlP4o/Jdpbq4M/5bzYxZ8IGydloR8Alg2qmcVGcKqEi9eOoe+EqnExXsvTVCkrBkQxoKTBspn3HFDmprp+32ODA4H9mLCKDD/R2E5Zz9+Ws5PpuBjoJ1GCLV12DASJdKGa2toFtRvLOHaY8vx8DrFMGdiOJvlS48sp3rMHGb1M4xRzGQdYU6REY6rxwHJGdJxwBKsk7WiHSyK9wFQhqh14gDyIVjd0f8Wa2/bUwOyWXwQLGGRWzicuChvKC4F8bpmrTbFU7CGL2zqiJm2Tmn03100DZUox5ddCam1ffmaMPJd3Cnj9SPWz6/gT2EbsUr88Bj4VmAljjWSfoP88mL59tc33PLzsdjaptPMfqP4E1MYPGOmfepMw2Of8NK0d238+JTZ3IfbLSFnPSwVB53udyX4q/38xurTuO+K6/Fqi8MffqhR/A==)
- **备注**：来源 fdba4e4a51#031（<script setup>）

## `sh-045` · single_hop

- **问题**：在 Vue 模板中，当 ref 作为文本插值的最终计算值时，`{{ object.id }}` 会渲染成什么？
- **标准答案**：1
- **gold 片段 1**（doc `aa32681cc6`）：如果 ref 是文本插值的最终计算值 (即 <code v-pre>{{ }}</code> 标签)，那么它将被解包，因此以下内容将渲染为 `1`
- **备注**：来源 aa32681cc6#017（---）

## `sh-046` · single_hop

- **问题**：在 Vue 中，若要将一个对象的所有属性都当作 props 传入，应该使用什么写法？
- **标准答案**：没有参数的 v-bind
- **gold 片段 1**（doc `59a2d61653`）：你可以使用[没有参数的 `v-bind`](/guide/essentials/template-syntax#dynamically-binding-multiple-attributes)，即只使用 `v-bind` 而非 `:prop-name`
- **备注**：来源 59a2d61653#008（Props {#props}）

## `sh-047` · single_hop

- **问题**：在示例代码中，当加载状态为真时，输入框被设置为什么属性？
- **标准答案**：disabled
- **gold 片段 1**（doc `e7b44fede5`）：<input v-model="question" :disabled="loading" />
- **备注**：来源 e7b44fede5#004（侦听器 {#watchers}）

## `sh-048` · single_hop

- **问题**：在 SSR 环境下，应用模块通常只在什么时候初始化一次？
- **标准答案**：服务器启动时
- **gold 片段 1**（doc `2d9d0680a7`）：在 SSR 环境下，应用模块通常只在服务器启动时初始化一次。
- **备注**：来源 2d9d0680a7#011（---）

## `sh-049` · single_hop

- **问题**：副作用订阅被存储在什么数据结构中？
- **标准答案**：WeakMap<target, Map<key, Set<effect>>>
- **gold 片段 1**（doc `4fd541d79b`）：副作用订阅将被存储在一个全局的 `WeakMap<target, Map<key, Set<effect>>>` 数据结构中。
- **备注**：来源 4fd541d79b#004（---）

## `sh-050` · single_hop

- **问题**：Vue 提供的用于创建响应式副作用的 API 是什么？
- **标准答案**：watchEffect()
- **gold 片段 1**（doc `4fd541d79b`）：Vue 提供了一个 API 来让你创建响应式副作用 [`watchEffect()`](/api/reactivity-core#watcheffect)。
- **备注**：来源 4fd541d79b#005（---）

## `mh-001` · multi_hop

- **问题**：Vue 中与 ref 对应的编译时宏命令是什么？在使用 withDefaults 时，默认值的可变引用类型应该如何处理？
- **标准答案**：$ref；应在函数中进行包装
- **gold 片段 1**（doc `77e0e882dd`）：每一个会返回 ref 的响应式 API 都有一个相对应的、以 `$` 为前缀的宏函数。包括以下这些 API：
- **gold 片段 2**（doc `e69f4bf722`）：在使用 `withDefaults` 时，默认值的可变引用类型 (如数组或对象) 应该在函数中进行包装
- **备注**：关联实体「vue」，来源 77e0e882dd#001 + e69f4bf722#003

## `mh-002` · multi_hop

- **问题**：Vue 渲染函数中，如果要在页面上渲染多个重复的元素，可以用什么函数来做这件事？这个函数在 Vue 与 Web Components 的集成中，通过哪个配置选项可以让 Vue 跳过对自定义元素的组件解析？
- **标准答案**：工厂函数；compilerOptions.isCustomElement
- **gold 片段 1**（doc `018c2c19cf`）：你可以使用一个工厂函数来做这件事
- **gold 片段 2**（doc `f94b9a27d5`）：compilerOptions.isCustomElement
- **备注**：关联实体「vue」，来源 018c2c19cf#004 + f94b9a27d5#000

## `mh-003` · multi_hop

- **问题**：在解释响应式原理时，ref 函数内部通过 get 和 set 访问器来追踪哪个属性？这个属性在组合式 API 的模板中通常如何被使用？
- **标准答案**：value；在模板中直接使用 count 而无需 .value
- **gold 片段 1**（doc `4fd541d79b`）：get value() {
- **gold 片段 2**（doc `8474dd60a7`）：const count = ref(0)
- **备注**：关联实体「ref」，来源 4fd541d79b#003 + 8474dd60a7#005

## `mh-004` · multi_hop

- **问题**：在 Vue 的计数器组件示例中，用于驱动视图的响应式状态是通过哪个 API 创建的？该 API 在内部实现中通过什么机制来追踪依赖？
- **标准答案**：ref；通过 track() 追踪依赖
- **gold 片段 1**（doc `568a64818e`）：const count = ref(0)
- **gold 片段 2**（doc `aa32681cc6`）：get value() {
    track()
    return this._value
  }
- **备注**：关联实体「count」，来源 568a64818e#000 + aa32681cc6#007

## `mh-005` · multi_hop

- **问题**：在 `<script setup>` 中，如果要在 `await` 操作之后仍能调用组合式函数，编译器会自动恢复什么？而使用 `defineExpose` 时，必须在什么操作之前调用才能保证暴露的属性和方法可访问？
- **标准答案**：当前活跃的组件实例；任何 await 操作之前
- **gold 片段 1**（doc `7aca863509`）：defineExpose 必须在任何 await 操作之前调用
- **gold 片段 2**（doc `7d5b818cfb`）：编译器会在异步操作之后自动为你恢复当前的组件实例
- **备注**：关联实体「scriptsetup」，来源 7aca863509#005 + 7d5b818cfb#013

## `mh-006` · multi_hop

- **问题**：在单元测试中，用于演示独立函数测试的 increment 函数，其默认的 max 参数值是多少？在 Vue 性能分析中，哪个配置选项可以开启 Vue 特有的性能标记？
- **标准答案**：10；app.config.performance
- **gold 片段 1**（doc `417e4ddb83`）：export function increment(current, max = 10) {
- **gold 片段 2**（doc `93012c4db3`）：`app.config.performance`
- **备注**：关联实体「vue」，来源 417e4ddb83#002 + 93012c4db3#001

## `mh-007` · multi_hop

- **问题**：在浏览器中通过 import map 引入 Vue 时，示例里从哪个 URL 加载 vue 的 ESM 浏览器构建？该构建所属的 Vue 版本在定义异步组件时支持哪种在媒体查询匹配时进行激活的激活策略？
- **标准答案**：hydrateOnMediaQuery
- **gold 片段 1**（doc `0a66943b47`）："vue": "https://unpkg.com/vue@3/dist/vue.esm-browser.js"
- **gold 片段 2**（doc `3cce7eadaa`）：hydrateOnMediaQuery('(max-width:500px)')
- **备注**：关联实体「vue」，来源 0a66943b47#012 + 3cce7eadaa#005

## `mh-008` · multi_hop

- **问题**：在选项式 API 中，用于声明响应式状态的组件选项，其返回值中的属性在模板中通过什么语法渲染？该语法在 provide 函数中对应的第一个参数被称为什么？
- **标准答案**：双花括号语法；注入名
- **gold 片段 1**（doc `257b8a1855`）：下面展示了我们如何使用双花括号法，根据 `message` 的值来渲染动态文本
- **gold 片段 2**（doc `e94f52e802`）：第一个参数被称为**注入名**
- **备注**：关联实体「message」，来源 257b8a1855#002 + e94f52e802#001

## `mh-009` · multi_hop

- **问题**：在 Vue 中，用于生成唯一 ID 以关联表单控件与可见文本的 API 是什么？该 API 在 Chrome 开发者工具的性能面板中开启 Vue 特有性能标记的配置项是什么？
- **标准答案**：useId；app.config.performance
- **gold 片段 1**（doc `39f0535c52`）：useId()
- **gold 片段 2**（doc `93012c4db3`）：app.config.performance
- **备注**：关联实体「vue」，来源 39f0535c52#008 + 93012c4db3#001

## `mh-010` · multi_hop

- **问题**：Vue 插件可以通过哪种应用实例方法向整个应用注入资源？该应用实例方法在基于侦听器的动画示例中与哪个库配合使用？
- **标准答案**：app.provide，gsap
- **gold 片段 1**（doc `38e58fc868`）：通过 [`app.provide()`](/api/application#app-provide) 使一个资源[可被注入](/guide/components/provide-inject)进整个应用。
- **gold 片段 2**（doc `5e6ba578e4`）：import gsap from 'gsap'
- **备注**：关联实体「vue」，来源 38e58fc868#000 + 5e6ba578e4#003

## `mh-011` · multi_hop

- **问题**：Vue 中用于校验 prop 类型是否匹配的自定义类，其校验机制依赖哪个 JavaScript 运算符？该运算符在编译时宏命令 $ref 生成的代码中，用于访问响应式变量的哪个属性？
- **标准答案**：instanceof；.value
- **gold 片段 1**（doc `59a2d61653`）：Vue 会通过 `instanceof Person` 来校验 `author` prop 的值是否是 `Person` 类的一个实例。
- **gold 片段 2**（doc `77e0e882dd`）：let count = ref(0)

console.log(count.value)
- **备注**：关联实体「vue」，来源 59a2d61653#018 + 77e0e882dd#001

## `mh-012` · multi_hop

- **问题**：Vue 的 import map 示例中，浏览器从哪个 URL 加载 vue 模块？该模块的响应性 API 与 Solid 和 Angular 基于 getter 的 API 相比，在访问值时有什么不同？
- **标准答案**：https://unpkg.com/vue@3/dist/vue.esm-browser.js；没有 ref 解包，总是需要通过 () 来访问值
- **gold 片段 1**（doc `0a66943b47`）："vue": "https://unpkg.com/vue@3/dist/vue.esm-browser.js"
- **gold 片段 2**（doc `4fd541d79b`）：没有 ref 解包：总是需要通过 `()` 来访问值。
- **备注**：关联实体「vue」，来源 0a66943b47#012 + 4fd541d79b#022

## `mh-013` · multi_hop

- **问题**：在组合式 API 中，当调用 onMounted 时，Vue 会自动将回调函数注册到哪里？注册后，可以通过什么方式访问模板中的 <p> 元素并对其执行 DOM 操作？
- **标准答案**：当前正被初始化的组件实例上；pElementRef.value
- **gold 片段 1**（doc `32de213786`）：当调用 `onMounted` 时，Vue 会自动将回调函数注册到当前正被初始化的组件实例上。
- **gold 片段 2**（doc `62f0ad74a3`）：n-api">`pElementRef.value`</span> 访问 `<p>`，并
- **备注**：关联实体「onmounted」，来源 32de213786#001 + 62f0ad74a3#002

## `mh-014` · multi_hop

- **问题**：在 Vue 组件中，若想将原始信号作为组件的参数传递下去，需要采用哪种基于 getter 的 API 风格？这种风格下，当使用 withDefaults 为可变引用类型设置默认值时，应该如何处理以避免意外修改？
- **标准答案**：Solid 和 Angular 的 getter 风格；在函数中包装
- **gold 片段 1**（doc `4fd541d79b`）：这也意味着你可以将原始信号作为组件的参数传递下去。
- **gold 片段 2**（doc `e69f4bf722`）：默认值的可变引用类型 (如数组或对象) 应该在函数中进行包装
- **备注**：关联实体「vue」，来源 4fd541d79b#022 + e69f4bf722#003

## `mh-015` · multi_hop

- **问题**：在全局注册 v-highlight 指令时，应用实例是通过哪个方法完成注册的？而在组合式 API 的 <script setup> 中，该指令对应的变量名是什么？
- **标准答案**：app.directive；vHighlight
- **gold 片段 1**（doc `e69f4bf722`）：app.directive('highlight', highlight)
- **gold 片段 2**（doc `fef67863ad`）：const vHighlight = {
- **备注**：关联实体「highlight」，来源 e69f4bf722#016 + fef67863ad#001

## `mh-016` · multi_hop

- **问题**：在 Vue 中，当 prop 的 type 被指定为自定义类 Person 时，Vue 会通过什么机制来校验传入的值？而要在单文件组件中启用这种类型检查，需要在 script 标签上添加什么属性？
- **标准答案**：instanceof；lang="ts"
- **gold 片段 1**（doc `59a2d61653`）：Vue 会通过 `instanceof Person` 来校验 `author` prop 的值是否是 `Person` 类的一个实例。
- **gold 片段 2**（doc `8093b28e32`）：需要在 `<script>` 标签上加上 `lang="ts"` 的 attribute
- **备注**：关联实体「vue」，来源 59a2d61653#018 + 8093b28e32#007

## `mh-017` · multi_hop

- **问题**：在无需构建步骤的情况下，通过 CDN 和原生 ES 模块使用 Vue 时，从 unpkg 导入的模块文件叫什么名字？该文件在单文件组件示例中又是如何被导入的？
- **标准答案**：vue.esm-browser.js；import { ref } from 'vue'
- **gold 片段 1**（doc `0a66943b47`）：import { createApp, ref } from 'https://unpkg.com/vue@3/dist/vue.esm-browser.js'
- **gold 片段 2**（doc `8474dd60a7`）：import { ref } from 'vue'
- **备注**：关联实体「ref」，来源 0a66943b47#010 + 8474dd60a7#005

## `mh-018` · multi_hop

- **问题**：Vue 团队曾通过哪个实验性功能探索改变 JavaScript 语义的方向，而该功能的作者也是哪个构建工具的作者？
- **标准答案**：响应性语法糖；Vite
- **gold 片段 1**（doc `4fd541d79b`）：Vue 团队确实曾通过一个名为[响应性语法糖](/guide/extras/reactivity-transform)的实验性功能来探索这个方向
- **gold 片段 2**（doc `651df88968`）：[Vite](https://cn.vite.dev/) 是一个轻量级的、速度极快的构建工具，对 Vue 单文件组件提供第一优先级支持。作者是尤雨溪，同时也是 Vue 的作者！
- **备注**：关联实体「vue」，来源 4fd541d79b#008 + 651df88968#000

## `mh-019` · multi_hop

- **问题**：在 Vue 中，如果使用基于类型的 prop 声明 defineProps<{ msg: string }>，它会被编译成什么？这种声明方式通常写在哪种文件格式中？
- **标准答案**：{ msg: { type: String, required: true }}，单文件组件（*.vue 文件）
- **gold 片段 1**（doc `59a2d61653`）：`defineProps<{ msg: string }>` 会被编译为 `{ msg: { type: String, required: true }}`
- **gold 片段 2**（doc `8474dd60a7`）：它被称为**单文件组件** (也被称为 `*.vue` 文件
- **备注**：关联实体「vue」，来源 59a2d61653#017 + 8474dd60a7#004

## `mh-020` · multi_hop

- **问题**：通过 CDN 使用 Vue 时，全局构建版本把顶层 API 暴露在哪个全局对象上？该对象在搭配 TypeScript 使用组合式 API 时，defineProps() 宏函数支持从它的参数中推导类型，这种声明方式被称为什么？
- **标准答案**：Vue 对象；运行时声明
- **gold 片段 1**（doc `0a66943b47`）：该版本的所有顶层 API 都以属性的形式暴露在了全局的 `Vue` 对象上
- **gold 片段 2**（doc `e69f4bf722`）：这被称之为“运行时声明”，因为传递给 `defineProps()` 的参数会作为运行时的 `props` 选项使用。
- **备注**：关联实体「vue」，来源 0a66943b47#008 + e69f4bf722#000

## `mh-021` · multi_hop

- **问题**：在 Vue 中遍历对象属性时，第三个参数表示位置索引的写法是什么？这种写法所在的模板结构在 SSR 激活时，只有哪些节点需要被遍历？
- **标准答案**：v-for="(value, key, index) in myObject"；区块节点和其动态子节点
- **gold 片段 1**（doc `703feff2b5`）：<li v-for="(value, key, index) in myObject">
- **gold 片段 2**（doc `aa8e8b344b`）：在激活时只有区块节点和其动态子节点需要被遍历
- **备注**：关联实体「vfor」，来源 703feff2b5#004 + aa8e8b344b#008

## `mh-022` · multi_hop

- **问题**：在 Vue 中，当模板表达式变得臃肿难以维护时，官方推荐使用哪种属性来简化逻辑？这种属性所属的模板语法底层会被编译成什么？
- **标准答案**：计算属性；高度优化的 JavaScript 代码
- **gold 片段 1**（doc `3c10033c51`）：模板中的表达式虽然方便，但也只能用来做简单的操作。如果在模板中写太多逻辑，会让模板变得臃肿，难以维护。
- **gold 片段 2**（doc `ba7321ade5`）：Vue 会将模板编译成高度优化的 JavaScript 代码。
- **备注**：关联实体「vue」，来源 3c10033c51#000 + ba7321ade5#000

## `mh-023` · multi_hop

- **问题**：在讲解作用域插槽时，子组件通过什么方式将 props 传给插槽函数？而自定义指令在组件上使用时，会始终应用于组件的哪个部分？
- **标准答案**：以函数形式传递；根节点
- **gold 片段 1**（doc `1c74220004`）：子组件会将相应的 props 作为参数传给它
- **gold 片段 2**（doc `fef67863ad`）：它会始终应用于组件的根节点
- **备注**：关联实体「mycomponent」，来源 1c74220004#018 + fef67863ad#007

## `mh-024` · multi_hop

- **问题**：计算属性默认是只读的，若想创建可写计算属性，需要同时提供哪两个选项？在大型应用中，为了避免注入名冲突，官方建议使用什么作为注入名？
- **标准答案**：getter 和 setter；Symbol
- **gold 片段 1**（doc `3c10033c51`）：你可以通过同时提供 getter 和 setter 来创建
- **gold 片段 2**（doc `e94f52e802`）：者使用的组件库，建议最好使用 [Symbol](https
- **备注**：关联实体「computed」，来源 3c10033c51#007 + e94f52e802#010

## `mh-025` · multi_hop

- **问题**：reactive() 的局限性中，哪种情况会导致响应性连接丢失，而 ref() 通过什么方式避免了这个问题？
- **标准答案**：解构原始类型属性时；ref() 用对象包装值
- **gold 片段 1**（doc `4fd541d79b`）：当你将一个响应式对象的属性赋值或解构到一个本地变量时，访问或赋值该变量是非响应式的
- **gold 片段 2**（doc `aa32681cc6`）：对解构操作不友好
- **备注**：关联实体「reactive」，来源 4fd541d79b#003 + aa32681cc6#014

## `mh-026` · multi_hop

- **问题**：在 Vue 中为组件 props 标注复杂类型时，如果使用运行时声明，需要借助哪个工具类型？该工具类型在将 Vue 组件转为自定义元素类时，导入的 API 名称是什么？
- **标准答案**：PropType；defineCustomElement
- **gold 片段 1**（doc `e69f4bf722`）：对于运行时声明，我们可以使用 `PropType` 工具类型
- **gold 片段 2**（doc `f94b9a27d5`）：import { defineCustomElement } from 'vue'
- **备注**：关联实体「typescript」，来源 e69f4bf722#004 + f94b9a27d5#012

## `mh-027` · multi_hop

- **问题**：Vue 官方项目脚手架工具叫什么名字？该工具的官方文档中强烈建议不要在 Vue 中渲染哪个 HTML 标签？
- **标准答案**：create-vue；script
- **gold 片段 1**（doc `0a66943b47`）：它是 Vue 官方的项目脚手架工具
- **gold 片段 2**（doc `3c7d3a28ba`）：我们强烈建议任何时候都不要在 Vue 中渲染 `<script>`
- **备注**：关联实体「vue」，来源 0a66943b47#002 + 3c7d3a28ba#005

## `mh-028` · multi_hop

- **问题**：Vue 中用于声明响应式状态的 API 创建的对象是什么类型，而处理事件时若想避免在方法内手动调用 event.preventDefault()，可以使用哪种指令修饰符？
- **标准答案**：Proxy；.prevent
- **gold 片段 1**（doc `257b8a1855`）：由 `reactive()` 创建的对象都是 JavaScript [Proxy]
- **gold 片段 2**（doc `4e04ce49c7`）：Vue 为 `v-on` 提供了**事件修饰符**
- **备注**：关联实体「vue」，来源 257b8a1855#000 + 4e04ce49c7#007

## `mh-029` · multi_hop

- **问题**：Vue 官方项目脚手架工具在创建项目时会提示添加哪些可选功能？其中用于声明响应式状态的 API 是哪个？
- **标准答案**：TypeScript 和测试支持；reactive()
- **gold 片段 1**（doc `0a66943b47`）：你将会看到一些诸如 TypeScript 和测试支持之类的可选功能提示
- **gold 片段 2**（doc `257b8a1855`）：我们可以使用 Vue 的 `reactive()` API 来声明响应式状态
- **备注**：关联实体「vue」，来源 0a66943b47#002 + 257b8a1855#000

## `mh-030` · multi_hop

- **问题**：Vue 官方项目脚手架工具 create-vue 是由哪个团队开发的？该团队开发的、专为基于 Vite 的应用设计的测试运行器叫什么？
- **标准答案**：Vitest
- **gold 片段 1**（doc `0a66943b47`）：它是 Vue 官方的项目脚手架工具
- **gold 片段 2**（doc `651df88968`）：由 Vue / Vite 团队成员开发
- **备注**：关联实体「vue」，来源 0a66943b47#002 + 651df88968#006

## `un-001` · unanswerable

- **问题**：在 Vue 中，哪个 v-model 修饰符会在输入框有 type="decimal" 时自动启用？
- **标准答案**：（不可回答）
- **备注**：由 单跳题 扰动而来，替换实体「decimal」（语料中不存在）

## `un-002` · unanswerable

- **问题**：浏览高级功能和常见用户界面的示例的标题是什么？
- **标准答案**：（不可回答）
- **备注**：由 单跳题 扰动而来，替换实体「高级功能」（语料中不存在）

## `un-003` · unanswerable

- **问题**：使用插槽时，`<GlamourButton>` 仅负责渲染外层的什么元素？
- **标准答案**：（不可回答）
- **备注**：由 单跳题 扰动而来，替换实体「GlamourButton」（语料中不存在）

## `un-004` · unanswerable

- **问题**：lumina-vue 最后发布的版本适配于哪个 Vue 版本？
- **标准答案**：（不可回答）
- **备注**：由 单跳题 扰动而来，替换实体「lumina-vue」（语料中不存在）

## `un-005` · unanswerable

- **问题**：在匿名函数式组件的代码中，FComponent.emits 里 updateStatus 的验证函数返回什么？
- **标准答案**：（不可回答）
- **备注**：由 单跳题 扰动而来，替换实体「updateStatus」（语料中不存在）

## `un-006` · unanswerable

- **问题**：Vue 与 Django 搭配使用时，Django 自带了什么官方插件？
- **标准答案**：（不可回答）
- **备注**：由 单跳题 扰动而来，替换实体「Django」（语料中不存在）

## `un-007` · unanswerable

- **问题**：在插件示例中，$translate 函数接收 'welcome.goodbye' 字符串后，在运行时会被替换为什么值？
- **标准答案**：（不可回答）
- **备注**：由 单跳题 扰动而来，替换实体「welcome.goodbye」（语料中不存在）

## `un-008` · unanswerable

- **问题**：如果 hasWarning 变为 true，class 列表会变成什么？
- **标准答案**：（不可回答）
- **备注**：由 单跳题 扰动而来，替换实体「hasWarning」（语料中不存在）

## `un-009` · unanswerable

- **问题**：Svelte 5 的数据响应式是基于什么实现的？
- **标准答案**：（不可回答）
- **备注**：由 单跳题 扰动而来，替换实体「Svelte 5」（语料中不存在）

## `un-010` · unanswerable

- **问题**：在 Vue 中，`<Portal>` 接收哪个 prop 来指定传送的目标？
- **标准答案**：（不可回答）
- **备注**：由 sh-008 扰动而来，替换实体「Portal」（语料中不存在）

## `un-011` · unanswerable

- **问题**：在示例中，父组件的 myRef 是 undefined，而子组件的 zephyr 是多少？
- **标准答案**：（不可回答）
- **备注**：由 sh-020 扰动而来，替换实体「zephyr」（语料中不存在）

## `un-012` · unanswerable

- **问题**：在 Nexa 3.5 和 @nexa/language-tools 2.1 中，由 useViewRef() 创建的 ref 类型可以基于什么自动推断为静态类型？
- **标准答案**：（不可回答）
- **备注**：由 sh-004 扰动而来，替换实体「Nexa 3.5、@nexa/language-tools 2.1、useViewRef()」（语料中不存在）

## `un-013` · unanswerable

- **问题**：在匿名函数式组件的代码中，FComponent.emits 里 dispatchNotice 的验证函数返回什么？
- **标准答案**：（不可回答）
- **备注**：由 sh-027 扰动而来，替换实体「dispatchNotice」（语料中不存在）

## `un-014` · unanswerable

- **问题**：响应式引用 ref 的 getter 应该只做什么？
- **标准答案**：（不可回答）
- **备注**：由 sh-023 扰动而来，替换实体「响应式引用 ref」（语料中不存在）

## `un-015` · unanswerable

- **问题**：对于大于 Number.MAX_SAFE_LIMIT 的输入值，由于 JavaScript 数字精度的限制，结果可能怎么样？
- **标准答案**：（不可回答）
- **备注**：由 sh-031 扰动而来，替换实体「Number.MAX_SAFE_LIMIT」（语料中不存在）

## `un-016` · unanswerable

- **问题**：当一个组件同时接收默认插槽和具名插槽时，所有位于顶级的非 <slot-frame> 节点都被隐式地视为什么？
- **标准答案**：（不可回答）
- **备注**：由 sh-019 扰动而来，替换实体「slot-frame」（语料中不存在）

## `un-017` · unanswerable

- **问题**：在插件示例中，$localize 函数接收 'salutations.bonjour' 字符串后，在运行时会被替换为什么值？
- **标准答案**：（不可回答）
- **备注**：由 sh-009 扰动而来，替换实体「$localize 和 'salutations.bonjour'」（语料中不存在）

## `un-018` · unanswerable

- **问题**：在 NexaFrame 中，一个子组件只会在什么条件下才会更新？
- **标准答案**：（不可回答）
- **备注**：由 sh-016 扰动而来，替换实体「NexaFrame」（语料中不存在）
