// frontend/src/shared/components/Layout.tsx
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Cable } from "lucide-react";

interface LayoutProps {
  children: ReactNode;
}

/**
 * App shell: a slim, sticky, translucent header over the page content.
 * Pages keep their own `container` wrappers, so this only provides the
 * persistent brand bar and a consistent background.
 */
export function Layout({ children }: LayoutProps) {
  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container flex h-14 items-center">
          <Link
            to="/profiles"
            className="flex items-center gap-2.5 font-heading text-sm font-semibold tracking-tight transition-opacity hover:opacity-80"
          >
            <span className="flex size-7 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <Cable className="size-4" />
            </span>
            API Connector
          </Link>
        </div>
      </header>

      <main>{children}</main>
    </div>
  );
}
