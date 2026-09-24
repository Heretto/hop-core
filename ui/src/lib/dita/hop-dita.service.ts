import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { HOP_API_URL } from '../tokens/hop-api-url.token';

/**
 * Conditional-processing exclusions, DITAVAL-style: attribute name → values
 * to exclude, e.g. `{ audience: ['expert'], platform: ['windows'] }`.
 */
export type DitaExclusions = Record<string, string[]>;

export interface DitaRenderRequest {
  /** A DITA topic as XML text (any topic type; nested topics included). */
  content: string;
  exclude?: DitaExclusions;
  /** Render draft-comment and required-cleanup (hidden by default). */
  show_draft?: boolean;
  /** Levels to push headings down — 1 makes the topic title an `<h2>`. */
  heading_offset?: number;
}

/** A topic rendered by `POST /dita/render` (`hop_core.dita.DitaRenderer`). */
export interface RenderedDitaTopic {
  /** HTML fragment — show it with `<hop-dita-content [html]>`. */
  html: string;
  /** Plain-text topic title. */
  title: string;
  shortdesc: string | null;
  topic_id: string | null;
  /** Root element name: topic, concept, task, reference, ... */
  topic_type: string;
  lang: string | null;
  /** Content the renderer could not honor (unresolved conrefs/keyrefs, ...). */
  warnings: string[];
}

@Injectable({ providedIn: 'root' })
export class HopDitaService {
  private http = inject(HttpClient);
  private apiUrl = inject(HOP_API_URL);

  /** Render a DITA topic to HTML on the server. */
  render(content: string, options: Omit<DitaRenderRequest, 'content'> = {}): Observable<RenderedDitaTopic> {
    return this.http.post<RenderedDitaTopic>(`${this.apiUrl}/dita/render`, { content, ...options });
  }
}
