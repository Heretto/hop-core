import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { HOP_API_URL } from '../tokens/hop-api-url.token';

/** The bundled OASIS DITA 1.3 grammar, which every organization has. */
export const BUILTIN_DTD_SET_ID = 'oasis-dita-1.3';

export type DtdSetStatus = 'ready' | 'processing' | 'failed';

/** A row of the DTD sets list. */
export interface DtdSetSummary {
  id: string;
  name: string;
  builtin: boolean;
  is_default: boolean;
  description: string;
  version_label?: string | null;
  filename?: string | null;
  based_on?: string | null;
  document_type_count?: number | null;
  specialized_count?: number | null;
  /** Of the set as a whole: processing or failed only while it has no usable version. */
  status: DtdSetStatus;
  warning_count: number;
  /** The most recent upload, when it isn't the version in use. */
  latest_version_id?: string | null;
  latest_label?: string | null;
  latest_status?: DtdSetStatus | null;
  latest_step?: number | null;
  latest_error?: string | null;
  used_by: number;
  updated_at?: string | null;
}

export interface DtdSetList {
  default_id: string;
  max_upload_mb: number;
  sets: DtdSetSummary[];
}

export interface DtdSetStep {
  key: string;
  label: string;
  state: 'done' | 'running' | 'pending' | 'failed';
  detail: string;
}

export interface DtdSetVersion {
  id: string;
  dtd_set_id: string;
  label: string;
  filename: string;
  size_bytes: number;
  status: DtdSetStatus;
  step: number;
  error?: string | null;
  is_current: boolean;
  uploaded_by?: string | null;
  created_at?: string | null;
  processed_at?: string | null;
  steps: DtdSetStep[];
}

export interface DtdDocumentType {
  name: string;
  root: string;
  public_id: string;
  shell: string;
  kind: 'base' | 'specialized';
  specializes?: string | null;
  parses: boolean;
}

export interface DtdSetIssue {
  title: string;
  detail: string;
  file?: string | null;
  line?: number | null;
  severity: string;
}

export interface DtdSetDetail extends DtdSetSummary {
  uploaded_by?: string | null;
  package: {
    based_on?: string | null;
    filename?: string | null;
    size_bytes?: number | null;
    file_count?: number | null;
    catalog?: string | null;
    public_id_count?: number | null;
    processed_at?: string | null;
  };
  issues: DtdSetIssue[];
  document_types: DtdDocumentType[];
  agents: { id: string; name: string }[];
  versions: DtdSetVersion[];
}

/** Uploading, processing and choosing an organization's DTD sets. */
@Injectable({ providedIn: 'root' })
export class HopDtdSetService {
  private http = inject(HttpClient);
  private apiUrl = inject(HOP_API_URL);

  /** All sets, the default first. 404s when the app didn't mount the DTD-set routes. */
  list(): Observable<DtdSetList> {
    return this.http.get<DtdSetList>(`${this.apiUrl}/dtd-sets`);
  }

  get(id: string): Observable<DtdSetDetail> {
    return this.http.get<DtdSetDetail>(`${this.apiUrl}/dtd-sets/${id}`);
  }

  setDefault(id: string): Observable<DtdSetList> {
    return this.http.put<DtdSetList>(`${this.apiUrl}/dtd-sets/default`, { dtd_set_id: id });
  }

  /** Upload a new set. Processing continues in the background; poll the returned version. */
  upload(file: File, name: string, version: string, description = ''): Observable<DtdSetVersion> {
    const form = new FormData();
    form.append('file', file, file.name);
    form.append('name', name);
    form.append('version', version);
    form.append('description', description);
    return this.http.post<DtdSetVersion>(`${this.apiUrl}/dtd-sets`, form);
  }

  /** Upload a new version. Apps keep using the current one until it's ready. */
  uploadVersion(id: string, file: File, version: string): Observable<DtdSetVersion> {
    const form = new FormData();
    form.append('file', file, file.name);
    form.append('version', version);
    return this.http.post<DtdSetVersion>(`${this.apiUrl}/dtd-sets/${id}/versions`, form);
  }

  getVersion(id: string, versionId: string): Observable<DtdSetVersion> {
    return this.http.get<DtdSetVersion>(`${this.apiUrl}/dtd-sets/${id}/versions/${versionId}`);
  }

  restore(id: string, versionId: string): Observable<DtdSetDetail> {
    return this.http.post<DtdSetDetail>(`${this.apiUrl}/dtd-sets/${id}/versions/${versionId}/restore`, {});
  }

  /** Where a version's zip downloads from (authenticated by the session cookie). */
  downloadUrl(id: string, versionId: string): string {
    return `${this.apiUrl}/dtd-sets/${id}/versions/${versionId}/download`;
  }

  delete(id: string): Observable<{ message: string }> {
    return this.http.delete<{ message: string }>(`${this.apiUrl}/dtd-sets/${id}`);
  }
}

/** "Acme Product DITA · v2.3", "OASIS DITA 1.3 (built in)", "Partner docs · failed". */
export function dtdSetOptionLabel(set: DtdSetSummary): string {
  if (set.builtin) return `${set.name} (built in)`;
  if (set.status !== 'ready') return `${set.name} · ${set.status}`;
  return set.version_label ? `${set.name} · ${set.version_label}` : set.name;
}

/** Only the built-in set or one with a processed version can be chosen. */
export function dtdSetUsable(set: DtdSetSummary): boolean {
  return set.status === 'ready';
}
