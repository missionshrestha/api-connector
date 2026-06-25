// frontend/src/App.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderWithRouter(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <QueryClientProvider client={createTestQueryClient()}>
        <App />
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("App routing", () => {
  it("renders profile list at /profiles", () => {
    renderWithRouter("/profiles");
    expect(screen.getByText("Connection Profiles")).toBeInTheDocument();
  });

  it("renders endpoint list page at /profiles/1/endpoints without crash", () => {
    renderWithRouter("/profiles/1/endpoints");
    expect(screen.getByText("Endpoints")).toBeInTheDocument();
  });

  it("renders endpoint form at /profiles/1/endpoints/new without crash", () => {
    renderWithRouter("/profiles/1/endpoints/new");
    expect(screen.getByText("New Endpoint")).toBeInTheDocument();
  });

  it("renders schema explorer page without crash", () => {
    renderWithRouter("/profiles/1/endpoints/1/schema");
    expect(document.body).toBeTruthy();
  });

  it("renders data preview page heading without crash", () => {
    renderWithRouter("/profiles/1/endpoints/1/preview");
    expect(screen.getByRole("heading", { name: "Data Preview" })).toBeInTheDocument();
  });

});