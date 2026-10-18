import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { AppCrashed, ErrorBoundary } from "./ErrorBoundary";
import "./styles.css";
import { applyCssPalette } from "./palette";

applyCssPalette();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary fallback={<AppCrashed />}>
      <App />
    </ErrorBoundary>
  </StrictMode>,
);
