import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { HOP_API_URL } from '../tokens/hop-api-url.token';

export type CredentialFieldType =
  'text' | 'password' | 'email' | 'url' | 'select' | 'textarea';

export interface CredentialFieldOption {
  value: string;
  label: string;
}

/** One input in a credential form, as declared by the backend's type spec. */
export interface CredentialField {
  name: string;
  label: string;
  type: CredentialFieldType;
  required: boolean;
  /** Write-only: never returned, and left alone when submitted blank. */
  secret: boolean;
  /** Shown as a column in the credential list. */
  summary: boolean;
  placeholder: string;
  help: string;
  options: CredentialFieldOption[];
}

/** A credential type the application registered. */
export interface CredentialTypeSpec {
  type: string;
  label: string;
  /** Types sharing a group render in one tab with a picker between them. */
  group?: string | null;
  group_label?: string | null;
  icon: string;
  description: string;
  is_ai_configuration: boolean;
  /** Whether a connection tester is registered for this type. */
  testable: boolean;
  fields: CredentialField[];
}

/**
 * What was sent and what came back. Absent when no request was made — a URL
 * refused by validation never leaves the server.
 */
export interface CredentialTestExchange {
  method: string;
  url: string;
  status_code: number | null;
  response_body: string;
  body_truncated: boolean;
  duration_ms: number | null;
}

/** The outcome of testing one credential. */
export interface CredentialTestResult {
  success: boolean;
  message: string;
  details: Record<string, any>;
  exchange: CredentialTestExchange | null;
  tested_at: string;
}

export interface Credential {
  id: string;
  type: string;
  name: string;
  created_at: string;
  updated_at?: string;
  /** Non-secret field values. */
  values: Record<string, any>;
  /** Which secret fields hold a value — never the values themselves. */
  secrets_set: string[];
}

export interface CredentialCreate {
  type: string;
  name: string;
  credentials: Record<string, any>;
}

export interface CredentialUpdate {
  name?: string;
  credentials?: Record<string, any>;
}

@Injectable({ providedIn: 'root' })
export class HopCredentialService {
  private http = inject(HttpClient);
  private apiUrl = inject(HOP_API_URL);

  /** The credential types this application registered. */
  listTypes(): Observable<CredentialTypeSpec[]> {
    return this.http.get<CredentialTypeSpec[]>(`${this.apiUrl}/credentials/types`);
  }

  listCredentials(): Observable<Credential[]> {
    return this.http.get<Credential[]>(`${this.apiUrl}/credentials`);
  }

  createCredential(credential: CredentialCreate): Observable<Credential> {
    return this.http.post<Credential>(`${this.apiUrl}/credentials`, credential);
  }

  updateCredential(credentialId: string, changes: CredentialUpdate): Observable<Credential> {
    return this.http.put<Credential>(`${this.apiUrl}/credentials/${credentialId}`, changes);
  }

  deleteCredential(credentialId: string): Observable<{ message: string }> {
    return this.http.delete<{ message: string }>(`${this.apiUrl}/credentials/${credentialId}`);
  }

  /**
   * Check that a credential reaches the service it names. A failed connection
   * comes back as a 200 with `success: false`, not an HTTP error.
   */
  testCredential(credentialId: string): Observable<CredentialTestResult> {
    return this.http.post<CredentialTestResult>(
      `${this.apiUrl}/credentials/${credentialId}/test`, {},
    );
  }
}
