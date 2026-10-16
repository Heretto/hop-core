import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { HOP_API_URL } from '../tokens/hop-api-url.token';

/**
 * An AI configuration an agent can run on — a credential of a type the host
 * app registered as `is_ai_configuration`. Established separately, through
 * the credentials API; never carries the API key.
 */
export interface AiConfiguration {
  id: string;
  name: string;
  /** The credential's type is the provider ("anthropic", "openai", ...). */
  provider: string;
  provider_label: string;
  model: string;
}

/** One markdown document supplied to the agent as reference material. */
export interface AgentContextFile {
  id?: string;
  name: string;
  content: string;
  position?: number;
}

/**
 * How a Heretto reference reaches the agent. Style guides, information models
 * and terminology are included in every run; general content is read on demand.
 */
export type AgentReferenceType = 'general' | 'style_guide' | 'information_model' | 'terminology';

/** Reference material the agent may draw on: a URL, or a file in Heretto. */
export interface AgentReference {
  id?: string | null;
  kind: 'url' | 'heretto';
  /** The operator's note on how the agent should use this material. */
  guidance: string;
  /** kind === 'url': a URL prefix the agent may read. */
  url?: string | null;
  /** kind === 'heretto': the Heretto connection (credential) to read through. */
  credential_id?: string | null;
  file_id?: string | null;
  title?: string | null;
  path?: string | null;
  /** A map: reading it brings in every topic it links to. */
  is_map?: boolean;
  reference_type?: AgentReferenceType | null;
  /** Response only: the connection's name, and whether it still exists. */
  credential_name?: string | null;
  available?: boolean;
}

/** A Heretto credential an agent can read references through. */
export interface HerettoConnection {
  id: string;
  name: string;
  server_url: string;
}

/** What a pasted Heretto identifier resolved to. */
export interface HerettoResolveResult {
  file_id: string;
  title: string;
  name: string;
  path?: string | null;
  is_map: boolean;
}

/** List-view shape — everything but the context-file bodies. */
export interface AgentSummary {
  id: string;
  name: string;
  description?: string | null;
  ai_configuration_id?: string | null;
  /** Resolved for display; null when unset or the credential was deleted. */
  ai_configuration?: AiConfiguration | null;
  permitted_urls: string[];
  /** null when the agent follows the organization default DTD set. */
  dtd_set_id?: string | null;
  context_file_count: number;
  has_feedback_memory: boolean;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
  created_by?: string | null;
}

export interface Agent extends AgentSummary {
  context_files: AgentContextFile[];
  references: AgentReference[];
  feedback_memory: string;
}

export interface AgentCreate {
  name: string;
  description?: string | null;
  ai_configuration_id?: string | null;
  context_files?: AgentContextFile[];
  /** Older shape; `references` supersedes it and wins when both are sent. */
  permitted_urls?: string[];
  references?: AgentReference[];
  /** The DTD set this agent validates DITA against; null follows the organization default. */
  dtd_set_id?: string | null;
  feedback_memory?: string;
  is_active?: boolean;
}

/** Partial update. `context_files` and `references` replace the whole list. */
export type AgentUpdate = Partial<AgentCreate>;

/** One turn in a test conversation. */
export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface AgentChatRequest {
  messages: ChatMessage[];
  max_tokens?: number | null;
  temperature?: number | null;
}

export interface AgentChatResponse {
  message: ChatMessage;
  provider: string;
  model: string;
  ai_configuration_name: string;
  /** What the agent was actually told — the point of testing. */
  system_prompt: string;
}

@Injectable({ providedIn: 'root' })
export class HopAgentService {
  private http = inject(HttpClient);
  private apiUrl = inject(HOP_API_URL);

  listAgents(): Observable<AgentSummary[]> {
    return this.http.get<AgentSummary[]>(`${this.apiUrl}/agents`);
  }

  getAgent(agentId: string): Observable<Agent> {
    return this.http.get<Agent>(`${this.apiUrl}/agents/${agentId}`);
  }

  createAgent(agent: AgentCreate): Observable<Agent> {
    return this.http.post<Agent>(`${this.apiUrl}/agents`, agent);
  }

  updateAgent(agentId: string, changes: AgentUpdate): Observable<Agent> {
    return this.http.put<Agent>(`${this.apiUrl}/agents/${agentId}`, changes);
  }

  deleteAgent(agentId: string): Observable<{ message: string }> {
    return this.http.delete<{ message: string }>(`${this.apiUrl}/agents/${agentId}`);
  }

  /** Replace the agent's feedback memory wholesale. */
  replaceMemory(agentId: string, feedbackMemory: string): Observable<Agent> {
    return this.http.put<Agent>(`${this.apiUrl}/agents/${agentId}/memory`, {
      feedback_memory: feedbackMemory,
    });
  }

  /** Add one piece of feedback to what the agent already remembers. */
  appendFeedback(agentId: string, feedback: string, heading?: string): Observable<Agent> {
    return this.http.post<Agent>(`${this.apiUrl}/agents/${agentId}/memory`, { feedback, heading });
  }

  /**
   * Talk to an agent to test it. The whole conversation goes up each time —
   * the server stores no history, so a test session lives in the browser.
   */
  chat(agentId: string, request: AgentChatRequest): Observable<AgentChatResponse> {
    return this.http.post<AgentChatResponse>(
      `${this.apiUrl}/agents/${agentId}/chat`, request,
    );
  }

  /** The AI configurations an agent can be pointed at. */
  listAiConfigurations(): Observable<AiConfiguration[]> {
    return this.http.get<AiConfiguration[]>(`${this.apiUrl}/agents/ai-configurations`);
  }

  /** The Heretto connections an agent can read references through. */
  listHerettoConnections(): Observable<HerettoConnection[]> {
    return this.http.get<HerettoConnection[]>(`${this.apiUrl}/agents/heretto-connections`);
  }

  /** Check a pasted Heretto file ID, URL or repository path, and describe the file. */
  resolveHerettoReference(credentialId: string, identifier: string): Observable<HerettoResolveResult> {
    return this.http.post<HerettoResolveResult>(`${this.apiUrl}/agents/heretto/resolve`, {
      credential_id: credentialId, identifier,
    });
  }
}
