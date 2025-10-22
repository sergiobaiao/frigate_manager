import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const createRequestLoggingPlugin = () => ({
  name: 'frigate-manager-request-logger',
  configureServer(server: any) {
    attachRequestLogger(server, 'dev');
  },
  configurePreviewServer(server: any) {
    attachRequestLogger(server, 'preview');
  }
});

const attachRequestLogger = (server: any, label: string) => {
  server.middlewares.use((req: any, res: any, next: () => void) => {
    const start = Date.now();
    const method = req?.method ?? 'UNKNOWN';
    const url = req?.url ?? '';
    if (typeof res?.on === 'function') {
      res.on('finish', () => {
        const duration = Date.now() - start;
        const status = res?.statusCode ?? 0;
        console.log(`[frontend:${label}] ${method} ${url} -> ${status} (${duration}ms)`);
      });
    }
    next();
  });
};

export default defineConfig({
  plugins: [react(), createRequestLoggingPlugin()],
  server: {
    port: 5173,
    host: '0.0.0.0'
  },
  preview: {
    port: 4173,
    host: '0.0.0.0'
  }
});
