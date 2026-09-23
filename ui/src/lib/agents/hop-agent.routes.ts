import { Routes } from '@angular/router';

/**
 * Agent management: the list, plus a full page for creating and editing.
 *
 * Mount these as children of whatever path the app uses, so the editor's
 * relative navigation back to the list works wherever they live:
 *
 * ```typescript
 * { path: 'agents', children: HOP_AGENT_ROUTES }
 * ```
 */
export const HOP_AGENT_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () => import('./hop-agents.component').then(m => m.HopAgentsComponent),
  },
  {
    path: 'new',
    loadComponent: () => import('./hop-agent-editor.component').then(m => m.HopAgentEditorComponent),
  },
  {
    // Declared after 'new' so that literal wins the match.
    path: ':agentId',
    loadComponent: () => import('./hop-agent-editor.component').then(m => m.HopAgentEditorComponent),
  },
];
