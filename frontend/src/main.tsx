// frontend/src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,         // Retry failed queries once before surfacing an error
      staleTime: 30_000, // 30s — reduces redundant refetches on tab focus
    },
    mutations: {
      retry: 0, // Mutations do NOT retry — silent duplicate form submission is a defect
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>
);