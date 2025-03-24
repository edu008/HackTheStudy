import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // Lade Umgebungsvariablen basierend auf dem Modus (dev/prod)
  const env = loadEnv(mode, process.cwd(), '');
  
  console.log(`Vite Modus: ${mode}`);
  console.log(`Umgebungsvariablen: VITE_API_URL=${env.VITE_API_URL}, NODE_ENV=${env.NODE_ENV}`);
  
  return {
    server: {
      host: "::",
      port: 8080,
    },
    plugins: [
      react(),
      mode === 'development' &&
      componentTagger(),
    ].filter(Boolean),
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    // Stelle sicher, dass Umgebungsvariablen korrekt eingebunden werden
    define: {
      // Dies stellt sicher, dass import.meta.env Variablen zur Build-Zeit ersetzt werden
      'import.meta.env.VITE_API_URL': JSON.stringify(env.VITE_API_URL || 'http://localhost:5000'),
      'import.meta.env.VITE_FRONTEND_URL': JSON.stringify(env.VITE_FRONTEND_URL || 'http://localhost:8080'),
    }
  };
});
