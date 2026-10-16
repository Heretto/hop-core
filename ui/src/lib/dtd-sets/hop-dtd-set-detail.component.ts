import {
  ChangeDetectionStrategy, ChangeDetectorRef, Component, DestroyRef, OnInit, inject,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { Subscription, timer } from 'rxjs';
import { HopConfirmDialogComponent } from '../shared/hop-confirm-dialog.component';
import { DtdDocumentType, DtdSetDetail, DtdSetVersion, HopDtdSetService } from './hop-dtd-set.service';
import {
  HopDtdUploadDialogComponent, HopDtdUploadDialogData, HopDtdUploadDialogResult,
} from './hop-dtd-upload-dialog.component';

const INITIAL_ROWS = 8;
/** Base types people look for first, in the order the mock lists them. */
const CORE_ROOTS = ['concept', 'task', 'reference', 'map', 'bookmap', 'topic', 'glossentry'];

/** One DTD set: its warnings, document types, package, users and versions. */
@Component({
  changeDetection: ChangeDetectionStrategy.Eager,
  selector: 'hop-dtd-set-detail',
  standalone: true,
  imports: [
    CommonModule, RouterLink, MatButtonModule, MatIconModule, MatMenuModule, MatFormFieldModule,
    MatInputModule, MatProgressSpinnerModule, MatDialogModule, MatSnackBarModule,
  ],
  template: `
    <div class="hop-page detail">
      <a class="back" routerLink="/admin" [queryParams]="{ section: 'dtd-sets' }">
        <mat-icon>arrow_back</mat-icon> Administration · DTD sets
      </a>

      <div class="loading" *ngIf="!set && !notFound"><mat-spinner diameter="32"></mat-spinner></div>
      <p class="error-text" *ngIf="notFound">That DTD set doesn't exist.</p>

      <ng-container *ngIf="set">
        <div class="title-row">
          <div class="title-block">
            <div class="title-line">
              <h1>{{ set.name }}</h1>
              <span class="tag" *ngIf="set.is_default">Organization default</span>
              <span class="tag" *ngIf="set.builtin">Built in</span>
              <span class="hop-status-chip" [ngClass]="statusClass()">
                <mat-icon *ngIf="set.status !== 'processing'">{{ statusIcon() }}</mat-icon>
                {{ statusLabel() }}
              </span>
            </div>
            <p class="subtitle">{{ subtitle() }}</p>
          </div>
          <div class="title-actions" *ngIf="!set.builtin">
            <button mat-stroked-button (click)="openUpload()" [disabled]="processingVersion">
              <mat-icon>upload</mat-icon> Upload new version
            </button>
            <a mat-stroked-button *ngIf="currentVersion" [href]="downloadUrl(currentVersion)" download>Download zip</a>
            <button mat-stroked-button class="more" [matMenuTriggerFor]="more" aria-label="More actions">
              <mat-icon>more_vert</mat-icon>
            </button>
            <mat-menu #more="matMenu">
              <button mat-menu-item (click)="makeDefault()" [disabled]="set.is_default || set.status !== 'ready'">
                <mat-icon>check_circle</mat-icon> Make organization default
              </button>
              <button mat-menu-item (click)="remove()" [disabled]="!canDelete()">
                <mat-icon>delete</mat-icon> Delete…
              </button>
            </mat-menu>
          </div>
          <div class="title-actions" *ngIf="set.builtin">
            <button mat-stroked-button (click)="makeDefault()" [disabled]="set.is_default">Make organization default</button>
          </div>
        </div>

        <div class="processing-banner" *ngIf="processingVersion as v">
          <mat-spinner diameter="18"></mat-spinner>
          <span>{{ v.label }} is processing — step {{ v.step + 1 }} of 6, {{ runningStep(v) }}.
            Apps keep using {{ currentVersion?.label || 'nothing from this set' }} until it's ready.</span>
        </div>
        <div class="failed-banner" *ngIf="!currentVersion && latestFailed as v">
          <mat-icon>error</mat-icon>
          <span>{{ v.label }} failed: {{ v.error }}</span>
        </div>

        <div class="columns">
          <div class="main">
            <section class="card" *ngIf="set.issues.length">
              <header>
                <h2>Warnings <span class="count">{{ set.issues.length }}</span></h2>
                <span class="quiet">{{ set.status === 'failed' ? 'Found before processing stopped' : "Didn't block processing" }}</span>
              </header>
              <ul class="issues">
                <li *ngFor="let issue of set.issues">
                  <mat-icon class="warn-icon">warning</mat-icon>
                  <div>
                    <div class="issue-title">{{ issue.title }}</div>
                    <div class="issue-detail">{{ issue.detail }}</div>
                    <div class="issue-loc mono" *ngIf="issue.file">
                      {{ issue.file }}<ng-container *ngIf="issue.line"> : line {{ issue.line }}</ng-container>
                    </div>
                  </div>
                </li>
              </ul>
            </section>

            <section class="card" *ngIf="set.document_types.length">
              <header>
                <h2>Document types <span class="quiet">{{ set.document_types.length }} · {{ specializedCount() }} specialized</span></h2>
                <mat-form-field appearance="outline" class="filter" subscriptSizing="dynamic">
                  <mat-icon matPrefix>search</mat-icon>
                  <input matInput placeholder="Filter document types" (input)="filter = $any($event.target).value; showAll = !!filter">
                </mat-form-field>
              </header>
              <div class="table-scroll">
                <table class="types">
                  <thead><tr><th>Document type</th><th>Root element</th><th>Public ID</th><th>Kind</th></tr></thead>
                  <tbody>
                    <tr *ngFor="let type of visibleTypes()">
                      <td>{{ type.name }}<span class="error-text" *ngIf="!type.parses"> · couldn't load</span></td>
                      <td class="mono">{{ type.root }}</td>
                      <td class="mono">{{ type.public_id }}</td>
                      <td>
                        <span class="kind" [class.specialized]="type.kind === 'specialized'">
                          {{ type.kind === 'specialized' ? 'Specialized' + (type.specializes ? ' · ' + type.specializes : '') : 'Base' }}
                        </span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <button mat-button class="show-all" *ngIf="!showAll && filteredTypes().length > initialRows"
                      (click)="showAll = true">
                Show all {{ filteredTypes().length }} document types
              </button>
            </section>
          </div>

          <aside class="side">
            <section class="card facts">
              <h2>Package</h2>
              <dl>
                <dt>Based on</dt><dd>{{ set.package.based_on || '—' }}</dd>
                <ng-container *ngIf="set.package.filename"><dt>File</dt><dd class="mono">{{ set.package.filename }}</dd></ng-container>
                <ng-container *ngIf="set.package.size_bytes">
                  <dt>Size</dt>
                  <dd>{{ formatSize(set.package.size_bytes) }}<ng-container *ngIf="set.package.file_count"> · {{ set.package.file_count }} files</ng-container></dd>
                </ng-container>
                <ng-container *ngIf="set.package.catalog">
                  <dt>Catalog</dt><dd><span class="mono">{{ set.package.catalog }}</span> · {{ set.package.public_id_count }} public IDs</dd>
                </ng-container>
                <ng-container *ngIf="set.package.processed_at"><dt>Processed</dt><dd>{{ asDate(set.package.processed_at) | date: 'MMM d, y, h:mm a' }}</dd></ng-container>
              </dl>
            </section>

            <section class="card">
              <h2>Used by</h2>
              <p class="quiet-text" *ngIf="set.is_default">
                The organization default, so every app and agent without its own choice validates against it.
                <ng-container *ngIf="set.agents.length">These agents also select it directly:</ng-container>
              </p>
              <p class="quiet-text" *ngIf="!set.is_default && set.agents.length">These agents select it:</p>
              <p class="quiet-text" *ngIf="!set.is_default && !set.agents.length">No agents select it, and it isn't the organization default.</p>
              <ul class="agents">
                <li *ngFor="let agent of set.agents"><mat-icon>smart_toy</mat-icon> {{ agent.name }}</li>
              </ul>
            </section>

            <section class="card" *ngIf="!set.builtin">
              <h2>Versions</h2>
              <ul class="versions">
                <li *ngFor="let v of set.versions">
                  <span class="v-label">{{ v.label }}</span>
                  <span class="v-date">{{ asDate(v.created_at) | date: 'MMM d, y' }}</span>
                  <span class="hop-status-chip hop-status-chip-completed" *ngIf="v.is_current">Current</span>
                  <span class="hop-status-chip hop-status-chip-running" *ngIf="v.status === 'processing'">Processing</span>
                  <span class="hop-status-chip hop-status-chip-failed" *ngIf="v.status === 'failed'" [title]="v.error || ''">Failed</span>
                  <button mat-stroked-button *ngIf="!v.is_current && v.status === 'ready'" (click)="restore(v)">Restore</button>
                </li>
              </ul>
              <p class="quiet-text small">A new version is processed in the background. Apps keep using the current one until it's ready.</p>
            </section>

            <section class="card" *ngIf="!set.builtin">
              <h2>Delete DTD set</h2>
              <p class="quiet-text">{{ deleteNote() }}</p>
              <button mat-stroked-button color="warn" [disabled]="!canDelete()" (click)="remove()">Delete…</button>
            </section>
          </aside>
        </div>
      </ng-container>
    </div>
  `,
  styles: [`
    .back { display: inline-flex; align-items: center; gap: 6px; color: var(--text-secondary); text-decoration: none; margin-bottom: 16px; }
    .back mat-icon { font-size: 18px; width: 18px; height: 18px; }
    .loading { display: flex; justify-content: center; padding: 48px; }
    .title-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; flex-wrap: wrap; }
    .title-line { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
    .title-line h1 { margin: 0; }
    .subtitle { margin: 6px 0 0; color: var(--text-secondary); }
    .title-actions { display: flex; gap: 8px; align-items: center; }
    .title-actions .more { min-width: 0; padding: 0 8px; }
    .tag {
      padding: 2px 10px; border-radius: 9999px; background: var(--button-secondary-bg);
      font-size: 0.78rem; font-weight: 600; color: var(--text-secondary);
    }
    .hop-status-chip { display: inline-flex; align-items: center; gap: 4px; }
    .hop-status-chip mat-icon { font-size: 14px; width: 14px; height: 14px; }
    .processing-banner, .failed-banner {
      display: flex; align-items: center; gap: 12px; margin-top: 20px; padding: 12px 16px; border-radius: 8px;
    }
    .processing-banner { background: var(--color-info-bg); color: var(--color-info-text); }
    .failed-banner { background: var(--color-error-bg); color: var(--color-error-text); }
    .columns { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 24px; margin-top: 24px; align-items: start; }
    .main, .side { display: flex; flex-direction: column; gap: 24px; min-width: 0; }
    .card { border: 1px solid var(--card-border); border-radius: 12px; background: var(--card-bg); }
    .card > h2 { margin: 0; padding: 20px 24px 8px; font-size: 1.05rem; }
    .card header {
      display: flex; justify-content: space-between; align-items: center; gap: 16px;
      padding: 16px 24px; border-bottom: 1px solid var(--border-default);
    }
    .card header h2 { margin: 0; font-size: 1.05rem; }
    .count {
      display: inline-flex; align-items: center; justify-content: center; min-width: 22px; padding: 0 6px; margin-left: 6px;
      border-radius: 9999px; background: var(--color-warning-bg); color: var(--color-warning-text); font-size: 0.78rem;
    }
    .quiet { color: var(--text-tertiary); font-weight: 400; font-size: 0.86rem; margin-left: 6px; }
    .quiet-text { margin: 0; padding: 0 24px 12px; color: var(--text-secondary); font-size: 0.9rem; }
    .quiet-text.small { font-size: 0.82rem; color: var(--text-tertiary); padding-bottom: 20px; }
    .issues { list-style: none; margin: 0; padding: 0; }
    .issues li { display: flex; gap: 12px; padding: 16px 24px; border-bottom: 1px solid var(--border-light); }
    .issues li:last-child { border-bottom: none; }
    .warn-icon { color: var(--color-warning); flex: none; }
    .issue-title { font-weight: 600; color: var(--text-primary); }
    .issue-detail { color: var(--text-secondary); margin-top: 2px; }
    .issue-loc { color: var(--text-tertiary); margin-top: 4px; font-size: 0.82rem; }
    .mono { font-family: var(--font-mono); font-size: 0.84rem; overflow-wrap: anywhere; }
    .filter { width: 240px; }
    .filter mat-icon { color: var(--text-tertiary); padding: 0 4px 0 8px; }
    .table-scroll { overflow-x: auto; }
    .types { width: 100%; border-collapse: collapse; }
    .types th {
      text-align: left; padding: 12px 24px; color: var(--text-tertiary); font-size: 0.72rem; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.04em; border-bottom: 1px solid var(--border-default);
    }
    .types td { padding: 10px 24px; border-bottom: 1px solid var(--border-light); }
    .kind {
      padding: 2px 8px; border-radius: 9999px; background: var(--button-secondary-bg);
      font-size: 0.78rem; white-space: nowrap; color: var(--text-secondary);
    }
    .kind.specialized { background: var(--color-tertiary-bg); color: var(--color-tertiary-text); }
    .show-all { margin: 8px 12px 12px; }
    .facts dl { display: grid; grid-template-columns: auto 1fr; gap: 10px 16px; margin: 0; padding: 4px 24px 20px; }
    .facts dt { color: var(--text-tertiary); }
    .facts dd { margin: 0; color: var(--text-primary); }
    .agents, .versions { list-style: none; margin: 0; padding: 0 24px 12px; }
    .agents li { display: flex; align-items: center; gap: 10px; padding: 6px 0; }
    .agents mat-icon { font-size: 18px; width: 18px; height: 18px; color: var(--text-tertiary); }
    .versions li { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--border-light); }
    .v-label { font-weight: 600; }
    .v-date { flex: 1; color: var(--text-tertiary); }
    .card > button { margin: 0 24px 20px; }
    .error-text { color: var(--color-error-text); }
    @media (max-width: 1000px) { .columns { grid-template-columns: 1fr; } }
  `],
})
export class HopDtdSetDetailComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private service = inject(HopDtdSetService);
  private dialog = inject(MatDialog);
  private snackBar = inject(MatSnackBar);
  private cdr = inject(ChangeDetectorRef);

  set: DtdSetDetail | null = null;
  notFound = false;
  filter = '';
  showAll = false;
  readonly initialRows = INITIAL_ROWS;
  private id = '';
  private refresh?: Subscription;
  private maxUploadMb = 50;

  constructor() {
    inject(DestroyRef).onDestroy(() => this.refresh?.unsubscribe());
  }

  ngOnInit(): void {
    this.route.paramMap.subscribe(params => {
      this.id = params.get('dtdSetId') ?? '';
      this.load();
    });
    this.service.list().subscribe({ next: list => { this.maxUploadMb = list.max_upload_mb; } });
  }

  private load(): void {
    this.service.get(this.id).subscribe({
      next: set => {
        this.set = set;
        this.notFound = false;
        this.refresh?.unsubscribe();
        if (this.processingVersion) {
          this.refresh = timer(2000).subscribe(() => this.load());
        }
        this.cdr.markForCheck();
      },
      error: () => { this.notFound = true; this.cdr.markForCheck(); },
    });
  }

  get currentVersion(): DtdSetVersion | undefined {
    return this.set?.versions.find(v => v.is_current);
  }

  get processingVersion(): DtdSetVersion | undefined {
    return this.set?.versions.find(v => v.status === 'processing');
  }

  get latestFailed(): DtdSetVersion | undefined {
    const latest = this.set?.versions[0];
    return latest?.status === 'failed' ? latest : undefined;
  }

  runningStep(v: DtdSetVersion): string {
    return (v.steps.find(s => s.state === 'running')?.label ?? '').toLowerCase();
  }

  subtitle(): string {
    const s = this.set!;
    if (s.builtin) return 'The OASIS DITA 1.3 standard, included with Hop.';
    const parts = [s.version_label, s.description].filter(Boolean);
    const current = this.currentVersion ?? s.versions[0];
    if (current?.uploaded_by && current.created_at) {
      const date = this.asDate(current.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
      parts.push(`uploaded by ${current.uploaded_by} on ${date}`);
    }
    return parts.join(' · ');
  }

  statusLabel(): string {
    const s = this.set!;
    if (s.status === 'processing') return 'Processing';
    if (s.status === 'failed') return 'Failed';
    return s.warning_count ? `Ready · ${s.warning_count} warning${s.warning_count === 1 ? '' : 's'}` : 'Ready';
  }

  statusClass(): string {
    const s = this.set!;
    if (s.status === 'processing') return 'hop-status-chip-running';
    if (s.status === 'failed') return 'hop-status-chip-failed';
    return s.warning_count ? 'hop-status-chip-pending' : 'hop-status-chip-completed';
  }

  statusIcon(): string {
    return this.set!.status === 'failed' ? 'close' : this.set!.warning_count ? 'warning' : 'check';
  }

  specializedCount(): number {
    return this.set!.document_types.filter(t => t.kind === 'specialized').length;
  }

  filteredTypes(): DtdDocumentType[] {
    const q = this.filter.trim().toLowerCase();
    // The core types first, then the specializations (what makes a custom set
    // worth uploading, so they belong in the first screenful), then the rest.
    const rank = (t: DtdDocumentType): number => {
      const core = CORE_ROOTS.indexOf(t.root);
      if (t.kind === 'base' && core >= 0 && t.name.toLowerCase() === t.root.toLowerCase()) return core;
      return t.kind === 'specialized' ? 100 : 200;
    };
    const types = [...this.set!.document_types].sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name));
    return q ? types.filter(t => [t.name, t.root, t.public_id, t.specializes ?? ''].some(v => v.toLowerCase().includes(q))) : types;
  }

  visibleTypes(): DtdDocumentType[] {
    const types = this.filteredTypes();
    return this.showAll ? types : types.slice(0, INITIAL_ROWS);
  }

  canDelete(): boolean {
    return !!this.set && !this.set.builtin && !this.set.is_default && this.set.agents.length === 0;
  }

  deleteNote(): string {
    const s = this.set!;
    const blockers = [];
    if (s.is_default) blockers.push('choose a different organization default');
    if (s.agents.length) blockers.push(`move the ${s.agents.length} agent${s.agents.length === 1 ? '' : 's'} to another set`);
    if (!blockers.length) return 'Deletes the set and every version of it.';
    const text = blockers.join(' and ');
    return text.charAt(0).toUpperCase() + text.slice(1) + ' first.';
  }

  downloadUrl(v: DtdSetVersion): string {
    return this.service.downloadUrl(this.set!.id, v.id);
  }

  asDate(value?: string | null): Date {
    if (!value) return new Date(NaN);
    // SQLite returns naive timestamps; they are UTC.
    return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : value + 'Z');
  }

  formatSize(bytes: number): string {
    return bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
  }

  openUpload(): void {
    const data: HopDtdUploadDialogData = { maxUploadMb: this.maxUploadMb, setId: this.set!.id, setName: this.set!.name };
    this.dialog.open<HopDtdUploadDialogComponent, HopDtdUploadDialogData, HopDtdUploadDialogResult>(
      HopDtdUploadDialogComponent, { data, autoFocus: false },
    ).afterClosed().subscribe(result => { if (result) this.load(); });
  }

  makeDefault(): void {
    this.service.setDefault(this.set!.id).subscribe({
      next: () => { this.snackBar.open('Organization default updated', 'Close', { duration: 3000 }); this.load(); },
      error: err => this.snackBar.open(err?.error?.detail || 'Failed to update the default', 'Close', { duration: 5000 }),
    });
  }

  restore(v: DtdSetVersion): void {
    this.service.restore(this.set!.id, v.id).subscribe({
      next: set => {
        this.set = set;
        this.snackBar.open(`${v.label} is now the current version`, 'Close', { duration: 3000 });
        this.cdr.markForCheck();
      },
      error: err => this.snackBar.open(err?.error?.detail || 'Failed to restore that version', 'Close', { duration: 5000 }),
    });
  }

  remove(): void {
    const s = this.set!;
    this.dialog.open(HopConfirmDialogComponent, {
      data: { title: 'Delete DTD set', message: `Delete ${s.name} and every version of it? This can't be undone.`, confirmText: 'Delete' },
    }).afterClosed().subscribe(confirmed => {
      if (!confirmed) return;
      this.service.delete(s.id).subscribe({
        next: () => {
          this.snackBar.open('DTD set deleted', 'Close', { duration: 3000 });
          this.router.navigate(['/admin'], { queryParams: { section: 'dtd-sets' } });
        },
        error: err => this.snackBar.open(err?.error?.detail || 'Failed to delete the DTD set', 'Close', { duration: 5000 }),
      });
    });
  }
}
