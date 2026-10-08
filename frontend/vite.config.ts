import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    // 默认前端直连 http://127.0.0.1:8000（后端已开 CORS），不走代理，
    // 避免反代缓冲破坏 SSE 的流式效果。
    // 如果你想改用同源代理，取消下面的注释并把 VITE_API_BASE 设为空字符串：
    // proxy: {
    //   '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    // },
  },
})
