import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      }
    }
  },
  build: {
    // Build as IIFE (self-executing) bundle for Salesforce Static Resource
    // Salesforce loadScript() cannot handle ES modules — it needs a plain script
    outDir: 'dist',
    cssCodeSplit: false, // Bundle all CSS into a single file
    rollupOptions: {
      input: './src/main.jsx',
      output: {
        // IIFE format — self-executes when loaded via loadScript
        format: 'iife',
        // Predictable filenames directly at the root of dist/ (no assets/ subfolder)
        entryFileNames: 'sfchat.js',
        assetFileNames: 'sfchat[extname]'
      }
    }
  }
})
