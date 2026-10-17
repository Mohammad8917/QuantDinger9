import { createServer } from 'vite'
import vue2 from '@vitejs/plugin-vue2'
import { fileURLToPath } from 'node:url'

// Isolated fixture server: no app authentication, backend, exchange or AI calls.
const root = fileURLToPath(new URL('../', import.meta.url))
const server = await createServer({
  configFile: false, envFile: false, root,
  plugins: [vue2()],
  optimizeDeps: { entries: ['tests/fixtures/strategy-review.html'] },
  resolve: { alias: [{ find: '@/api/strategy', replacement: fileURLToPath(new URL('./fixtures/strategy-review-api.js', import.meta.url)) }] },
  server: { host: '127.0.0.1', port: 5197, strictPort: true }
})
await server.listen()
server.printUrls()
