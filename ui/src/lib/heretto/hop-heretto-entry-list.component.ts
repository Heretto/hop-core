import { ChangeDetectionStrategy, Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { HERETTO_KIND_LABELS, HerettoEntry, HerettoEntryKind, HerettoFailure } from './hop-heretto.service';

/** One row of the browser's list: a folder or file, where it is, and whether it can be chosen. */
export interface HerettoBrowserRow {
  entry: HerettoEntry;
  /** Search results: the folder the entry is in, shown under its name. */
  pathLabel?: string;
  disabled: boolean;
}

const KIND_ICONS: Record<HerettoEntryKind, string> = {
  folder: 'folder', map: 'account_tree', topic: 'description', image: 'image', other: 'draft',
};
const SKELETON = ['180px', '140px', '220px', '160px', '200px', '120px', '170px'];

/** The file browser's list pane: rows, loading skeleton, empty and error states. */
@Component({
  changeDetection: ChangeDetectionStrategy.Eager,
  selector: 'hop-heretto-entry-list',
  standalone: true,
  imports: [CommonModule, RouterLink, MatButtonModule, MatIconModule],
  template: `
    <div class="row head" aria-hidden="true"><span>Name</span><span>Type</span></div>

    <div *ngIf="loading" aria-busy="true" [attr.aria-label]="loadingLabel">
      <div class="row" *ngFor="let w of skeleton">
        <span class="name"><span class="bone icon"></span><span class="bone" [style.width]="w"></span></span>
        <span class="bone type"></span>
      </div>
    </div>

    <div class="failure" *ngIf="!loading && error" role="alert">
      <mat-icon>error</mat-icon>
      <div>
        <p><strong>{{ errorTitle }}</strong> {{ error.message }}</p>
        <p class="actions">
          <button mat-stroked-button type="button" (click)="retry.emit()">Try again</button>
          <a *ngIf="error.reason === 'credentials' && credentialsLink" [routerLink]="credentialsLink"
             (click)="leave.emit()">Open Credentials</a>
        </p>
      </div>
    </div>

    <div class="empty" *ngIf="!loading && !error && rows.length === 0">
      <mat-icon>{{ emptyIcon }}</mat-icon>
      <strong>{{ emptyTitle }}</strong>
      <span>{{ emptyHint }}</span>
    </div>

    <ul role="listbox" aria-label="Files and folders" *ngIf="!loading && !error && rows.length > 0">
      <li *ngFor="let row of rows; trackBy: trackRow">
        <button type="button" class="row" role="option" [disabled]="row.disabled"
                [class.folder]="row.entry.kind === 'folder'" [class.selected]="row.entry.id === selectedId"
                [attr.aria-selected]="row.entry.id === selectedId"
                (click)="activate(row)" (dblclick)="row.entry.kind !== 'folder' && choose.emit(row)">
          <span class="name">
            <mat-icon>{{ icon(row) }}</mat-icon>
            <span class="text">
              <span class="label">{{ row.entry.name }}</span>
              <span class="where" *ngIf="row.pathLabel">{{ row.pathLabel }}</span>
            </span>
          </span>
          <span class="type">{{ kindLabel(row) }}</span>
        </button>
      </li>
    </ul>
  `,
  styles: [`
    :host { display: block; }
    ul { list-style: none; margin: 0; padding: 0; }
    .row {
      width: 100%; display: grid; grid-template-columns: minmax(0, 1fr) 140px; gap: 12px; align-items: center;
      min-height: 44px; padding: 6px 24px; box-sizing: border-box; border: 0;
      border-bottom: 1px solid var(--border-light); background: transparent; font: inherit;
      text-align: left; color: var(--text-primary);
    }
    button.row { cursor: pointer; }
    button.row:hover:not(:disabled) { background: var(--hover-overlay); }
    button.row.selected { background: var(--color-primary-bg); }
    button.row:disabled { color: var(--text-disabled); cursor: default; }
    .row.folder .label, .row.selected .label { font-weight: 500; }
    .head {
      position: sticky; top: 0; z-index: 1; min-height: 0; padding: 10px 24px; background: var(--bg-primary);
      border-bottom-color: var(--border-default); font-size: 11px; font-weight: 600;
      letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-tertiary);
    }
    .name { display: flex; align-items: center; gap: 12px; min-width: 0; }
    .name mat-icon { flex-shrink: 0; color: var(--text-tertiary); }
    .row.folder mat-icon { color: var(--color-accent-text); }
    button.row:disabled mat-icon { color: var(--text-disabled); }
    .text { display: flex; flex-direction: column; min-width: 0; }
    .label, .where { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .where { font-size: 12px; color: var(--text-tertiary); }
    .type { font-size: 13px; color: var(--text-tertiary); }
    .bone { display: block; height: 10px; border-radius: 4px; background: var(--bg-tertiary); }
    .bone.icon { width: 20px; height: 20px; }
    .bone.type { width: 72px; }
    .failure {
      display: flex; gap: 12px; margin: 24px; padding: 16px; border-radius: 8px; line-height: 1.5;
      background: var(--color-error-bg); border: 1px solid var(--color-error-border); color: var(--color-error-text);
    }
    .failure p { margin: 0; color: inherit; }
    .failure .actions { display: flex; align-items: center; gap: 16px; margin-top: 12px; }
    .empty {
      display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 56px 24px;
      text-align: center; color: var(--text-secondary);
    }
    .empty mat-icon { color: var(--text-tertiary); margin-bottom: 4px; }
    .empty strong { color: var(--text-primary); font-weight: 500; }
    @media (max-width: 768px) { .row { grid-template-columns: minmax(0, 1fr); padding: 6px 16px; } .type { display: none; } }
  `],
})
export class HopHerettoEntryListComponent {
  @Input() rows: HerettoBrowserRow[] = [];
  @Input() loading = false;
  @Input() loadingLabel = 'Loading folder';
  @Input() error: HerettoFailure | null = null;
  @Input() errorTitle = "Couldn't open this folder.";
  @Input() credentialsLink: string | null = null;
  @Input() selectedId: string | null = null;
  @Input() emptyIcon = 'folder_open';
  @Input() emptyTitle = 'This folder is empty';
  @Input() emptyHint = '';
  /** A folder row was clicked. */
  @Output() open = new EventEmitter<HerettoBrowserRow>();
  /** A file row was clicked. */
  @Output() pick = new EventEmitter<HerettoBrowserRow>();
  /** A file row was double-clicked: choose it straight away. */
  @Output() choose = new EventEmitter<HerettoBrowserRow>();
  @Output() retry = new EventEmitter<void>();
  /** The error's Credentials link was followed. */
  @Output() leave = new EventEmitter<void>();

  readonly skeleton = SKELETON;

  activate(row: HerettoBrowserRow): void {
    (row.entry.kind === 'folder' ? this.open : this.pick).emit(row);
  }

  icon(row: HerettoBrowserRow): string {
    return KIND_ICONS[row.entry.kind];
  }

  kindLabel(row: HerettoBrowserRow): string {
    return HERETTO_KIND_LABELS[row.entry.kind];
  }

  trackRow = (_: number, row: HerettoBrowserRow) => row.entry.id;
}
