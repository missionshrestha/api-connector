// frontend/src/App.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

describe("App", () => {
  it("renders the profile list page at /profiles", () => {
    const queryClient = createTestQueryClient();
    render(
      <MemoryRouter initialEntries={["/profiles"]}>
        <QueryClientProvider client={queryClient}>
          <App />
        </QueryClientProvider>
      </MemoryRouter>
    );
    // Stub renders the page name text
    expect(screen.getByText("Connection Profiles")).toBeInTheDocument();

  });
});