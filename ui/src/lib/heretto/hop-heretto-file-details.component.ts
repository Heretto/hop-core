import {
  ChangeDetectionStrategy, ChangeDetectorRef, Component, EventEmitter, Input, Output, inject,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { HERETTO_KIND_LABELS, HerettoFile } from './hop-heretto.service';

/** The open folder, as folder selection describes it. */
export interface HerettoFolderSummary {
  id: string;
  name: string;
  path?: string | null;
  folders: number;
  files: number;
}

/** The file browser's side pane: the selected file's (or the open folder's)
 *  title, location, date and ID — and, choosing many files, what's chosen. */
@Component({
  changeDetection: ChangeDetectionStrategy.Eager,
  selector: 'hop-heretto-file-details',
  standalone: true,
  imports: [CommonModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule],
  template: `
    <div class="loading" *ngIf="loading"><mat-spinner diameter="24"></mat-spinner></div>

    <ng-container *ngIf="!loading && file">
      <div class="heading">
        <span class="kind">{{ kindLabel }}</span>
        <span class="title">{{ file.title }}</span>
        <span class="mono">{{ file.name }}</span>
      </div>
      <dl>
        <div *ngIf="file.path"><dt>Location</dt><dd class="mono">{{ slashed(file.path) }}</dd></div>
        <div *ngIf="file.last_modified"><dt>Last modified</dt><dd>{{ file.last_modified | date: 'mediumDate' }}</dd></div>
        <div *ngIf="file.status"><dt>Status</dt><dd>{{ file.status }}</dd></div>
        <ng-container *ngTemplateOutlet="idRow; context: { id: file.id, label: 'File ID' }"></ng-container>
      </dl>
      <a *ngIf="file.editor_url" class="open" [href]="file.editor_url" target="_blank" rel="noopener">
        Open in Heretto <mat-icon>open_in_new</mat-icon>
      </a>
    </ng-container>

    <ng-container *ngIf="!loading && !file && folder">
      <div class="heading">
        <span class="kind">Folder</span>
        <span class="title">{{ folder.name }}</span>
      </div>
      <dl>
        <div *ngIf="folder.path"><dt>Location</dt><dd class="mono">{{ slashed(folder.path) }}</dd></div>
        <div><dt>Contains</dt><dd>{{ contents }}</dd></div>
        <ng-container *ngTemplateOutlet="idRow; context: { id: folder.id, label: 'Folder ID' }"></ng-container>
      </dl>
    </ng-container>

    <div class="none" *ngIf="!loading && !file && !folder">
      <strong>{{ error || 'No file selected' }}</strong>
      <span *ngIf="!error">{{ hint }}</span>
    </div>

    <section class="chosen" *ngIf="chosen.length" aria-label="Selected files">
      <div class="chosen-head">
        <span class="kind">Selected ({{ chosen.length }})</span>
        <button type="button" class="clear" (click)="clear.emit()">Clear</button>
      </div>
      <ul>
        <li *ngFor="let item of chosen; trackBy: trackId">
          <span class="mono">{{ item.name }}</span>
          <button mat-icon-button type="button" [attr.aria-label]="'Remove ' + item.name" (click)="remove.emit(item.id)">
            <mat-icon>close</mat-icon>
          </button>
        </li>
      </ul>
    </section>

    <ng-template #idRow let-id="id" let-label="label">
      <div>
        <dt>{{ label }}</dt>
        <dd class="id">
          <span class="mono">{{ id }}</span>
          <button mat-icon-button type="button" [attr.aria-label]="copied === id ? 'Copied' : 'Copy ' + label"
                  (click)="copy(id)">
            <mat-icon>{{ copied === id ? 'check' : 'content_copy' }}</mat-icon>
          </button>
        </dd>
      </div>
    </ng-template>
  `,
  styles: [`
    :host {
      display: flex; flex-direction: column; gap: 16px; box-sizing: border-box; padding: 20px;
      overflow-y: auto; background: var(--bg-secondary); border-left: 1px solid var(--border-default);
    }
    .loading { display: flex; justify-content: center; padding-top: 24px; }
    .heading { display: flex; flex-direction: column; gap: 4px; }
    .kind { font-size: 11px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-tertiary); }
    .title { font-size: 17px; font-weight: 600; letter-spacing: -0.01em; color: var(--text-primary); }
    .mono { font-family: var(--font-mono); font-size: 12px; overflow-wrap: anywhere; }
    .heading .mono { color: var(--text-secondary); }
    dl { margin: 0; display: flex; flex-direction: column; gap: 12px; }
    dl > div { display: flex; flex-direction: column; gap: 2px; }
    dt { font-size: 12px; color: var(--text-tertiary); }
    dd { margin: 0; color: var(--text-primary); }
    dd.id, .chosen li { display: flex; align-items: center; gap: 2px; }
    dd.id button, .chosen li button { flex-shrink: 0; color: var(--text-secondary); }
    .open { display: inline-flex; align-items: center; gap: 6px; font-weight: 500; }
    .open mat-icon { font-size: 18px; width: 18px; height: 18px; }
    .none { display: flex; flex-direction: column; gap: 6px; padding-top: 8px; line-height: 1.5; color: var(--text-secondary); }
    .none strong { font-weight: 500; color: var(--text-primary); }
    .chosen { margin-top: auto; padding-top: 12px; border-top: 1px solid var(--border-default); }
    .chosen-head { display: flex; align-items: center; justify-content: space-between; }
    .clear { padding: 4px; border: 0; background: none; font: inherit; font-size: 13px; color: var(--text-link); cursor: pointer; }
    .chosen ul { list-style: none; margin: 4px 0 0; padding: 0; }
    .chosen li .mono { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  `],
})
export class HopHerettoFileDetailsComponent {
  private cdr = inject(ChangeDetectorRef);

  @Input() file: HerettoFile | null = null;
  /** Choosing a folder: the open folder, shown when no file is. */
  @Input() folder: HerettoFolderSummary | null = null;
  @Input() loading = false;
  /** Shown in place of the details when the file couldn't be read. */
  @Input() error = '';
  /** Shown when nothing is selected. */
  @Input() hint = 'Select a file to see its title, location and ID. Double-click to choose it straight away.';
  /** Choosing many files: what's chosen so far. */
  @Input() chosen: { id: string; name: string }[] = [];
  @Output() remove = new EventEmitter<string>();
  @Output() clear = new EventEmitter<void>();

  copied: string | null = null;

  get kindLabel(): string {
    return this.file ? HERETTO_KIND_LABELS[this.file.kind] : '';
  }

  get contents(): string {
    const { folders, files } = this.folder ?? { folders: 0, files: 0 };
    if (!folders && !files) return 'Nothing yet';
    const part = (n: number, one: string) => `${n} ${one}${n === 1 ? '' : 's'}`;
    return [folders && part(folders, 'folder'), files && part(files, 'file')].filter(Boolean).join(', ');
  }

  /** Paths read as Heretto shows them: /master/product/documents/… */
  slashed(path: string): string {
    return path.startsWith('/') ? path : '/' + path;
  }

  copy(id: string): void {
    navigator.clipboard?.writeText(id).then(() => {
      this.copied = id;
      this.cdr.markForCheck();
      setTimeout(() => { this.copied = null; this.cdr.markForCheck(); }, 1500);
    }).catch(() => undefined);
  }

  trackId = (_: number, item: { id: string }) => item.id;
}
