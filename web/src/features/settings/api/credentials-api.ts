import { http } from "@/lib/http";

export interface CredentialKeyStatus {
  key: string;
  label: string;
  configured: boolean;
}

export interface CredentialNamespace {
  namespace: string;
  label: string;
  description: string | null;
  keys: CredentialKeyStatus[];
}

export interface CredentialsResponse {
  vault_enabled: boolean;
  namespaces: CredentialNamespace[];
}

export const credentialsApi = {
  list: () => http.get<CredentialsResponse>("/credentials"),

  write: (namespace: string, key: string, value: string) =>
    http.put<void>(
      `/credentials/${encodeURIComponent(namespace)}/${encodeURIComponent(key)}`,
      { value },
    ),

  remove: (namespace: string, key: string) =>
    http.delete(
      `/credentials/${encodeURIComponent(namespace)}/${encodeURIComponent(key)}`,
    ),
};
