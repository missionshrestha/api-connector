// frontend/src/features/connection-profile/api/connectionTestApi.ts
import { apiClient } from "@/lib";
import type { ConnectionTestResult } from "../types";

export const connectionTestApi = {
  runConnectionTest(
    profileId: number,
    testPath?: string,
  ): Promise<ConnectionTestResult> {
    return apiClient
      .post<ConnectionTestResult>(
        `/api/connector/profiles/${profileId}/test/`,
        { test_path: testPath ?? null },
      )
      .then((r) => r.data);
  },
};