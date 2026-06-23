// frontend/src/features/connection-profile/hooks/useOAuthAuthorize.ts
import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { APIError } from "@/shared/types";
import type { OAuthACMessageEvent, OAuthACStatus } from "../types";
import { oauthApi } from "../api/oauthApi";
import { PROFILE_QUERY_KEY } from "./useProfiles";

interface UseOAuthAuthorizeOptions {
  profileId: number | undefined;
  initialStatus?: OAuthACStatus;
}

interface UseOAuthAuthorizeReturn {
  status: OAuthACStatus;
  isAuthorizing: boolean;
  error: string | null;
  authorize: () => Promise<void>;
  reset: () => void;
}

export function useOAuthAuthorize({
  profileId,
  initialStatus = "unauthorized",
}: UseOAuthAuthorizeOptions): UseOAuthAuthorizeReturn {
  const [status, setStatus] = useState<OAuthACStatus>(initialStatus);
  const [error, setError] = useState<string | null>(null);
  const popupRef = useRef<Window | null>(null);
  const queryClient = useQueryClient();

  // postMessage listener — set up once, respond to OAUTH_AC_* events
  useEffect(() => {
    function handleMessage(event: MessageEvent) {
      const data = event.data as OAuthACMessageEvent | undefined;
      if (!data || typeof data.type !== "string") return;
      if (!data.type.startsWith("OAUTH_AC_")) return;

      if (data.type === "OAUTH_AC_SUCCESS") {
        setStatus("authorized");
        setError(null);
        popupRef.current?.close();
        // Refresh profile list so oauth_ac_authorized updates to true
        queryClient.invalidateQueries({ queryKey: PROFILE_QUERY_KEY });
      } else if (data.type === "OAUTH_AC_ERROR") {
        setStatus("unauthorized");
        setError((data as { type: string; message?: string }).message ?? "Authorization failed.");
        popupRef.current?.close();
      }
    }

    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [queryClient]);

  // Poll for popup closure — user closed popup without completing authorization
  useEffect(() => {
    if (status !== "authorizing" || !popupRef.current) return;

    const timer = setInterval(() => {
      if (popupRef.current?.closed) {
        // Popup was closed without receiving a postMessage
        setStatus("unauthorized");
        setError(null);
        popupRef.current = null;
        clearInterval(timer);
      }
    }, 500);

    return () => clearInterval(timer);
  }, [status]);

  async function authorize(): Promise<void> {
    if (!profileId) return;

    setStatus("authorizing");
    setError(null);

    let authorizationUrl: string;
    try {
      const response = await oauthApi.initiateOAuthAC(
        profileId,
        window.location.origin,
      );
      authorizationUrl = response.authorization_url;
    } catch (err) {
      setStatus("unauthorized");
      const apiError = err as APIError;
      setError(apiError?.message ?? "Failed to initiate authorization.");
      return;
    }

    // CRITICAL: window.open() must be called as soon as possible after await.
    // Most modern browsers allow popups from user-gesture chains that include
    // a single await. If popup blocking occurs, surface a fallback link.
    const popup = window.open(
      authorizationUrl,
      "oauth_ac_popup",
      "width=600,height=700,scrollbars=yes,resizable=yes",
    );

    if (!popup || popup.closed) {
      // Popup was blocked by the browser
      setStatus("unauthorized");
      setError(
        "Popup was blocked. Allow popups for this site and try again, " +
        "or open this URL manually: " + authorizationUrl,
      );
      return;
    }

    popupRef.current = popup;
  }

  function reset() {
    setStatus("unauthorized");
    setError(null);
    popupRef.current?.close();
    popupRef.current = null;
  }

  return {
    status,
    isAuthorizing: status === "authorizing",
    error,
    authorize,
    reset,
  };
}