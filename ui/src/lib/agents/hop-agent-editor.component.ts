import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  FormArray, FormBuilder, FormGroup, ReactiveFormsModule, Validators,
} from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTabsModule } from '@angular/material/tabs';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { of } from 'rxjs';
import { catchError } from 'rxjs/operators';
import {
  Agent, AgentContextFile, AgentCreate, AiConfiguration, HopAgentService,
} from './hop-agent.service';
import { HopAgentChatComponent } from './hop-agent-chat.component';

@Component({
  selector: 'hop-agent-editor',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, MatButtonModule, MatIconModule, MatTabsModule,
    MatFormFieldModule, MatInputModule, MatSelectModule, MatSlideToggleModule,
    MatTooltipModule, MatProgressSpinnerModule, MatSnackBarModule,
    HopAgentChatComponent,
  ],
  template: `
    <div class="editor-container hop-page">
      <div class="loading-state" *ngIf="loading">
        <mat-spinner></mat-spinner>
        <p>Loading agent…</p>
      </div>

      <form [formGroup]="form" *ngIf="!loading">
        <div class="editor-header">
          <div class="heading">
            <button mat-icon-button type="button" matTooltip="Back to agents"
                    (click)="cancel()">
              <mat-icon>arrow_back</mat-icon>
            </button>
            <div>
              <h1>{{ isNew ? 'New Agent' : (agent?.name || 'Edit Agent') }}</h1>
              <p class="subtitle">
                Jobs and workflows give this agent input and instructions, and get its
                output back.
              </p>
            </div>
          </div>
        </div>

        <mat-tab-group>

          <!-- Configuration -->
          <mat-tab label="Configuration">
            <div class="tab-body">
              <div class="form-column">
                <mat-form-field appearance="outline" class="full-width">
                  <mat-label>Name</mat-label>
                  <input matInput formControlName="name" required
                         placeholder="Release Notes Writer">
                  <mat-error *ngIf="form.get('name')?.hasError('required')">
                    A name is required
                  </mat-error>
                </mat-form-field>

                <mat-form-field appearance="outline" class="full-width">
                  <mat-label>Description</mat-label>
                  <textarea matInput formControlName="description" rows="3"
                            placeholder="What this agent is for."></textarea>
                </mat-form-field>

                <mat-form-field appearance="outline" class="full-width">
                  <mat-label>AI Configuration</mat-label>
                  <mat-select formControlName="ai_configuration_id">
                    <mat-option [value]="null">None selected</mat-option>
                    <mat-option *ngFor="let configuration of aiConfigurations"
                                [value]="configuration.id">
                      {{ configuration.name }} ({{ configuration.provider_label }}{{
                        configuration.model ? ' — ' + configuration.model : '' }})
                    </mat-option>
                  </mat-select>
                  <mat-hint *ngIf="aiConfigurations.length > 0">
                    The model this agent runs on. Set up under credentials and shared
                    between agents.
                  </mat-hint>
                  <mat-hint *ngIf="aiConfigurations.length === 0">
                    No AI configurations yet — add one under credentials, then select it
                    here.
                  </mat-hint>
                </mat-form-field>

                <div class="toggle-row">
                  <mat-slide-toggle formControlName="is_active">Active</mat-slide-toggle>
                  <span class="field-hint">
                    Inactive agents stay configured but are not offered to jobs and
                    workflows.
                  </span>
                </div>

                <div class="tab-save-row">
                  <span class="error-text" *ngIf="configError">{{ configError }}</span>
                  <button mat-button type="button" (click)="cancel()">Cancel</button>
                  <button mat-raised-button color="primary" type="button"
                          [disabled]="form.invalid || saving" (click)="save()">
                    <mat-spinner diameter="20" *ngIf="saving"></mat-spinner>
                    <span *ngIf="!saving">{{ isNew ? 'Create Agent' : 'Save Changes' }}</span>
                  </button>
                </div>
              </div>
            </div>
          </mat-tab>

          <!-- Context files -->
          <mat-tab [label]="'Context (' + contextFiles.length + ')'">
            <div class="tab-body">

              <!-- List view -->
              <ng-container *ngIf="editingFileIndex === null">
                <div class="context-list-header">
                  <p class="field-hint">
                    Markdown the agent is given as reference on every run — style guides,
                    templates, domain background.
                  </p>
                  <button mat-stroked-button type="button" (click)="addContextFile()">
                    <mat-icon>add</mat-icon>
                    Add context file
                  </button>
                </div>

                <div class="empty-state" *ngIf="contextFiles.length === 0">
                  <mat-icon>description</mat-icon>
                  <p>No context files yet.</p>
                </div>

                <div class="context-file-list" *ngIf="contextFiles.length > 0">
                  <div class="context-file-list-item"
                       *ngFor="let file of contextFiles.controls; let i = index">
                    <div class="context-file-list-main" (click)="openContextFile(i)">
                      <div class="context-file-list-name">
                        {{ file.get('name')?.value || 'Untitled' }}
                      </div>
                      <div class="context-file-list-preview" *ngIf="filePreview(i)">
                        {{ filePreview(i) }}
                      </div>
                    </div>
                    <div class="context-file-list-controls">
                      <button mat-icon-button type="button" matTooltip="Move up"
                              [disabled]="i === 0" (click)="moveContextFile(i, -1)">
                        <mat-icon>arrow_upward</mat-icon>
                      </button>
                      <button mat-icon-button type="button" matTooltip="Move down"
                              [disabled]="i === contextFiles.length - 1"
                              (click)="moveContextFile(i, 1)">
                        <mat-icon>arrow_downward</mat-icon>
                      </button>
                    </div>
                  </div>
                </div>
              </ng-container>

              <!-- Edit view -->
              <div *ngIf="editingFileIndex !== null && editingFile"
                   [formGroup]="editingFile">
                <div class="context-file-edit-toolbar">
                  <button mat-icon-button type="button" matTooltip="Back to list"
                          (click)="closeContextFile()">
                    <mat-icon>arrow_back</mat-icon>
                  </button>
                  <div class="context-file-edit-actions">
                    <button mat-icon-button type="button" matTooltip="Remove file"
                            (click)="confirmRemoveContextFile(editingFileIndex)">
                      <mat-icon>delete</mat-icon>
                    </button>
                    <button mat-raised-button color="primary" type="button"
                            [disabled]="form.invalid || saving" (click)="saveContextFile()">
                      <mat-spinner diameter="20" *ngIf="saving"></mat-spinner>
                      <span *ngIf="!saving">Save</span>
                    </button>
                  </div>
                </div>
                <mat-form-field appearance="outline" class="full-width">
                  <mat-label>File name</mat-label>
                  <input matInput formControlName="name" required
                         placeholder="voice-and-tone.md">
                </mat-form-field>
                <mat-form-field appearance="outline" class="full-width">
                  <mat-label>Markdown</mat-label>
                  <textarea matInput formControlName="content" rows="20"
                            class="markdown-input" placeholder="# Heading"></textarea>
                </mat-form-field>
              </div>

            </div>
          </mat-tab>

          <!-- Permitted URLs -->
          <mat-tab [label]="'Reference URLs (' + permittedUrls.length + ')'">
            <div class="tab-body">
              <div class="form-column">
                <p class="field-hint">
                  URLs the agent may read for additional reference. A URL covers the pages
                  beneath it, so <code>https://docs.example.com/guide</code> also permits
                  <code>/guide/install</code>. Use <code>*.</code> before a host to cover
                  its subdomains.
                </p>

                <div class="url-add">
                  <mat-form-field appearance="outline" class="full-width">
                    <mat-label>Add a URL</mat-label>
                    <input matInput [formControl]="urlControl"
                           placeholder="https://docs.example.com/guide"
                           (keydown.enter)="addUrl(); $event.preventDefault()">
                    <mat-error *ngIf="urlControl.hasError('invalidUrl')">
                      Enter a full http:// or https:// URL
                    </mat-error>
                    <mat-error *ngIf="urlControl.hasError('duplicate')">
                      That URL is already on the list
                    </mat-error>
                  </mat-form-field>
                  <button mat-stroked-button type="button" (click)="addUrl()">Add</button>
                </div>

                <div class="empty-state" *ngIf="permittedUrls.length === 0">
                  <mat-icon>link_off</mat-icon>
                  <p>No URLs permitted. The agent works from its context files alone.</p>
                </div>

                <ul class="url-list" *ngIf="permittedUrls.length > 0">
                  <li *ngFor="let url of permittedUrls; let i = index">
                    <span class="url-text">{{ url }}</span>
                    <button mat-icon-button type="button" matTooltip="Remove URL"
                            (click)="removeUrl(i)">
                      <mat-icon>close</mat-icon>
                    </button>
                  </li>
                </ul>
              </div>
            </div>
          </mat-tab>

          <!-- Feedback memory -->
          <mat-tab label="Memory">
            <div class="tab-body">
              <p class="field-hint">
                What the agent has learned from feedback on its past work. Kept separate
                from context files: context is what the agent was given, memory is what it
                has picked up. Workflows append to this after a run is reviewed.
              </p>
              <mat-form-field appearance="outline" class="full-width">
                <mat-label>Feedback memory</mat-label>
                <textarea matInput formControlName="feedback_memory" rows="22"
                          class="markdown-input"
                          placeholder="### 2026-09-19&#10;&#10;Keep entries under two sentences."></textarea>
              </mat-form-field>
              <div class="tab-save-row">
                <span class="error-text" *ngIf="memoryError">{{ memoryError }}</span>
                <button mat-button type="button" (click)="cancel()">Cancel</button>
                <button mat-raised-button color="primary" type="button"
                        [disabled]="saving || isNew" (click)="saveMemory()">
                  <mat-spinner diameter="20" *ngIf="saving"></mat-spinner>
                  <span *ngIf="!saving">Save Changes</span>
                </button>
              </div>
            </div>
          </mat-tab>

          <!-- Test -->
          <mat-tab label="Test">
            <div class="tab-body">
              <hop-agent-chat
                [agentId]="agentId"
                [agentName]="agent?.name || form.get('name')?.value || ''"
                [hasConfiguration]="!!form.get('ai_configuration_id')?.value"
                [dirty]="form.dirty"></hop-agent-chat>
            </div>
          </mat-tab>

        </mat-tab-group>
      </form>
    </div>
  `,
  styles: [`

    .loading-state { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 64px 0; }
    .loading-state p { margin: 0; color: var(--text-secondary); }

    .editor-header {
      display: flex; justify-content: space-between; align-items: flex-start;
      gap: 24px; margin-bottom: 16px; flex-wrap: wrap;
    }
    .heading { display: flex; align-items: flex-start; gap: 8px; min-width: 0; }
    .heading h1 { margin: 0 0 4px; }
    .heading button { margin-top: 4px; }
    .subtitle { margin: 0; max-width: 60ch; color: var(--text-secondary); }

    .tab-body { padding: 24px 4px 8px; }
    /* Prose and single inputs stay readable; markdown gets the full width. */
    .form-column { max-width: 720px; }
    .full-width { width: 100%; }
    .field-hint { color: var(--text-tertiary); margin: 0 0 16px; max-width: 80ch; }
    .field-hint code { font-family: var(--font-mono); font-size: 0.9em; }
    .toggle-row { display: flex; align-items: center; gap: 12px; margin-top: 20px; flex-wrap: wrap; }
    .toggle-row .field-hint { margin: 0; }

    .context-list-header {
      display: flex; align-items: flex-start; justify-content: space-between; gap: 16px;
      margin-bottom: 16px;
    }
    .context-list-header .field-hint { margin: 0; }
    .context-list-header button { flex-shrink: 0; }

    .context-file-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
    .context-file-list-item {
      display: flex; align-items: stretch;
      border: 1px solid var(--border-default);
      border-radius: 8px;
      overflow: hidden;
    }
    .context-file-list-main {
      flex: 1; min-width: 0;
      padding: 12px 16px;
      cursor: pointer;
      transition: background 0.15s;
    }
    .context-file-list-main:hover { background: var(--surface-hover, var(--surface-default)); }
    .context-file-list-name { font-weight: 500; margin-bottom: 6px; }
    .context-file-list-preview {
      font-family: var(--font-mono);
      font-size: 0.82rem;
      color: var(--text-tertiary);
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      display: -webkit-box;
      -webkit-line-clamp: 4;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }
    .context-file-list-controls {
      display: flex; flex-direction: column; justify-content: center;
      padding: 4px;
      border-left: 1px solid var(--border-default);
    }

    .context-file-edit-toolbar {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 12px;
    }
    .context-file-edit-actions { display: flex; align-items: center; gap: 8px; }
    .markdown-input { font-family: var(--font-mono); font-size: 0.9rem; line-height: 1.5; }

    .url-add { display: flex; align-items: flex-start; gap: 12px; }
    .url-add button { margin-top: 18px; }
    .url-list { list-style: none; margin: 0; padding: 0; }
    .url-list li {
      display: flex; align-items: center; gap: 12px;
      padding: 6px 6px 6px 12px;
      border-bottom: 1px solid var(--border-light);
    }
    .url-list li:last-child { border-bottom: none; }
    .url-text {
      flex: 1; min-width: 0;
      font-family: var(--font-mono); font-size: 0.9rem;
      overflow-wrap: anywhere;
    }

    .empty-state { text-align: center; padding: 32px 16px; color: var(--text-tertiary); }
    .empty-state mat-icon { font-size: 40px; height: 40px; width: 40px; }
    .empty-state p { margin: 8px 0 0; }

    .tab-save-row {
      display: flex; align-items: center; justify-content: flex-end;
      gap: 12px; margin-top: 20px;
    }
    .error-text { color: var(--color-error-text); }

    @media (max-width: 768px) {
      .editor-header { flex-direction: column; }
    }
  `],
})
export class HopAgentEditorComponent implements OnInit {
  private fb = inject(FormBuilder);
  private agentService = inject(HopAgentService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private snackBar = inject(MatSnackBar);

  agent: Agent | null = null;
  aiConfigurations: AiConfiguration[] = [];
  permittedUrls: string[] = [];

  loading = false;
  saving = false;
  configError = '';
  memoryError = '';

  urlControl = this.fb.control('');

  form = this.fb.group({
    name: ['', Validators.required],
    description: [''],
    ai_configuration_id: this.fb.control<string | null>(null),
    is_active: [true],
    feedback_memory: [''],
    context_files: this.fb.array<FormGroup>([]),
  });

  /** Null until the agent is saved; the Test tab needs it to talk to one. */
  agentId: string | null = null;
  /** Index of the context file open for editing; null shows the list. */
  editingFileIndex: number | null = null;

  get isNew(): boolean { return !this.agentId; }
  get contextFiles(): FormArray<FormGroup> {
    return this.form.get('context_files') as FormArray<FormGroup>;
  }
  get editingFile(): FormGroup | null {
    return this.editingFileIndex !== null
      ? this.asGroup(this.contextFiles.at(this.editingFileIndex))
      : null;
  }

  ngOnInit(): void {
    this.loadAiConfigurations();

    // Read from paramMap rather than a snapshot so the page stays correct if
    // it is ever routed to from another agent without being torn down.
    this.route.paramMap.subscribe(params => {
      this.agentId = params.get('agentId');
      if (this.agentId) {
        this.loadAgent(this.agentId);
      } else {
        this.reset();
      }
    });
  }

  private reset(): void {
    this.agent = null;
    this.permittedUrls = [];
    this.configError = '';
    this.memoryError = '';
    this.editingFileIndex = null;
    this.urlControl.reset('');
    this.contextFiles.clear();
    this.form.reset({
      name: '', description: '', ai_configuration_id: null,
      is_active: true, feedback_memory: '',
    });
  }

  private loadAgent(agentId: string): void {
    this.loading = true;
    this.agentService.getAgent(agentId).subscribe({
      next: agent => {
        this.agent = agent;
        this.form.patchValue({
          name: agent.name,
          description: agent.description ?? '',
          ai_configuration_id: agent.ai_configuration_id ?? null,
          is_active: agent.is_active,
          feedback_memory: agent.feedback_memory ?? '',
        });

        this.permittedUrls = [...(agent.permitted_urls ?? [])];
        this.editingFileIndex = null;
        this.contextFiles.clear();
        for (const file of agent.context_files ?? []) {
          this.contextFiles.push(this.contextFileGroup(file));
        }
        this.loading = false;
      },
      error: () => {
        this.loading = false;
        this.snackBar.open('Failed to load agent', 'Close', { duration: 4000 });
        this.cancel();
      },
    });
  }

  /**
   * Only populates the select, so a failure here must not stop the agent
   * being edited — it falls back to an empty list.
   */
  private loadAiConfigurations(): void {
    this.agentService.listAiConfigurations().pipe(
      catchError(() => of([] as AiConfiguration[])),
    ).subscribe(configurations => { this.aiConfigurations = configurations; });
  }

  /** Narrowing helper — templates cannot call `as FormGroup`. */
  asGroup(control: any): FormGroup { return control as FormGroup; }

  private contextFileGroup(file?: AgentContextFile): FormGroup {
    return this.fb.group({
      name: [file?.name ?? '', Validators.required],
      content: [file?.content ?? ''],
    });
  }

  filePreview(index: number): string {
    const content = (this.contextFiles.at(index).get('content')?.value ?? '') as string;
    const trimmed = content.replace(/^\s+/, '');
    return trimmed.length > 600 ? trimmed.slice(0, 600) + '…' : trimmed;
  }

  openContextFile(index: number): void { this.editingFileIndex = index; }

  closeContextFile(): void { this.editingFileIndex = null; }

  addContextFile(): void {
    this.contextFiles.push(this.contextFileGroup());
    this.editingFileIndex = this.contextFiles.length - 1;
  }

  removeContextFileAndBack(index: number): void {
    this.contextFiles.removeAt(index);
    this.editingFileIndex = null;
  }

  confirmRemoveContextFile(index: number): void {
    const name = this.contextFiles.at(index).get('name')?.value || 'this file';
    if (window.confirm(`Delete "${name}"? This cannot be undone.`)) {
      this.contextFiles.removeAt(index);
      this.editingFileIndex = null;
      this.performSave();
    }
  }

  moveContextFile(index: number, offset: number): void {
    const target = index + offset;
    if (target < 0 || target >= this.contextFiles.length) return;
    const group = this.contextFiles.at(index);
    this.contextFiles.removeAt(index);
    this.contextFiles.insert(target, group);
    if (this.editingFileIndex === index) this.editingFileIndex = target;
  }

  addUrl(): void {
    const raw = (this.urlControl.value ?? '').trim();
    if (!raw) return;

    try {
      const parsed = new URL(raw);
      if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') throw new Error('scheme');
    } catch {
      this.urlControl.setErrors({ invalidUrl: true });
      return;
    }

    if (this.permittedUrls.includes(raw)) {
      this.urlControl.setErrors({ duplicate: true });
      return;
    }

    this.permittedUrls = [...this.permittedUrls, raw];
    this.urlControl.setValue('');
    this.urlControl.setErrors(null);
  }

  removeUrl(index: number): void {
    this.permittedUrls = this.permittedUrls.filter((_, i) => i !== index);
  }

  private buildPayload(): AgentCreate {
    const value = this.form.getRawValue();
    return {
      name: (value.name ?? '').trim(),
      description: (value.description ?? '').trim() || null,
      ai_configuration_id: value.ai_configuration_id ?? null,
      context_files: this.contextFiles.controls.map((group, index) => ({
        name: (group.get('name')?.value ?? '').trim(),
        content: group.get('content')?.value ?? '',
        position: index,
      })),
      permitted_urls: this.permittedUrls,
      feedback_memory: value.feedback_memory ?? '',
      is_active: value.is_active ?? true,
    };
  }

  private performSave(onSuccess?: () => void): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.configError = 'Check the highlighted fields.';
      return;
    }

