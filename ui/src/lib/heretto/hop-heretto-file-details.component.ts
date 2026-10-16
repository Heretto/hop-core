import { ChangeDetectionStrategy, ChangeDetectorRef, Component, Input, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { HERETTO_KIND_LABELS, HerettoFile } from './hop-heretto.service';

/** The file browser's side pane: the selected file's title, location, date and ID. */
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
        <div *ngIf="file.path"><dt>Location</dt><dd class="mono">{{ location }}</dd></div>
        <div *ngIf="file.last_modified"><dt>Last modified</dt><dd>{{ file.last_modified | date: 'mediumDate' }}</dd></div>
        <div *ngIf="file.status"><dt>Status</dt><dd>{{ file.status }}</dd></div>
        <div>
          <dt>File ID</dt>
          <dd class="id">
            <span class="mono">{{ file.id }}</span>
            <button mat-icon-button type="button" [attr.aria-label]="copied ? 'Copied' : 'Copy file ID'"
                    (click)="copyId()">
              <mat-icon>{{ copied ? 'check' : 'content_copy' }}</mat-icon>
            </button>
          </dd>
        </div>
      </dl>
      <a *ngIf="file.editor_url" class="open" [href]="file.editor_url" target="_blank" rel="noopener">
        Open in Heretto <mat-icon>open_in_new</mat-icon>
      </a>
    </ng-container>

    <div class="none" *ngIf="!loading && !file">
      <strong>{{ error || 'No file selected' }}</strong>
      <span *ngIf="!error">Select a file to see its title, location and ID. Double-click to choose it straight away.</span>
    </div>
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
    dd.id { display: flex; align-items: center; gap: 2px; }
    dd.id button { flex-shrink: 0; color: var(--text-secondary); }
    .open { display: inline-flex; align-items: center; gap: 6px; font-weight: 500; }
    .open mat-icon { font-size: 18px; width: 18px; height: 18px; }
    .none { display: flex; flex-direction: column; gap: 6px; padding-top: 8px; line-height: 1.5; color: var(--text-secondary); }
    .none strong { font-weight: 500; color: var(--text-primary); }
  `],
})
export class HopHerettoFileDetailsComponent {
  private cdr = inject(ChangeDetectorRef);

  @Input() file: HerettoFile | null = null;
  @Input() loading = false;
  /** Shown in place of the details when the file couldn't be read. */
  @Input() error = '';

  copied = false;

  get kindLabel(): string {
    return this.file ? HERETTO_KIND_LABELS[this.file.kind] : '';
  }

  /** Paths read as Heretto shows them: /master/product/documents/… */
  get location(): string {
    const path = this.file?.path ?? '';
    return path.startsWith('/') ? path : '/' + path;
  }

  copyId(): void {
    if (!this.file) return;
    navigator.clipboard?.writeText(this.file.id).then(() => {
      this.copied = true;
      this.cdr.markForCheck();
      setTimeout(() => { this.copied = false; this.cdr.markForCheck(); }, 1500);
    }).catch(() => undefined);
  }
}
