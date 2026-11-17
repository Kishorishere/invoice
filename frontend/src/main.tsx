import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "sonner";

import App from "./App";
import { AuthProvider } from "./lib/auth";
import { InvoicesProvider } from "./lib/invoicesContext";
import { LimitsProvider } from "./lib/limitsContext";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <LimitsProvider>
          <InvoicesProvider>
            <App />
            <Toaster
              position="bottom-right"
              toastOptions={{
                className:
                  "!bg-card !text-foreground !border !border-border !shadow-soft !rounded-xl",
              }}
            />
          </InvoicesProvider>
        </LimitsProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
