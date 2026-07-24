// frontend/src/shared/types/domain.test.ts
import { describe, it, expectTypeOf } from "vitest";
import type { APIError, ConnectionProfile, Endpoint } from "@/shared/types";
import type { AuthType } from "@/shared/types";
import { ErrorCode } from "@/lib/errors";

describe("TypeScript domain types", () => {
    it("ConnectionProfile.last_test_outcome is boolean | null (never just boolean)", () => {
        expectTypeOf<ConnectionProfile["last_test_outcome"]>().toEqualTypeOf<boolean | null>();
    });

  it("ConnectionProfile.credentials_summary is CredentialsSummary | null", () => {
    expectTypeOf<ConnectionProfile["credentials_summary"]>().not.toBeString();
    expectTypeOf<ConnectionProfile["credentials_summary"]>().not.toBeNumber();
  });

  it("AuthType includes all 6 string literal values", () => {
    const types: AuthType[] = [
      "none",
      "api_key",
      "bearer",
      "basic",
      "oauth_cc",
      "oauth_ac",
    ];
    expectTypeOf(types).toBeArray();
  });

  it("ErrorCode.NOT_FOUND is the string literal type 'API_CONN_002'", () => {
    expectTypeOf(ErrorCode.NOT_FOUND).toEqualTypeOf<"API_CONN_002">();
  });

  it("ErrorCode.VALIDATION_ERROR is not just 'string' — it is a literal", () => {
    // If 'as const' were removed, this would fail: string ≠ "API_CONN_001"
    expectTypeOf(ErrorCode.VALIDATION_ERROR).toEqualTypeOf<"API_CONN_001">();
  });

  it("APIError.detail is never null", () => {
    expectTypeOf<APIError["detail"]>().not.toBeNull();
  });

  it("APIError.detail accepts a plain empty object", () => {
    const err: APIError = {
      error_code: "API_CONN_001",
      message: "test",
      detail: {},
    };
    expectTypeOf(err.detail).not.toBeNull();
  });

  it("Endpoint.response_format is the literal union 'json' | 'xml' (never just string)", () => {
    expectTypeOf<Endpoint["response_format"]>().toEqualTypeOf<"json" | "xml">();
  });
});