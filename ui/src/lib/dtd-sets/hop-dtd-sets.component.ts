import {
  ChangeDetectionStrategy, ChangeDetectorRef, Component, DestroyRef, EventEmitter, OnInit, Output, inject,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { Subscription, timer } from 'rxjs';
import { HopConfirmDialogComponent } from '../shared/hop-confirm-dialog.component';
import {
  DtdSetList, DtdSetSummary, HopDtdSetService, dtdSetOptionLabel, dtdSetUsable,
} from './hop-dtd-set.service';
import {
  HopDtdUploadDialogComponent, HopDtdUploadDialogData, HopDtdUploadDialogResult,
} from './hop-dtd-upload-dialog.component';

/** Steps in processing, for "Processing · step 4 of 6". */
const STEP_COUNT = 6;

/**
 * The DTD sets section of the admin page: the organization default, every
 * set with its status, and uploading. `HopAdminComponent` hosts it; it can
 * also be placed on any admin-guarded page.
 */
@Component({
  changeDetection: ChangeDetectionStrategy.Eager,
  selector: 'hop-dtd-sets',
  standalone: true,
  imports: [
    CommonModule, MatButtonModule, MatIconModule, MatMenuModule, MatFormFieldModule,
    MatSelectModule, MatProgressSpinnerModule, MatDialogModule, MatSnackBarModule,
  ],
  template: `
    <div class="section-head">
      <div>
        <h2>DTD sets</h2>
        <p class="section-intro">
          Document type definitions that apps and agents use to validate DITA content. Upload a
          zip of your DTDs with an XML catalog; Hop checks the package and compiles it so it's
          ready for validation.
        </p>
      </div>
      <button mat-raised-button color="primary" (click)="openUpload()">
        <mat-icon>upload</mat-icon> Upload DTD set
      </button>
    </div>

    <div class="loading" *ngIf="!list"><mat-spinner diameter="32"></mat-spinner></div>

    <ng-container *ngIf="list">
      <div class="default-card">
        <div>
          <h3>Organization default</h3>
          <p>Used by every app and agent that doesn't choose its own DTD set.</p>
        </div>
        <mat-form-field appearance="outline" class="default-field">
          <mat-label>Default DTD set</mat-label>
          <mat-select [value]="list.default_id" (selectionChange)="setDefault($event.value)">
            <mat-option *ngFor="let set of list.sets" [value]="set.id" [disabled]="!usable(set)">
              {{ optionLabel(set) }}
            </mat-option>
          </mat-select>
        </mat-form-field>
      </div>

      <div class="table-card">
        <table class="sets-table">
          <thead>
            <tr>
              <th>Name</th><th>Based on</th><th>Document types</th><th>Status</th>
              <th>Used by</th><th>Updated</th><th><span class="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            <tr *ngFor="let set of list.sets" (click)="open(set)" class="set-row">
              <td>
                <div class="set-name">{{ set.name }}</div>
                <span class="tag" *ngIf="set.is_default">Default</span>
                <span class="tag" *ngIf="set.builtin">Built in</span>
                <div class="meta" *ngIf="set.builtin">Included with Hop</div>
                <div class="meta" *ngIf="!set.builtin && set.version_label">
                  {{ set.version_label }} · {{ set.filename }}
                </div>
                <div class="meta error" *ngIf="set.status === 'failed' && set.latest_error">{{ set.latest_error }}</div>
                <div class="meta" *ngIf="set.latest_status === 'processing' && set.status === 'ready'">
                  {{ set.latest_label }} processing
                </div>
                <div class="meta error" *ngIf="set.latest_status === 'failed' && set.status === 'ready'">
                  {{ set.latest_label }} failed
                </div>
              </td>
              <td>{{ set.based_on || '—' }}</td>
              <td>
                <div>{{ set.document_type_count ?? '—' }}</div>
                <div class="meta">{{ typesNote(set) }}</div>
              </td>
              <td>
                <span class="hop-status-chip" [ngClass]="statusClass(set)">
                  <mat-icon *ngIf="set.status !== 'processing'">{{ statusIcon(set) }}</mat-icon>
                  <mat-spinner *ngIf="set.status === 'processing'" diameter="12"></mat-spinner>
                  {{ statusLabel(set) }}
                </span>
              </td>
              <td>{{ set.used_by ? set.used_by + (set.used_by === 1 ? ' agent' : ' agents') : '—' }}</td>
              <td class="nowrap">{{ updatedLabel(set) }}</td>
              <td class="actions" (click)="$event.stopPropagation()">
                <button mat-icon-button [matMenuTriggerFor]="menu" [attr.aria-label]="'Actions for ' + set.name">
                  <mat-icon>more_vert</mat-icon>
                </button>
                <mat-menu #menu="matMenu">
                  <button mat-menu-item (click)="open(set)"><mat-icon>open_in_new</mat-icon> Open</button>
                  <button mat-menu-item (click)="setDefault(set.id)" [disabled]="set.is_default || !usable(set)">
                    <mat-icon>check_circle</mat-icon> Make organization default
                  </button>
                  <ng-container *ngIf="!set.builtin">
                    <button mat-menu-item (click)="openUpload(set)"><mat-icon>upload</mat-icon> Upload new version</button>
                    <button mat-menu-item (click)="remove(set)" [disabled]="set.is_default || set.used_by > 0">
                      <mat-icon>delete</mat-icon> Delete
                    </button>
                  </ng-container>
                </mat-menu>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="guide">
        <div>
          <h4>One zip per set</h4>
          <p>Up to {{ list.max_upload_mb }} MB. Folder structure is kept, so relative references between files keep working.</p>
        </div>
        <div>
          <h4>Shells and modules</h4>
          <p>Include every <code>.dtd</code>, <code>.mod</code> and <code>.ent</code> file your document types need.</p>
        </div>
        <div>
          <h4>An XML catalog</h4>
          <p>A <code>catalog.xml</code> mapping public IDs to files. Hop uses it to find each document type.</p>
        </div>
      </div>
    </ng-container>
  `,
  styles: [`
    :host { display: block; }
    .section-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; }
    .section-head h2 { margin: 0 0 4px; }
    .section-intro { margin: 0; color: var(--text-secondary); max-width: 640px; }
    .loading { display: flex; justify-content: center; padding: 48px; }
    .default-card, .table-card, .guide {
      margin-top: 20px; border: 1px solid var(--card-border); border-radius: 12px; background: var(--card-bg);
    }
    .default-card { display: flex; justify-content: space-between; align-items: center; gap: 24px; padding: 8px 24px; }
    .default-card h3 { margin: 0; font-size: 1rem; }
    .default-card p { margin: 2px 0 0; color: var(--text-secondary); }
    .default-field { width: 340px; max-width: 100%; }
    .table-card { overflow-x: auto; }
    .sets-table { width: 100%; border-collapse: collapse; }
    .sets-table th {
      text-align: left; padding: 14px 16px; white-space: nowrap;
      color: var(--text-tertiary); font-size: 0.72rem; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.04em; border-bottom: 1px solid var(--border-default);
    }
    .sets-table td { padding: 14px 16px; vertical-align: top; border-bottom: 1px solid var(--border-light); }
    .sets-table tr:last-child td { border-bottom: none; }
    .set-row { cursor: pointer; }
    .set-row:hover td { background: var(--hover-overlay); }
    .set-name { font-weight: 600; color: var(--text-primary); }
    .tag {
      display: inline-block; margin: 4px 6px 0 0; padding: 1px 8px; border-radius: 9999px;
      background: var(--button-secondary-bg); font-size: 0.72rem; font-weight: 600; color: var(--text-secondary);
    }
    .meta { color: var(--text-tertiary); font-size: 0.82rem; margin-top: 2px; overflow-wrap: anywhere; }
    .meta.error { color: var(--color-error-text); }
    .hop-status-chip { display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; }
    .hop-status-chip mat-icon { font-size: 14px; width: 14px; height: 14px; }
    .actions { width: 48px; }
    .nowrap { white-space: nowrap; }
    .guide { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; padding: 20px 24px; background: var(--surface-sunken); border: none; }
    .guide h4 { margin: 0 0 4px; font-size: 0.9rem; }
    .guide p { margin: 0; color: var(--text-secondary); font-size: 0.86rem; }
    .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
    @media (max-width: 900px) {
      .section-head, .default-card { flex-direction: column; align-items: stretch; }
      .guide { grid-template-columns: 1fr; }
    }
  `],
})
export class HopDtdSetsComponent implements OnInit {
  private service = inject(HopDtdSetService);
  private dialog = inject(MatDialog);
  private snackBar = inject(MatSnackBar);
  private router = inject(Router);
  private cdr = inject(ChangeDetectorRef);

  /** The number of sets (built-in included), for the admin nav's count. */
  @Output() countChange = new EventEmitter<number>();

  list: DtdSetList | null = null;
  private refresh?: Subscription;

  constructor() {
    inject(DestroyRef).onDestroy(() => this.refresh?.unsubscribe());
  }

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.service.list().subscribe({
      next: list => {
        this.list = list;
        this.countChange.emit(list.sets.length);
        this.scheduleRefresh();
        this.cdr.markForCheck();
      },
      error: () => this.snackBar.open('Failed to load DTD sets', 'Close', { duration: 4000 }),
    });
  }

  /** Keep the list live while anything is processing. */
  private scheduleRefresh(): void {
    this.refresh?.unsubscribe();
    const processing = this.list?.sets.some(s => s.status === 'processing' || s.latest_status === 'processing');
    if (processing) {
      this.refresh = timer(3000).subscribe(() => this.load());
    }
  }

  usable = dtdSetUsable;
  optionLabel = dtdSetOptionLabel;

  statusLabel(set: DtdSetSummary): string {
    if (set.status === 'processing') return `Processing · step ${(set.latest_step ?? 0) + 1} of ${STEP_COUNT}`;
    if (set.status === 'failed') return 'Failed';
    return set.warning_count
      ? `Ready · ${set.warning_count} warning${set.warning_count === 1 ? '' : 's'}`
      : 'Ready';
  }

  statusClass(set: DtdSetSummary): string {
    if (set.status === 'processing') return 'hop-status-chip-running';
    if (set.status === 'failed') return 'hop-status-chip-failed';
    return set.warning_count ? 'hop-status-chip-pending' : 'hop-status-chip-completed';
  }

  statusIcon(set: DtdSetSummary): string {
    if (set.status === 'failed') return 'close';
    return set.warning_count ? 'warning' : 'check';
  }

  typesNote(set: DtdSetSummary): string {
    if (set.status === 'processing' && set.document_type_count == null) return 'Counting…';
    if (set.document_type_count == null) return '';
    return set.specialized_count ? `${set.specialized_count} specialized` : 'Standard';
  }

  updatedLabel(set: DtdSetSummary): string {
    if (!set.updated_at) return '—';
    const updated = new Date(set.updated_at.endsWith('Z') || set.updated_at.includes('+') ? set.updated_at : set.updated_at + 'Z');
    if (Date.now() - updated.getTime() < 60_000) return 'Just now';
    return updated.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }

  open(set: DtdSetSummary): void {
    this.router.navigate(['/admin/dtd-sets', set.id]);
  }

  openUpload(set?: DtdSetSummary): void {
    const data: HopDtdUploadDialogData = {
      maxUploadMb: this.list?.max_upload_mb ?? 50, setId: set?.id, setName: set?.name,
    };
    this.dialog.open<HopDtdUploadDialogComponent, HopDtdUploadDialogData, HopDtdUploadDialogResult>(
      HopDtdUploadDialogComponent, { data, autoFocus: false },
    ).afterClosed().subscribe(result => { if (result) this.load(); });
  }

  setDefault(id: string): void {
    this.service.setDefault(id).subscribe({
      next: list => {
        this.list = list;
        this.snackBar.open('Organization default updated', 'Close', { duration: 3000 });
        this.cdr.markForCheck();
      },
      error: err => this.snackBar.open(err?.error?.detail || 'Failed to update the default', 'Close', { duration: 5000 }),
    });
  }

  remove(set: DtdSetSummary): void {
    this.dialog.open(HopConfirmDialogComponent, {
      data: { title: 'Delete DTD set', message: `Delete ${set.name} and every version of it? This can't be undone.`, confirmText: 'Delete' },
    }).afterClosed().subscribe(confirmed => {
      if (!confirmed) return;
      this.service.delete(set.id).subscribe({
        next: () => { this.snackBar.open('DTD set deleted', 'Close', { duration: 3000 }); this.load(); },
        error: err => this.snackBar.open(err?.error?.detail || 'Failed to delete the DTD set', 'Close', { duration: 5000 }),
      });
    });
  }
}
