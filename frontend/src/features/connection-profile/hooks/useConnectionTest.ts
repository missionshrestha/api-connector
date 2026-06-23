// frontend/src/features/connection-profile/hooks/useConnectionTest.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { connectionTestApi } from "../api/connectionTestApi";
import type { ConnectionTestResult } from "../types";
import { PROFILE_QUERY_KEY } from "./useProfiles";

export function useRunConnectionTest() {
  const queryClient = useQueryClient();

  return useMutation<
    ConnectionTestResult,
    unknown,
    { profileId: number; testPath?: string }
  >({
    mutationFn: ({ profileId, testPath }) =>
      connectionTestApi.runConnectionTest(profileId, testPath),
    onSuccess: () => {
      // Refresh profile list so last_test_* fields update
      queryClient.invalidateQueries({ queryKey: PROFILE_QUERY_KEY });
    },
  });
}