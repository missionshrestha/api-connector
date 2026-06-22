// frontend/src/features/connection-profile/types/requests.ts
import type { AuthType } from "@/shared/types";

// ── Per-auth-type credential write types ──────────────────────────────────────

export type NoneCredentials = Record<string, never>;

export interface APIKeyCredentials {
  key_name: string;
  key_value: string;
  delivery: "header" | "query";
  prefix?: string;
}

export interface BearerCredentials {
  token: string;
  header_name?: string;
}

export interface BasicCredentials {
  username: string;
  password: string;
}

export interface OAuthCCCredentials {
  client_id: string;
  client_secret: string;
  token_endpoint: string;
  scopes?: string;
}

export interface OAuthACCredentials extends OAuthCCCredentials {
  authorization_endpoint: string;
}

export type Credentials =
  | NoneCredentials
  | APIKeyCredentials
  | BearerCredentials
  | BasicCredentials
  | OAuthCCCredentials
  | OAuthACCredentials;

// ── Profile write request types ────────────────────────────────────────────────

export interface ProfileCreateRequest {
  name: string;
  base_url: string;
  auth_type: AuthType;
  default_headers?: Array<{ name: string; value: string }>;
  ssl_verify?: boolean;
  request_timeout?: number;
  credentials?: Credentials;
}

// All fields optional for PATCH support
export type ProfileUpdateRequest = Partial<ProfileCreateRequest>;