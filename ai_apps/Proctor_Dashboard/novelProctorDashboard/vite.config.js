import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  build: {
    outDir: '../../public/novel-proctor-dashboard',
    emptyOutDir: true
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
  }
});
