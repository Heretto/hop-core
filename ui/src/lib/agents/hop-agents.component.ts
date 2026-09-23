import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatChipsModule } from '@angular/material/chips';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ActivatedRoute, Router } from '@angular/router';
import { AgentCreate, AgentSummary, HopAgentService } from './hop-agent.service';
import { HopConfirmDialogComponent } from '../shared/hop-confirm-dialog.component';

@Component({
  selector: 'hop-agents',
  standalone: true,
  imports: [
    CommonModule, MatCardModule, MatButtonModule, MatIconModule, MatMenuModule,
    MatChipsModule, MatTooltipModule, MatProgressSpinnerModule, MatDialogModule,
    MatSnackBarModule,
  ],
  template: `
    <div class="agents-container hop-page">
      <div class="agents-header">
        <div>
          <h1>Agents</h1>
          <p class="page-intro">
            Reusable agent configurations. Jobs and workflows give an agent input and
            instructions and get its output back — agents do nothing on their own.
          </p>
        </div>
        <button mat-raised-button color="primary" (click)="createAgent()">
          <mat-icon>add</mat-icon>
          New Agent
        </button>
      </div>

      <mat-card class="loading-card" *ngIf="loading">
        <mat-card-content>
          <mat-spinner></mat-spinner>
          <p>Loading agents...</p>
        </mat-card-content>
      </mat-card>

      <div class="empty-state" *ngIf="!loading && agents.length === 0">
        <span class="hop-icon-badge accent"><mat-icon>smart_toy</mat-icon></span>
        <h2>No agents yet</h2>
        <p>Create one to give your jobs and workflows a configured agent to call.</p>
        <button mat-raised-button color="primary" (click)="createAgent()">
          <mat-icon>add</mat-icon>
          New Agent
        </button>
      </div>

      <div class="agent-list" *ngIf="!loading && agents.length > 0">
        <mat-card *ngFor="let agent of agents"
                  class="agent-card"
                  [class.inactive]="!agent.is_active"
                  role="button"
                  tabindex="0"
                  [attr.aria-label]="'Open ' + agent.name"
                  (click)="openAgent(agent)"
                  (keydown.enter)="openAgent(agent)"
                  (keydown.space)="openAgent(agent); $event.preventDefault()">
          <mat-card-content>
            <div class="agent-row">
              <div class="agent-main">
                <div class="agent-title">
                  <h2>{{ agent.name }}</h2>
                  <span class="hop-status-chip" *ngIf="!agent.is_active">Inactive</span>
                </div>
                <p class="agent-description" *ngIf="agent.description">{{ agent.description }}</p>

                <div class="agent-facts">
                  <span class="fact" *ngIf="agent.ai_configuration"
                        matTooltip="AI configuration this agent runs on">
                    <mat-icon>memory</mat-icon>
                    {{ agent.ai_configuration.name }}
                    <span class="fact-detail" *ngIf="agent.ai_configuration.model">
                      ({{ agent.ai_configuration.model }})
                    </span>
                  </span>
                  <span class="fact fact-warning" *ngIf="!agent.ai_configuration"
                        matTooltip="Select an AI configuration before using this agent">
                    <mat-icon>error_outline</mat-icon>
                    No AI configuration
                  </span>
                  <span class="fact" matTooltip="Markdown context files">
                    <mat-icon>description</mat-icon>
                    {{ agent.context_file_count }}
                    {{ agent.context_file_count === 1 ? 'context file' : 'context files' }}
                  </span>
                  <span class="fact" matTooltip="URLs this agent may read">
                    <mat-icon>link</mat-icon>
                    {{ agent.permitted_urls.length }}
                    {{ agent.permitted_urls.length === 1 ? 'reference URL' : 'reference URLs' }}
                  </span>
                  <span class="fact" *ngIf="agent.has_feedback_memory"
                        matTooltip="This agent has feedback in memory">
                    <mat-icon>psychology</mat-icon>
                    Has memory
                  </span>
                </div>
              </div>

              <!-- Clicks here must not also open the agent behind them. -->
              <div class="agent-actions" (click)="$event.stopPropagation()">
                <button mat-icon-button [matMenuTriggerFor]="agentMenu" matTooltip="More actions"
                        [attr.aria-label]="'Actions for ' + agent.name">
                  <mat-icon>more_vert</mat-icon>
                </button>
                <mat-menu #agentMenu="matMenu">
                  <button mat-menu-item (click)="toggleActive(agent)">
                    <mat-icon>{{ agent.is_active ? 'pause_circle' : 'play_circle' }}</mat-icon>
                    <span>{{ agent.is_active ? 'Deactivate' : 'Activate' }}</span>
                  </button>
                  <button mat-menu-item (click)="duplicateAgent(agent)">
                    <mat-icon>content_copy</mat-icon>
                    <span>Duplicate</span>
                  </button>
                  <button mat-menu-item (click)="deleteAgent(agent)">
                    <mat-icon>delete</mat-icon>
                    <span>Delete</span>
                  </button>
                </mat-menu>
              </div>
            </div>
          </mat-card-content>
        </mat-card>
      </div>
    </div>
  `,
  styles: [`
    .agents-header {
      display: flex; justify-content: space-between; align-items: flex-start;
      gap: 24px; margin-bottom: 24px; flex-wrap: wrap;
    }
    .agents-header h1 { margin-bottom: 4px; }
    .page-intro { max-width: 60ch; margin: 0; }

    .agent-list { display: flex; flex-direction: column; gap: 12px; }
    mat-card.inactive { opacity: 0.65; }

    /* The card is the control: depth comes from the hairline, not a shadow. */
    .agent-card { cursor: pointer; transition: border-color .15s ease, background-color .15s ease; }
    .agent-card:hover { border-color: var(--border-strong); background: var(--hover-overlay); }
    .agent-card:focus-visible { outline: none; box-shadow: var(--focus-ring); }
    .agent-card:hover .agent-title h2 { color: var(--color-accent-text); }

    .agent-row { display: flex; align-items: flex-start; gap: 16px; }
    .agent-main { flex: 1; min-width: 0; }
    .agent-title { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
    .agent-title h2 { margin: 0; font-size: 1.125rem; }
    .agent-description { margin: 4px 0 0; }

    .agent-facts {
      display: flex; flex-wrap: wrap; gap: 8px 20px; margin-top: 12px;
      color: var(--text-tertiary);
    }
    .fact { display: inline-flex; align-items: center; gap: 6px; }
    .fact mat-icon { font-size: 18px; height: 18px; width: 18px; }
    .fact-detail { color: var(--text-tertiary); }
    .fact-warning { color: var(--color-warning-text); }

    .agent-actions { display: flex; align-items: center; gap: 4px; }

    .loading-card { display: flex; justify-content: center; min-height: 200px; text-align: center; }
    .loading-card mat-card-content { display: flex; flex-direction: column; align-items: center; }

    .empty-state { text-align: center; padding: 64px 24px; }
    .empty-state h2 { margin: 16px 0 4px; }
    .empty-state p { margin: 0 0 20px; }

    @media (max-width: 768px) {
      .agent-row { flex-direction: column; }
      .agent-actions { align-self: flex-end; }
    }
  `],
})
export class HopAgentsComponent implements OnInit {
  private agentService = inject(HopAgentService);
  private dialog = inject(MatDialog);
  private snackBar = inject(MatSnackBar);
  private router = inject(Router);
  private route = inject(ActivatedRoute);

