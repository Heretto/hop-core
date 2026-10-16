import { Component, inject, OnInit, ChangeDetectionStrategy, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  FormArray, FormBuilder, FormGroup, ReactiveFormsModule, Validators,
} from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTabsModule } from '@angular/material/tabs';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { of } from 'rxjs';
import { catchError } from 'rxjs/operators';
import {
  Agent, AgentContextFile, AgentCreate, AgentReference, AgentReferenceType, AiConfiguration,
  HerettoConnection, HopAgentService,
} from './hop-agent.service';

/** The Heretto reference types and how each reaches the agent. */
const REFERENCE_TYPES: { value: AgentReferenceType; label: string }[] = [
  { value: 'general', label: 'General content' },
  { value: 'style_guide', label: 'Style guide' },
  { value: 'information_model', label: 'Information model' },
  { value: 'terminology', label: 'Terminology / glossary' },
];
/** The DTD Set select's "Organization default" choice; saved as null. */
const FOLLOW_DEFAULT = '';
const INCLUDED_TYPES: AgentReferenceType[] = ['style_guide', 'information_model', 'terminology'];
import { HopAgentChatComponent } from './hop-agent-chat.component';
import { HopAccountService } from '../shared/hop-account.service';
import {
  DtdSetDetail, DtdSetList, HopDtdSetService, dtdSetOptionLabel, dtdSetUsable,
} from '../dtd-sets/hop-dtd-set.service';

