// frontend/src/features/connection-profile/pages/ProfileFormPage.tsx
import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Controller, useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import type { APIError } from "@/shared/types";
import { Credentials } from "../types";
import { profileCreateSchema, type ProfileFormValues } from "../schemas";
import { DefaultHeadersEditor } from "../components/DefaultHeadersEditor";
import { AUTH_FIELDS_COMPONENT_MAP } from "../components/auth-fields";
import { useCreateProfile, useProfile, useUpdateProfile } from "../hooks";

export default function ProfileFormPage() {
  const { id } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const isEditMode = id !== undefined;
  const profileId = id ? Number(id) : undefined;

  const { data: profile, isLoading: isLoadingProfile } = useProfile(profileId);
  const createProfile = useCreateProfile();
  const updateProfile = useUpdateProfile();

  const {
    control,
    handleSubmit,
    reset,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<ProfileFormValues>({
    resolver: zodResolver(profileCreateSchema),
    defaultValues: {
      name: "",
      base_url: "",
      auth_type: "none",
      ssl_verify: true,
      request_timeout: 30,
      default_headers: [],
      credentials: {},
    },
  });

  // Populate form when editing — NEVER populate credentials from API response
  useEffect(() => {
    if (isEditMode && profile) {
      reset({
        name: profile.name,
        base_url: profile.base_url,
        auth_type: profile.auth_type,
        ssl_verify: profile.ssl_verify,
        request_timeout: profile.request_timeout,
        default_headers: profile.default_headers,
        credentials: {}, // Always empty — credentials are never pre-populated
      });
    }
  }, [profile, isEditMode, reset]);

  const watchedAuthType = useWatch({ control, name: "auth_type" }) ?? "none";
  const AuthFieldsComponent = AUTH_FIELDS_COMPONENT_MAP[watchedAuthType as keyof typeof AUTH_FIELDS_COMPONENT_MAP];

  function handleAuthTypeChange(newType: string) {
    setValue("auth_type", newType as ProfileFormValues["auth_type"]);
    // Only clear credentials — preserve all other form fields
    setValue("credentials", {});
  }

  async function onSubmit(data: ProfileFormValues) {
    // Filter empty-string credential values before submission.
    // An empty string means "don't change this field" for the update path.
    // The backend merge logic relies on falsy values being excluded.
    const filteredCredentials = Object.fromEntries(
      Object.entries(data.credentials ?? {}).filter(([, v]) => v !== "" && v !== null && v !== undefined)
    );

    const payload = { ...data, credentials: filteredCredentials as Credentials };

    // Security: never log payload — it may contain credential values
    if (isEditMode && profileId !== undefined) {
      updateProfile.mutate(
        { id: profileId, data: payload },
        { onSuccess: () => navigate("/profiles") }
      );
    } else {
      createProfile.mutate(payload, {
        onSuccess: () => navigate("/profiles"),
      });
    }
  }

  const mutationError = isEditMode ? updateProfile.error : createProfile.error;
  const isSaving = isEditMode ? updateProfile.isPending : createProfile.isPending;

  if (isEditMode && isLoadingProfile) {
    return <div className="container mx-auto py-8 px-4 max-w-2xl">Loading…</div>;
  }

  return (
    <div className="container mx-auto py-8 px-4 max-w-2xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold">
          {isEditMode ? `Edit ${profile?.name ?? "Profile"}` : "New Profile"}
        </h1>
        {/* TODO Phase 3: Test Connection button */}
      </div>

      <form onSubmit={handleSubmit(onSubmit)} autoComplete="off" className="space-y-8">
        {/* ── Section 1: Profile Information ──────────────────────────── */}
        <section className="space-y-4">
          <h2 className="text-lg font-medium border-b pb-2">Profile Information</h2>

          <Controller
            name="name"
            control={control}
            render={({ field }) => (
              <div className="space-y-1">
                <Label htmlFor="name">Profile Name</Label>
                <Input id="name" {...field} placeholder="My API" />
                {errors.name && <p className="text-destructive text-sm">{errors.name.message}</p>}
              </div>
            )}
          />

          <Controller
            name="base_url"
            control={control}
            render={({ field }) => (
              <div className="space-y-1">
                <Label htmlFor="base_url">Base URL</Label>
                <Input id="base_url" {...field} placeholder="https://api.example.com" />
                {errors.base_url && <p className="text-destructive text-sm">{errors.base_url.message}</p>}
              </div>
            )}
          />

          <Controller
            name="request_timeout"
            control={control}
            render={({ field }) => (
              <div className="space-y-1">
                <Label htmlFor="request_timeout">Request Timeout (seconds)</Label>
                <Input
                  id="request_timeout"
                  type="number"
                  min={1}
                  max={120}
                  {...field}
                  onChange={(e) => field.onChange(e.target.valueAsNumber)}
                />
                {errors.request_timeout && (
                  <p className="text-destructive text-sm">{errors.request_timeout.message}</p>
                )}
              </div>
            )}
          />

          <Controller
            name="ssl_verify"
            control={control}
            render={({ field }) => (
              <div className="flex items-center gap-2">
                <Checkbox
                  id="ssl_verify"
                  checked={field.value}
                  onCheckedChange={field.onChange}
                />
                <Label htmlFor="ssl_verify">Verify SSL Certificate</Label>
              </div>
            )}
          />

          <div className="space-y-2">
            <Label>Default Headers</Label>
            <Controller
              name="default_headers"
              control={control}
              render={({ field }) => (
                <DefaultHeadersEditor
                  value={field.value ?? []}
                  onChange={field.onChange}
                />
              )}
            />
            {errors.default_headers && (
              <p className="text-destructive text-sm">
                {typeof errors.default_headers.message === "string"
                  ? errors.default_headers.message
                  : "Invalid header configuration"}
              </p>
            )}
          </div>
        </section>

        {/* ── Section 2: Authentication ────────────────────────────────── */}
        <section className="space-y-4">
          <h2 className="text-lg font-medium border-b pb-2">Authentication</h2>

          <div className="space-y-1">
            <Label>Auth Type</Label>
            <Select value={watchedAuthType} onValueChange={handleAuthTypeChange}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">No Auth</SelectItem>
                <SelectItem value="api_key">API Key</SelectItem>
                <SelectItem value="bearer">Bearer Token</SelectItem>
                <SelectItem value="basic">Basic Auth</SelectItem>
                <SelectItem value="oauth_cc">OAuth Client Credentials</SelectItem>
                <SelectItem value="oauth_ac">OAuth Authorization Code</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {AuthFieldsComponent && (
            <AuthFieldsComponent
              isEditMode={isEditMode}
              credentialsSummary={profile?.credentials_summary ?? null}
              control={control}
              errors={errors}
              oauthAcAuthorized={profile?.oauth_ac_authorized ?? null}
              profileId={profileId}                                        
            />
          )}
        </section>

        {/* ── Form-level error ─────────────────────────────────────────── */}
        {mutationError && (
          <p className="text-destructive text-sm">
            {(mutationError as unknown as APIError)?.message ?? "An error occurred. Please try again."}
          </p>
        )}

        {/* ── Actions ──────────────────────────────────────────────────── */}
        <div className="flex gap-3">
          <Button type="submit" disabled={isSaving || isSubmitting}>
            {isSaving ? "Saving…" : isEditMode ? "Save Changes" : "Create Profile"}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate("/profiles")}
          >
            Cancel
          </Button>
        </div>
      </form>
    </div>
  );
}