  agents: AgentSummary[] = [];
  loading = false;

  ngOnInit(): void {
    this.loadAgents();
  }

  private loadAgents(): void {
    this.loading = true;
    this.agentService.listAgents().subscribe({
      next: agents => { this.agents = agents; this.loading = false; },
      error: () => {
        this.loading = false;
        this.snackBar.open('Failed to load agents', 'Close', { duration: 3000 });
      },
    });
  }

  /** Editing happens on its own page — an agent is too big for a dialog. */
  createAgent(): void {
    this.router.navigate(['new'], { relativeTo: this.route });
  }

  /** Open an agent. The whole card is the control; there is no Edit button. */
  openAgent(summary: AgentSummary): void {
    this.router.navigate([summary.id], { relativeTo: this.route });
  }

  duplicateAgent(summary: AgentSummary): void {
    this.agentService.getAgent(summary.id).subscribe({
      next: agent => {
        const copy: AgentCreate = {
          name: `${agent.name} (copy)`,
          description: agent.description,
          ai_configuration_id: agent.ai_configuration_id,
          context_files: agent.context_files.map(f => ({ name: f.name, content: f.content })),
          permitted_urls: [...agent.permitted_urls],
          feedback_memory: agent.feedback_memory,
          is_active: agent.is_active,
        };
        this.agentService.createAgent(copy).subscribe({
          next: () => {
            this.loadAgents();
            this.snackBar.open('Agent duplicated', 'Close', { duration: 3000 });
          },
          error: error => this.showError(error, 'Failed to duplicate agent'),
        });
      },
      error: error => this.showError(error, 'Failed to load agent'),
    });
  }

  toggleActive(agent: AgentSummary): void {
    this.agentService.updateAgent(agent.id, { is_active: !agent.is_active }).subscribe({
      next: updated => {
        agent.is_active = updated.is_active;
        this.snackBar.open(
          updated.is_active ? 'Agent activated' : 'Agent deactivated', 'Close', { duration: 3000 },
        );
      },
      error: error => this.showError(error, 'Failed to update agent'),
    });
  }

  deleteAgent(agent: AgentSummary): void {
    this.dialog.open(HopConfirmDialogComponent, {
      data: {
        title: 'Delete Agent',
        message: `Delete "${agent.name}"? Its context files and feedback memory are deleted with it.`,
        confirmText: 'Delete',
      },
    }).afterClosed().subscribe(confirmed => {
      if (!confirmed) return;
      this.agentService.deleteAgent(agent.id).subscribe({
        next: () => {
          this.loadAgents();
          this.snackBar.open('Agent deleted', 'Close', { duration: 3000 });
        },
        error: error => this.showError(error, 'Failed to delete agent'),
      });
    });
  }

  private showError(error: any, fallback: string): void {
    this.snackBar.open(error?.error?.detail || fallback, 'Close', { duration: 4000 });
  }
}
