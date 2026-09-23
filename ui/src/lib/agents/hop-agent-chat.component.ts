import { Component, ElementRef, Input, ViewChild, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatExpansionModule } from '@angular/material/expansion';
import { ChatMessage, HopAgentService } from './hop-agent.service';

/** A turn as the panel renders it: a message, or a failure in its place. */
interface Turn {
  role: 'user' | 'assistant' | 'error';
  content: string;
}

@Component({
  selector: 'hop-agent-chat',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, MatButtonModule, MatIconModule,
    MatFormFieldModule, MatInputModule, MatTooltipModule,
    MatProgressSpinnerModule, MatExpansionModule,
  ],
  template: `
    <div class="chat">
      <div class="chat-intro">
        <p class="field-hint">
          Talk to this agent to see how it behaves. It runs exactly as a job would —
          same context files, reference URLs and memory — and nothing said here is
          stored.
        </p>
        <button mat-stroked-button type="button" *ngIf="turns.length > 0"
                (click)="clear()">
          <mat-icon>restart_alt</mat-icon>
          New conversation
        </button>
      </div>

      <!-- Preconditions: say plainly why the box is disabled. -->
      <div class="callout warning" *ngIf="!agentId">
        <mat-icon>save</mat-icon>
        <span>Save the agent before testing it.</span>
      </div>
      <div class="callout warning" *ngIf="agentId && !hasConfiguration">
        <mat-icon>memory</mat-icon>
        <span>Select an AI configuration before testing this agent.</span>
      </div>
      <div class="callout info" *ngIf="canChat && dirty">
        <mat-icon>info</mat-icon>
        <span>
          You have unsaved changes. The conversation uses the last saved version —
          save to test your edits.
        </span>
      </div>

      <div class="transcript" #transcript *ngIf="canChat">
        <div class="empty-state" *ngIf="turns.length === 0">
          <mat-icon>forum</mat-icon>
          <p>Send a message to start testing.</p>
        </div>

        <div class="turn" *ngFor="let turn of turns" [ngClass]="turn.role">
          <div class="bubble">
            <span class="who">{{ labelFor(turn) }}</span>
            <p>{{ turn.content }}</p>
          </div>
        </div>

        <div class="turn assistant" *ngIf="sending">
          <div class="bubble hop-shimmer">
            <span class="who">{{ agentName || 'Agent' }}</span>
            <p class="thinking">Thinking…</p>
          </div>
        </div>
      </div>

      <form class="composer" [formGroup]="form" (ngSubmit)="send()" *ngIf="canChat">
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Message</mat-label>
          <textarea matInput formControlName="message" rows="3"
                    placeholder="Ask the agent to do what a job would ask it to do."
                    (keydown.control.enter)="send()"
                    (keydown.meta.enter)="send()"></textarea>
          <mat-hint>Ctrl/⌘ + Enter to send</mat-hint>
        </mat-form-field>
        <button mat-raised-button color="primary" type="submit"
                [disabled]="form.invalid || sending">
          <mat-spinner diameter="20" *ngIf="sending"></mat-spinner>
          <span *ngIf="!sending">Send</span>
        </button>
      </form>

      <mat-expansion-panel class="prompt-panel" *ngIf="systemPrompt">
        <mat-expansion-panel-header>
          <mat-panel-title>System prompt sent to the model</mat-panel-title>
          <mat-panel-description *ngIf="ranOn">{{ ranOn }}</mat-panel-description>
        </mat-expansion-panel-header>
        <div class="hop-code-panel">
          <pre>{{ systemPrompt }}</pre>
        </div>
      </mat-expansion-panel>
    </div>
  `,
  styles: [`
    .chat { max-width: 900px; }
    .chat-intro { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
    .field-hint { color: var(--text-tertiary); margin: 0 0 16px; max-width: 70ch; }

    .callout {
      display: flex; gap: 12px; align-items: center;
      padding: 12px 16px; border-radius: 8px; margin-bottom: 16px;
      border: 1px solid transparent;
    }
    .callout.warning {
      background: var(--color-warning-bg); color: var(--color-warning-text);
      border-color: var(--color-warning-border);
    }
    .callout.info {
      background: var(--color-info-bg); color: var(--color-info-text);
    }

    .transcript {
      border: 1px solid var(--border-default);
      border-radius: 8px;
      background: var(--surface-sunken);
      padding: 16px;
      min-height: 280px;
      max-height: 480px;
      overflow-y: auto;
      display: flex; flex-direction: column; gap: 12px;
    }

    .turn { display: flex; }
    .turn.user { justify-content: flex-end; }
    .bubble {
      max-width: 78%;
      padding: 10px 14px;
      border-radius: 8px;
      background: var(--surface-default);
      border: 1px solid var(--border-default);
    }
    .turn.user .bubble {
      background: var(--color-accent-bg);
      border-color: var(--color-accent-bg);
    }
    .turn.error .bubble {
      background: var(--color-error-bg);
      border-color: var(--color-error-border);
      color: var(--color-error-text);
    }
    .who {
      display: block; font-size: 0.75rem; text-transform: uppercase;
      letter-spacing: 0.04em; color: var(--text-tertiary); margin-bottom: 4px;
    }
    .turn.error .who { color: inherit; }
    .bubble p { margin: 0; color: inherit; white-space: pre-wrap; overflow-wrap: anywhere; }
    .thinking { color: var(--text-tertiary); }

    .empty-state { margin: auto; text-align: center; color: var(--text-tertiary); }
    .empty-state mat-icon { font-size: 40px; height: 40px; width: 40px; }
    .empty-state p { margin: 8px 0 0; }

    .composer { display: flex; align-items: flex-start; gap: 12px; margin-top: 16px; }
    .composer button { margin-top: 18px; }
    .full-width { width: 100%; }

    .prompt-panel { margin-top: 20px; }
    .hop-code-panel { max-height: 320px; overflow: auto; }
    .hop-code-panel pre { white-space: pre-wrap; overflow-wrap: anywhere; }

    @media (max-width: 768px) {
      .composer { flex-direction: column; }
      .composer button { margin-top: 0; align-self: flex-end; }
      .bubble { max-width: 100%; }
    }
  `],
})
export class HopAgentChatComponent {
  private fb = inject(FormBuilder);
  private agentService = inject(HopAgentService);