    this.saving = true;
    this.configError = '';
    const payload = this.buildPayload();
    const wasNew = this.isNew;

    const request = this.agentId
      ? this.agentService.updateAgent(this.agentId, payload)
      : this.agentService.createAgent(payload);

    request.subscribe({
      next: (agent) => {
        this.saving = false;
        this.agent = agent;
        this.agentId = agent.id;
        this.form.markAsPristine();
        this.snackBar.open(
          wasNew ? 'Agent created' : 'Agent saved', 'Close', { duration: 3000 },
        );
        if (wasNew) {
          this.router.navigate(['..', agent.id], { relativeTo: this.route });
        }
        onSuccess?.();
      },
      error: error => {
        this.saving = false;
        this.configError = error?.error?.detail || 'Failed to save agent.';
      },
    });
  }

  save(): void { this.performSave(); }

  saveContextFile(): void { this.performSave(() => { this.editingFileIndex = null; }); }

  saveMemory(): void {
    if (this.saving || !this.agentId) return;
    this.saving = true;
    this.memoryError = '';
    this.agentService.updateAgent(this.agentId, {
      feedback_memory: this.form.get('feedback_memory')?.value ?? '',
    }).subscribe({
      next: (agent) => {
        this.saving = false;
        this.agent = agent;
        this.form.get('feedback_memory')?.markAsPristine();
        this.snackBar.open('Memory saved', 'Close', { duration: 3000 });
      },
      error: error => {
        this.saving = false;
        this.memoryError = error?.error?.detail || 'Failed to save memory.';
      },
    });
  }

  /** Back to the agent list, wherever the app mounted it. */
  cancel(): void {
    this.router.navigate(['..'], { relativeTo: this.route });
  }
}
