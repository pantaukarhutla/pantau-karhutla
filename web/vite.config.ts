import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        // The map library changes rarely: its own chunk stays cached across app updates.
        manualChunks: { maplibre: ["maplibre-gl"], react: ["react", "react-dom"] },
      },
    },
  },
});