  /** Null for an unsaved agent — there is nothing to talk to yet. */
  @Input() agentId: string | null = null;
  @Input() agentName = '';
  @Input() hasConfiguration = false;
  /** Whether the editor form has unsaved edits, so the panel can say so. */
  @Input() dirty = false;

  @ViewChild('transcript') private transcript?: ElementRef<HTMLElement>;

  turns: Turn[] = [];
  sending = false;
  systemPrompt = '';
  ranOn = '';

  form = this.fb.group({
    message: ['', Validators.required],
  });

  get canChat(): boolean { return !!this.agentId && this.hasConfiguration; }

  labelFor(turn: Turn): string {
    if (turn.role === 'user') return 'You';
    if (turn.role === 'error') return 'Error';
    return this.agentName || 'Agent';
  }

  clear(): void {
    this.turns = [];
    this.systemPrompt = '';
    this.ranOn = '';
  }

  send(): void {
    const message = (this.form.get('message')?.value ?? '').trim();
    if (!message || this.sending || !this.agentId) return;

    this.turns = [...this.turns, { role: 'user', content: message }];
    this.form.reset({ message: '' });
    this.sending = true;
    this.scrollToEnd();

    // Only real turns go back up; an error bubble is a UI artefact, and
    // sending it as history would confuse the model on the next message.
    const history: ChatMessage[] = this.turns
      .filter((t): t is Turn & { role: 'user' | 'assistant' } => t.role !== 'error')
      .map(t => ({ role: t.role, content: t.content }));

    this.agentService.chat(this.agentId, { messages: history }).subscribe({
      next: response => {
        this.sending = false;
        this.turns = [...this.turns, { role: 'assistant', content: response.message.content }];
        this.systemPrompt = response.system_prompt;
        this.ranOn = `${response.ai_configuration_name} — ${response.model}`;
        this.scrollToEnd();
      },
      error: error => {
        this.sending = false;
        this.turns = [...this.turns, {
          role: 'error',
          content: error?.error?.detail || 'The agent could not be reached.',
        }];
        this.scrollToEnd();
      },
    });
  }

  private scrollToEnd(): void {
    setTimeout(() => {
      const element = this.transcript?.nativeElement;
      if (element) element.scrollTop = element.scrollHeight;
    });
  }
}
