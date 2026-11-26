import "./styles.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import { AppStateProvider } from "./state/AppState";

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("Missing #root element in index.html.");

createRoot(rootElement).render(
  <StrictMode>
    <BrowserRouter>
      <AppStateProvider>
        <App />
      </AppStateProvider>
    </BrowserRouter>
  </StrictMode>,
);