@Component({
  changeDetection: ChangeDetectionStrategy.Eager,
  selector: 'hop-agent-editor',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, MatButtonModule, MatIconModule, MatTabsModule,
    MatFormFieldModule, MatInputModule, MatSelectModule, MatButtonToggleModule, MatSlideToggleModule,
    MatTooltipModule, MatProgressSpinnerModule, MatSnackBarModule,
    HopAgentChatComponent, RouterLink,
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

                <ng-container *ngIf="dtdSets">
                  <mat-form-field appearance="outline" class="full-width">
                    <mat-label>DTD Set</mat-label>
                    <mat-select formControlName="dtd_set_id">
                      <mat-option [value]="followDefault">Organization default ({{ defaultSetLabel() }})</mat-option>
                      <mat-option *ngFor="let set of dtdSets.sets" [value]="set.id" [disabled]="!dtdSetUsable(set)">
                        {{ dtdSetOptionLabel(set) }}
                      </mat-option>
                    </mat-select>
                    <mat-hint>
                      The DTDs this agent validates DITA content against.<ng-container *ngIf="isAdmin$ | async"> Managed under
                      <a routerLink="/admin" [queryParams]="{ section: 'dtd-sets' }">Administration › DTD sets</a>.</ng-container>
                    </mat-hint>
                  </mat-form-field>
                  <div class="dtd-info" *ngIf="effectiveSet as set">
                    <ng-container *ngIf="!form.get('dtd_set_id')?.value">Follows the organization default if an admin changes it. </ng-container>
                    {{ dtdSetSummary(set) }}
                    <span class="dtd-warning" *ngIf="set.issues.length">
                      ⚠ {{ set.issues.length }} warning{{ set.issues.length === 1 ? '' : 's' }}: {{ set.issues[0].title }}.
                      <a *ngIf="isAdmin$ | async" [routerLink]="['/admin/dtd-sets', set.id]">Review warnings</a>
                    </span>
                  </div>
                </ng-container>

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

          <!-- References -->
          <mat-tab [label]="'References (' + references.length + ')'">
            <div class="tab-body">
              <div class="form-column">
                <p class="field-hint">
                  Material the agent can draw on: URLs it may read, and files in Heretto.
                  Guidance on each one tells the agent how to use it.
                </p>

                <div class="reference-add">
                  <mat-button-toggle-group [value]="addKind" (change)="setAddKind($event.value)"
                                           aria-label="Kind of reference to add">
                    <mat-button-toggle value="url"><mat-icon>link</mat-icon> URL</mat-button-toggle>
                    <mat-button-toggle value="heretto"><mat-icon>menu_book</mat-icon> Heretto</mat-button-toggle>
                  </mat-button-toggle-group>

                  <ng-container *ngIf="addKind === 'url'">
                    <mat-form-field appearance="outline" class="full-width">
                      <mat-label>URL</mat-label>
                      <input matInput [formControl]="urlControl"
                             placeholder="https://docs.example.com/guide"
                             (keydown.enter)="addReference(); $event.preventDefault()">
                      <mat-hint>
                        Covers the pages beneath it. Put <code>*.</code> before a host to cover its subdomains.
                      </mat-hint>
                      <mat-error *ngIf="urlControl.hasError('invalidUrl')">
                        Enter a full http:// or https:// URL
                      </mat-error>
                      <mat-error *ngIf="urlControl.hasError('duplicate')">
                        That URL is already on the list
                      </mat-error>
                    </mat-form-field>
                  </ng-container>

                  <ng-container *ngIf="addKind === 'heretto'">
                    <p class="notice" *ngIf="herettoConnections.length === 0">
                      <mat-icon>info</mat-icon>
                      No Heretto connection is set up. Add one under Credentials to reference
                      content in Heretto.
                    </p>
                    <ng-container *ngIf="herettoConnections.length > 0">
                      <mat-form-field appearance="outline" class="full-width"
                                      *ngIf="herettoConnections.length > 1">
                        <mat-label>Heretto connection</mat-label>
                        <mat-select [formControl]="herettoConnectionControl">
                          <mat-option *ngFor="let c of herettoConnections" [value]="c.id">
                            {{ c.name }}
                          </mat-option>
                        </mat-select>
                      </mat-form-field>
                      <mat-form-field appearance="outline" class="full-width">
                        <mat-label>Heretto file</mat-label>
                        <input matInput [formControl]="herettoIdControl"
                               placeholder="File ID, Heretto URL, or repository path"
                               (keydown.enter)="addReference(); $event.preventDefault()">
                        <mat-hint *ngIf="!herettoError">
                          A topic or a map — a map brings in every topic it links to.
                        </mat-hint>
                      </mat-form-field>
                      <p class="error-text field-error" *ngIf="herettoError">{{ herettoError }}</p>
                      <mat-form-field appearance="outline" class="full-width">
                        <mat-label>Type</mat-label>
                        <mat-select [formControl]="newTypeControl">
                          <mat-option *ngFor="let t of referenceTypes" [value]="t.value">{{ t.label }}</mat-option>
                        </mat-select>
                        <mat-hint>{{ deliveryHint(newTypeControl.value) }}</mat-hint>
                      </mat-form-field>
                    </ng-container>
                  </ng-container>

                  <mat-form-field appearance="outline" class="full-width"
                                  *ngIf="addKind === 'url' || herettoConnections.length > 0">
                    <mat-label>Guidance (optional)</mat-label>
                    <textarea matInput [formControl]="newGuidanceControl" rows="2"
                              placeholder="How should the agent use this? e.g. 'Check product names against this.'"></textarea>
                  </mat-form-field>

                  <div class="add-row" *ngIf="addKind === 'url' || herettoConnections.length > 0">
                    <button mat-stroked-button type="button" [disabled]="resolving" (click)="addReference()">
                      <mat-spinner diameter="18" *ngIf="resolving"></mat-spinner>
                      <span *ngIf="!resolving">Add reference</span>
                    </button>
                  </div>
                </div>

                <div class="empty-state" *ngIf="references.length === 0">
                  <mat-icon>link_off</mat-icon>
                  <p>No references. The agent works from its context files alone.</p>
                </div>

                <ul class="reference-list" *ngIf="references.length > 0">
                  <li *ngFor="let ref of references; let i = index"
                      [class.unavailable]="ref.kind === 'heretto' && ref.available === false">
                    <mat-icon class="ref-icon">{{ referenceIcon(ref) }}</mat-icon>
                    <div class="ref-main">
                      <div class="ref-title" [class.mono]="ref.kind === 'url'">{{ referenceTitle(ref) }}</div>
                      <div class="ref-meta" *ngIf="ref.kind === 'heretto'">
                        <span *ngIf="ref.is_map">Map · includes every topic it links to · </span>
                        <span *ngIf="ref.path" class="mono">{{ ref.path }}</span>
                        <span *ngIf="ref.credential_name"> · {{ ref.credential_name }}</span>
                      </div>
                      <p class="error-text" *ngIf="ref.kind === 'heretto' && ref.available === false">
                        Its Heretto connection was deleted, so the agent can't read it. Remove it,
                        then add it again through another connection.
                      </p>
                      <div class="ref-type" *ngIf="ref.kind === 'heretto'">
                        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="type-field">
                          <mat-label>Type</mat-label>
                          <mat-select [value]="ref.reference_type || 'general'"
                                      (selectionChange)="setReferenceType(i, $event.value)">
                            <mat-option *ngFor="let t of referenceTypes" [value]="t.value">{{ t.label }}</mat-option>
                          </mat-select>
                        </mat-form-field>
                        <span class="delivery">
                          <mat-icon>{{ isIncluded(ref.reference_type) ? 'push_pin' : 'travel_explore' }}</mat-icon>
                          {{ deliveryHint(ref.reference_type) }}
                        </span>
                      </div>
                      <mat-form-field appearance="outline" subscriptSizing="dynamic" class="full-width">
                        <mat-label>Guidance (optional)</mat-label>
                        <textarea matInput rows="2" [value]="ref.guidance"
                                  (input)="setReferenceGuidance(i, $any($event.target).value)"
                                  placeholder="How should the agent use this?"></textarea>
                      </mat-form-field>
                    </div>
                    <button mat-icon-button type="button" matTooltip="Remove reference"
                            [attr.aria-label]="'Remove ' + referenceTitle(ref)"
                            (click)="removeReference(i)">
                      <mat-icon>close</mat-icon>
                    </button>
                  </li>
                </ul>

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

    .dtd-info, .reference-add { padding: 16px; border-radius: 8px; background: var(--surface-sunken); }
    .dtd-info { margin: 4px 0 16px; color: var(--text-secondary); }
    .dtd-warning { display: block; margin-top: 6px; color: var(--color-warning-text); }
    .reference-add { margin-bottom: 20px; border: 1px solid var(--border-default); }
    .reference-add mat-button-toggle mat-icon { font-size: 18px; height: 18px; width: 18px; vertical-align: -4px; }
    .add-row { display: flex; justify-content: flex-end; }
    .notice {
      display: flex; gap: 8px; align-items: flex-start; margin: 16px 0 4px;
      color: var(--text-secondary);
    }
    .notice mat-icon { color: var(--color-info); flex: none; }
    .field-error { margin: -4px 0 8px; font-size: 0.82rem; }
    .reference-list { list-style: none; margin: 0; padding: 0; }
    .reference-list li {
      display: flex; align-items: flex-start; gap: 12px;
      padding: 14px 4px;
      border-bottom: 1px solid var(--border-light);
    }
    .reference-list li:last-child { border-bottom: none; }
    .reference-list li.unavailable .ref-icon { color: var(--color-error); }
    .ref-icon { color: var(--text-tertiary); flex: none; margin-top: 2px; }
    .ref-main { flex: 1; min-width: 0; }
    .ref-title { font-weight: 600; color: var(--text-primary); overflow-wrap: anywhere; }
    .ref-meta { color: var(--text-tertiary); font-size: 0.82rem; margin-top: 2px; overflow-wrap: anywhere; }
    .mono { font-family: var(--font-mono); font-size: 0.86rem; font-weight: 400; }
    .ref-type { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
    .type-field { width: 240px; max-width: 100%; }
    .delivery {
      display: inline-flex; align-items: center; gap: 4px; margin-top: 12px;
      color: var(--text-secondary); font-size: 0.82rem;
    }
    .delivery mat-icon { font-size: 16px; height: 16px; width: 16px; color: var(--text-tertiary); }

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
  private cdr = inject(ChangeDetectorRef);
  private dtdSetService = inject(HopDtdSetService);
  readonly isAdmin$ = inject(HopAccountService).isAdmin$;

  /** Null when the app didn't mount the DTD-set routes; the field is hidden. */
  dtdSets: DtdSetList | null = null;
  /** The set that applies with the current selection (the default when none). */
  effectiveSet: DtdSetDetail | null = null;
  readonly dtdSetUsable = dtdSetUsable;
  readonly followDefault = FOLLOW_DEFAULT;
  readonly dtdSetOptionLabel = dtdSetOptionLabel;

  agent: Agent | null = null;
  aiConfigurations: AiConfiguration[] = [];
  herettoConnections: HerettoConnection[] = [];
  references: AgentReference[] = [];
  readonly referenceTypes = REFERENCE_TYPES;

  loading = false;
  saving = false;
  configError = '';
  memoryError = '';

  addKind: 'url' | 'heretto' = 'url';
  urlControl = this.fb.control('');
  herettoConnectionControl = this.fb.control<string | null>(null);
  herettoIdControl = this.fb.control('');
  newTypeControl = this.fb.control<AgentReferenceType>('general');
  newGuidanceControl = this.fb.control('');
  resolving = false;
  herettoError = '';

  form = this.fb.group({
    name: ['', Validators.required],
    description: [''],
    ai_configuration_id: this.fb.control<string | null>(null),
    // FOLLOW_DEFAULT rather than null: mat-select shows nothing for a null value.
    dtd_set_id: this.fb.control<string>(FOLLOW_DEFAULT),
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
    this.loadHerettoConnections();
    this.loadDtdSets();
    this.form.get('dtd_set_id')!.valueChanges.subscribe(() => this.loadEffectiveSet());

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
    this.references = [];
    this.resetAddForm();
    this.configError = '';
    this.memoryError = '';
    this.editingFileIndex = null;
    this.urlControl.reset('');
    this.contextFiles.clear();
    this.form.reset({
      name: '', description: '', ai_configuration_id: null, dtd_set_id: FOLLOW_DEFAULT,
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
          dtd_set_id: agent.dtd_set_id ?? FOLLOW_DEFAULT,
          is_active: agent.is_active,
          feedback_memory: agent.feedback_memory ?? '',
        });

        this.references = (agent.references ?? []).map(ref => ({ ...ref, guidance: ref.guidance ?? '' }));
        this.editingFileIndex = null;
        this.contextFiles.clear();
        for (const file of agent.context_files ?? []) {
          this.contextFiles.push(this.contextFileGroup(file));
        }
        this.loading = false;
        this.cdr.markForCheck();
      },
      error: () => {
        this.loading = false;
        this.snackBar.open('Failed to load agent', 'Close', { duration: 4000 });
        this.cdr.markForCheck();
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
    ).subscribe(configurations => { this.aiConfigurations = configurations; this.cdr.markForCheck(); });
  }

  private loadDtdSets(): void {
    this.dtdSetService.list().subscribe({
      next: list => { this.dtdSets = list; this.loadEffectiveSet(); this.cdr.markForCheck(); },
      error: () => { this.dtdSets = null; this.cdr.markForCheck(); },
    });
  }

  private loadEffectiveSet(): void {
    if (!this.dtdSets) return;
    const id = this.form.get('dtd_set_id')?.value || this.dtdSets.default_id;
    this.dtdSetService.get(id).subscribe({
      next: set => { this.effectiveSet = set; this.cdr.markForCheck(); },
      error: () => { this.effectiveSet = null; this.cdr.markForCheck(); },
    });
  }

  defaultSetLabel(): string {
    const set = this.dtdSets?.sets.find(s => s.id === this.dtdSets?.default_id);
    return set ? (set.builtin ? set.name : this.dtdSetOptionLabel(set)) : '';
  }

  /** "Validates 31 document types: the DITA 1.3 base types plus 7 specializations, including apiRef, …" */
  dtdSetSummary(set: DtdSetDetail): string {
    const total = set.document_types.length;
    const specialized = set.document_types.filter(t => t.kind === 'specialized');
    if (!specialized.length) {
      return `Validates ${total} standard ${set.builtin ? 'OASIS DITA 1.3' : (set.based_on ?? 'DITA')} document types.`;
    }
    const names = specialized.slice(0, 3).map(t => t.root);
    const list = names.length > 1 ? `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}` : names[0];
    const base = set.based_on ? `the ${set.based_on} base types` : 'the base types';
    return `Validates ${total} document types: ${base} plus ${specialized.length} specialization${specialized.length === 1 ? '' : 's'}, including ${list}.`;
  }

  /** Only populates the Heretto picker; a failure leaves it empty. */
  private loadHerettoConnections(): void {
    this.agentService.listHerettoConnections().pipe(
      catchError(() => of([] as HerettoConnection[])),
    ).subscribe(connections => {
      this.herettoConnections = connections;
      if (!this.herettoConnectionControl.value && connections.length) {
        this.herettoConnectionControl.setValue(connections[0].id);
      }
      this.cdr.markForCheck();
    });
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

  setAddKind(kind: 'url' | 'heretto'): void {
    this.addKind = kind;
    this.herettoError = '';
  }

  isIncluded(type: AgentReferenceType | null | undefined): boolean {
    return INCLUDED_TYPES.includes((type ?? 'general') as AgentReferenceType);
  }

  deliveryHint(type: AgentReferenceType | null | undefined): string {
    return this.isIncluded(type)
      ? 'Included in full in every run'
      : 'Listed for the agent, which reads it when a task needs it';
  }

  referenceIcon(ref: AgentReference): string {
    if (ref.kind === 'url') return 'link';
    if (ref.available === false) return 'link_off';
    return ref.is_map ? 'account_tree' : 'description';
  }

  referenceTitle(ref: AgentReference): string {
    return ref.kind === 'url' ? (ref.url ?? '') : (ref.title || ref.file_id || 'Heretto file');
  }

  addReference(): void {
    if (this.addKind === 'url') {
      this.addUrlReference();
    } else {
      this.addHerettoReference();
    }
  }

  private addUrlReference(): void {
    const raw = (this.urlControl.value ?? '').trim();
    if (!raw) return;

    try {
      const parsed = new URL(raw);
      if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') throw new Error('scheme');
    } catch {
      this.urlControl.setErrors({ invalidUrl: true });
      this.urlControl.markAsTouched();
      return;
    }

    if (this.references.some(ref => ref.kind === 'url' && ref.url === raw)) {
      this.urlControl.setErrors({ duplicate: true });
      this.urlControl.markAsTouched();
      return;
    }

    this.pushReference({ kind: 'url', url: raw, guidance: this.newGuidance() });
  }

  /** Checked against Heretto before it is added, so a typo shows up now
   *  rather than on the agent's next run. */
  private addHerettoReference(): void {
    const identifier = (this.herettoIdControl.value ?? '').trim();
    const credentialId = this.herettoConnectionControl.value;
    if (!identifier || !credentialId || this.resolving) return;

    this.resolving = true;
    this.herettoError = '';
    this.agentService.resolveHerettoReference(credentialId, identifier).subscribe({
      next: file => {
        this.resolving = false;
        const duplicate = this.references.some(
          ref => ref.kind === 'heretto' && ref.credential_id === credentialId && ref.file_id === file.file_id,
        );
        if (duplicate) {
          this.herettoError = `${file.title} is already on the list.`;
        } else {
          this.pushReference({
            kind: 'heretto',
            credential_id: credentialId,
            credential_name: this.herettoConnections.find(c => c.id === credentialId)?.name ?? null,
            file_id: file.file_id,
            title: file.title,
            path: file.path ?? null,
            is_map: file.is_map,
            reference_type: this.newTypeControl.value ?? 'general',
            guidance: this.newGuidance(),
            available: true,
          });
        }
        this.cdr.markForCheck();
      },
      error: error => {
        this.resolving = false;
        this.herettoError = error?.error?.detail || 'Could not check that file in Heretto.';
        this.cdr.markForCheck();
      },
    });
  }

  private newGuidance(): string {
    return (this.newGuidanceControl.value ?? '').trim();
  }

  private pushReference(ref: AgentReference): void {
    this.references = [...this.references, ref];
    this.resetAddForm();
    this.form.markAsDirty();
  }

  private resetAddForm(): void {
    this.urlControl.reset('');
    this.herettoIdControl.reset('');
    this.newGuidanceControl.reset('');
    this.newTypeControl.reset('general');
    this.herettoError = '';
  }

  removeReference(index: number): void {
    this.references = this.references.filter((_, i) => i !== index);
    this.form.markAsDirty();
  }

  setReferenceType(index: number, type: AgentReferenceType): void {
    this.references = this.references.map((ref, i) => i === index ? { ...ref, reference_type: type } : ref);
    this.form.markAsDirty();
  }

  setReferenceGuidance(index: number, guidance: string): void {
    // Mutated in place: replacing the object would re-render the textarea
    // being typed in and drop the cursor.
    this.references[index].guidance = guidance;
    this.form.markAsDirty();
  }

  private buildPayload(): AgentCreate {
    const value = this.form.getRawValue();
    return {
      name: (value.name ?? '').trim(),
      description: (value.description ?? '').trim() || null,
      ai_configuration_id: value.ai_configuration_id ?? null,
      // Only sent when the app has DTD sets, so an app without them never clears a choice.
      ...(this.dtdSets ? { dtd_set_id: value.dtd_set_id || null } : {}),
      context_files: this.contextFiles.controls.map((group, index) => ({
        name: (group.get('name')?.value ?? '').trim(),
        content: group.get('content')?.value ?? '',
        position: index,
      })),
      references: this.references.map(ref => ({
        kind: ref.kind,
        url: ref.kind === 'url' ? ref.url : null,
        credential_id: ref.kind === 'heretto' ? ref.credential_id ?? null : null,
        file_id: ref.kind === 'heretto' ? ref.file_id : null,
        title: ref.kind === 'heretto' ? ref.title : null,
        path: ref.kind === 'heretto' ? ref.path : null,
        is_map: ref.kind === 'heretto' ? !!ref.is_map : false,
        reference_type: ref.kind === 'heretto' ? ref.reference_type ?? 'general' : null,
        guidance: (ref.guidance ?? '').trim(),
      })),
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
        // The server's copy carries IDs and connection names for new references.
        this.references = (agent.references ?? []).map(ref => ({ ...ref, guidance: ref.guidance ?? '' }));
        this.form.markAsPristine();
        this.snackBar.open(
          wasNew ? 'Agent created' : 'Agent saved', 'Close', { duration: 3000 },
        );
        this.cdr.markForCheck();
        if (wasNew) {
          this.router.navigate(['..', agent.id], { relativeTo: this.route });
        }
        onSuccess?.();
      },
      error: error => {
        this.saving = false;
        this.configError = error?.error?.detail || 'Failed to save agent.';
        this.cdr.markForCheck();
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
        this.cdr.markForCheck();
      },
      error: error => {
        this.saving = false;
        this.memoryError = error?.error?.detail || 'Failed to save memory.';
        this.cdr.markForCheck();
      },
    });
  }

  /** Back to the agent list, wherever the app mounted it. */
  cancel(): void {
    this.router.navigate(['..'], { relativeTo: this.route });
  }
}
