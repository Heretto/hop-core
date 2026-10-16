import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { HOP_API_URL } from '../tokens/hop-api-url.token';
import { HerettoConnection } from '../agents/hop-agent.service';

/** What a picker filters on. `other` is any file that isn't one of the rest. */
export type HerettoFileKind = 'map' | 'topic' | 'image' | 'other';
export type HerettoEntryKind = HerettoFileKind | 'folder';

export interface HerettoRepository {
  branch: string;
  repository: string;
}

/** A folder or file in a listing or search result. */
export interface HerettoEntry {
  id: string;
  name: string;
  kind: HerettoEntryKind;
  /** Heretto's own type (Topic, Map, SiteMap, …), when it gives one. */
  type?: string | null;
  mime_type?: string | null;
}

export interface HerettoFolderRef {
  id: string;
  name: string;
}

export interface HerettoFolderListing {
  id: string;
  name: string;
  path?: string | null;
  parent_id?: string | null;
  branch?: string | null;
  repository?: string | null;
  /** The folders above, from the repository's documents folder down — when asked for. */
  ancestors?: HerettoFolderRef[] | null;
  entries: HerettoEntry[];
}

export interface HerettoSearchMatch extends HerettoEntry {
  folder_id: string;
  /** Relative to the folder the search started in: "/" or "/install". */
  folder_path: string;
}

export interface HerettoSearchResult {
  query: string;
  matches: HerettoSearchMatch[];
  folders_searched: number;
  /** A limit stopped the search before it covered every subfolder. */
  truncated: boolean;
}

/** A Heretto file as a picker describes it — and what an app keeps once one is chosen. */
export interface HerettoFile {
  id: string;
  name: string;
  title: string;
  kind: HerettoFileKind;
  is_map: boolean;
  path?: string | null;
  folder_id?: string | null;
  mime_type?: string | null;
  status?: string | null;
  /** ISO 8601. */
  last_modified?: string | null;
  /** Opens the file in Heretto's editor; DITA topics and maps only. */
  editor_url?: string | null;
  credential_id: string;
  credential_name: string;
}

/** Why a Heretto request failed, from a `/heretto` error response. */
export interface HerettoFailure {
  message: string;
  /** `credentials`: Heretto rejected the connection. `not_found`: no such file or folder. */
  reason: 'credentials' | 'not_found' | 'error';
  /** The folder a typed path stopped in, to offer browsing it. */
  folder_id?: string | null;
}

/** Turns any `/heretto` error response into a `HerettoFailure`. */
export function herettoFailure(error: unknown): HerettoFailure {
  const detail = (error as HttpErrorResponse)?.error?.detail;
  if (detail && typeof detail === 'object' && 'message' in detail) return detail as HerettoFailure;
  if (typeof detail === 'string') return { message: detail, reason: 'error' };
  if ((error as HttpErrorResponse)?.status === 429) {
    return { message: 'Too many Heretto requests just now. Wait a minute and try again.', reason: 'error' };
  }
  return { message: 'Could not reach the server.', reason: 'error' };
}

export const HERETTO_KIND_LABELS: Record<HerettoEntryKind, string> = {
  folder: 'Folder', map: 'DITA map', topic: 'DITA topic', image: 'Image', other: 'File',
};

/** Browsing a Heretto CCMS through the organization's Heretto connections. */
@Injectable({ providedIn: 'root' })
export class HopHerettoService {
  private http = inject(HttpClient);
  private apiUrl = inject(HOP_API_URL);

  private base(credentialId: string): string {
    return `${this.apiUrl}/heretto/${encodeURIComponent(credentialId)}`;
  }

  connections(): Observable<HerettoConnection[]> {
    return this.http.get<HerettoConnection[]>(`${this.apiUrl}/heretto/connections`);
  }

  repositories(credentialId: string): Observable<HerettoRepository[]> {
    return this.http.get<HerettoRepository[]>(`${this.base(credentialId)}/repositories`);
  }

  /** A repository's documents folder, where browsing starts. */
  openRepository(credentialId: string, branch: string, repository: string): Observable<HerettoFolderListing> {
    return this.http.get<HerettoFolderListing>(
      `${this.base(credentialId)}/repositories/${encodeURIComponent(branch)}/${encodeURIComponent(repository)}`,
    );
  }

  /** A folder's contents. `ancestors` adds the folders above it, for breadcrumbs. */
  openFolder(credentialId: string, folderId: string, ancestors = false): Observable<HerettoFolderListing> {
    const params = ancestors ? new HttpParams().set('ancestors', 'true') : undefined;
    return this.http.get<HerettoFolderListing>(
      `${this.base(credentialId)}/folders/${encodeURIComponent(folderId)}`, { params },
    );
  }

  /** The folder a typed path names (`/guides/install`, a full repository path, or a folder ID/URL). */
  resolveFolder(credentialId: string, repo: HerettoRepository, path: string): Observable<HerettoFolderListing> {
    return this.http.post<HerettoFolderListing>(`${this.base(credentialId)}/folders/resolve`, {
      branch: repo.branch, repository: repo.repository, path,
    });
  }

  /** Files and folders whose names contain `query`, in the folder and below. */
  search(credentialId: string, folderId: string, query: string): Observable<HerettoSearchResult> {
    return this.http.get<HerettoSearchResult>(
      `${this.base(credentialId)}/folders/${encodeURIComponent(folderId)}/search`,
      { params: new HttpParams().set('q', query) },
    );
  }

  file(credentialId: string, fileId: string): Observable<HerettoFile> {
    return this.http.get<HerettoFile>(`${this.base(credentialId)}/files/${encodeURIComponent(fileId)}`);
  }

  /** The file a pasted file ID, Heretto URL or repository path names. */
  resolve(credentialId: string, identifier: string): Observable<HerettoFile> {
    return this.http.post<HerettoFile>(`${this.base(credentialId)}/resolve`, { identifier });
  }
}
