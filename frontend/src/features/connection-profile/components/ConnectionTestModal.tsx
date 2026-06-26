// frontend/src/features/connection-profile/components/ConnectionTestModal.tsx
import { useState } from "react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/shared/components/ui/sheet";
import { useRunConnectionTest } from "../hooks/useConnectionTest";
import { ConnectionTestPanel } from "./ConnectionTestPanel";

interface ConnectionTestModalProps {
  profileId: number;
  profileName: string;
  isOpen: boolean;
  onClose: () => void;
}

export function ConnectionTestModal({
  profileId,
  profileName,
  isOpen,
  onClose,
}: ConnectionTestModalProps) {
  const [testPath, setTestPath] = useState("");
  const mutation = useRunConnectionTest();

  function handleOpenChange(open: boolean) {
    if (open) {
      // Modal opening — reset to clean state
      // Event handler, not an effect body — setState is correct here
      setTestPath("");
      mutation.reset();
    } else {
      onClose();
    }
  }

  function handleRunTest() {
    const trimmed = testPath.trim();
    mutation.mutate({
      profileId,
      // Conditional spread — only include testPath when it has a value
      // Avoids passing undefined explicitly (exactOptionalPropertyTypes)
      ...(trimmed ? { testPath: trimmed } : {}),
    });
    // Modal does NOT close on success — user reads results
  }

  return (
    <Sheet open={isOpen} onOpenChange={handleOpenChange}>
      <SheetContent className="w-full sm:max-w-xl">
        <SheetHeader className="border-b px-5 py-4">
          <SheetTitle className="text-base">Test Connection</SheetTitle>
          <SheetDescription className="font-mono text-xs">{profileName}</SheetDescription>
        </SheetHeader>

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-5">
          {/* Test path input */}
          <div className="space-y-1">
            <Label htmlFor="test-path">Test Path (optional)</Label>
            <Input
              id="test-path"
              value={testPath}
              onChange={(e) => setTestPath(e.target.value)}
              placeholder="/api/v1/health"
              disabled={mutation.isPending}
            />
            <p className="text-xs text-muted-foreground">
              Leave blank to test the base URL. Must start with{" "}
              <code className="font-mono">/</code> if provided.
            </p>
          </div>

          {/* Run Test button */}
          <Button
            onClick={handleRunTest}
            disabled={mutation.isPending}
            className="w-full"
          >
            {mutation.isPending ? "Testing…" : "Run Test"}
          </Button>

          {/* Step results panel */}
          <ConnectionTestPanel
            result={mutation.data ?? null}
            isRunning={mutation.isPending}
            error={mutation.error}
          />
        </div>
      </SheetContent>
    </Sheet>
  );
}