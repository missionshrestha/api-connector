// frontend/src/features/connection-profile/api/oauthApi.ts
import { apiClient } from "@/lib";

interface OAuthInitiateResponse {
  authorization_url: string;
  state: string;
}

export const oauthApi = {
  /**
   * Requests the backend to generate a PKCE pair and state record,
   * then returns the fully-constructed authorization URL.
   *
   * redirectOrigin: window.location.origin — the frontend's origin for
   * postMessage targeting. Validated against CORS_ALLOWED_ORIGINS on backend.
   */
  initiateOAuthAC(
    profileId: number,
    redirectOrigin: string,
  ): Promise<OAuthInitiateResponse> {
    return apiClient
      .get<OAuthInitiateResponse>(
        `/api/connector/profiles/${profileId}/oauth/initiate/`,
        { params: { redirect_origin: redirectOrigin } },
      )
      .then((r) => r.data);
  },
};