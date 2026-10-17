import {
  ChangeDetectionStrategy, ChangeDetectorRef, Component, EventEmitter, Input, Output, forwardRef, inject,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { ControlValueAccessor, FormControl, NG_VALUE_ACCESSOR, ReactiveFormsModule } from '@angular/forms';
import { MatDialog } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { Observable, map, shareReplay, switchMap } from 'rxjs';
import { HerettoConnection } from '../agents/hop-agent.service';
import {
  HERETTO_KIND_LABELS, HerettoFailure, HerettoFile, HerettoFileKind, HerettoFolder, HerettoFolderListing,
  HerettoSelectionMode, HopHerettoService, herettoFailure,
} from './hop-heretto.service';
import {
  HopHerettoBrowserDialogData, openHerettoFileBrowser, openHerettoFilesBrowser, openHerettoFolderBrowser,
} from './hop-heretto-browser-dialog.component';

/** The field's value, by `selection`: a file, a list of files, or a folder. */
export type HerettoFieldValue = HerettoFile | HerettoFile[] | HerettoFolder | null;

const ICONS: Record<HerettoFileKind, string> = {
  map: 'account_tree', topic: 'description', image: 'image', other: 'draft',
};
const PLACEHOLDERS: Record<HerettoSelectionMode, string> = {
  file: 'Paste a file ID, Heretto URL or repository path',
  files: 'Paste a file ID, Heretto URL or repository path to add it',
  folder: 'Paste a folder ID, Heretto URL or repository path',
};
let nextId = 0;

/**
 * A form control for Heretto content: one file (the default), any number of
 * files, or a folder — set by `selection`. Paste an ID, Heretto URL or
 * repository path, or browse. A chosen file or folder shows as a card with
 * Change and Remove; chosen files show as a list, with more added by pasting
 * or browsing.
 *
 * The value is a `HerettoFile` or null, a `HerettoFile[]`, or a
 * `HerettoFolder` or null.
 */
@Component({
  changeDetection: ChangeDetectionStrategy.Eager,
  selector: 'hop-heretto-file-field',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, MatButtonModule, MatFormFieldModule, MatIconModule, MatInputModule,
    MatProgressSpinnerModule,
  ],
  providers: [{ provide: NG_VALUE_ACCESSOR, useExisting: forwardRef(() => HopHerettoFileFieldComponent), multi: true }],
  template: `
    <span class="label" *ngIf="label" [id]="ids.label">{{ label }}</span>

    <div class="card" *ngIf="file || folder" role="group" [attr.aria-labelledby]="label ? ids.label : null">
      <span class="badge"><mat-icon>{{ folder ? 'folder' : icon(file!) }}</mat-icon></span>
      <span class="info">
        <span class="title">{{ folder ? folder.name : file!.title }}</span>
        <span class="path" *ngIf="(folder ?? file)!.path as path" [title]="slashed(path)">{{ slashed(path) }}</span>
        <span class="meta">{{ folder ? 'Folder' : kindLabel(file!) }} · {{ (folder ?? file)!.credential_name }}</span>
      </span>
      <button mat-stroked-button type="button" [disabled]="disabled" (click)="browse()">Change</button>
      <button mat-icon-button type="button" [attr.aria-label]="'Remove ' + (label || (folder ? 'folder' : 'file')).toLowerCase()"
              [disabled]="disabled" (click)="clear()"><mat-icon>close</mat-icon></button>
    </div>

    <ul class="files" *ngIf="files.length" [attr.aria-labelledby]="label ? ids.label : null">
      <li class="card compact" *ngFor="let item of files; trackBy: trackId">
        <span class="badge"><mat-icon>{{ icon(item) }}</mat-icon></span>
        <span class="info">
          <span class="title">{{ item.title }}</span>
          <span class="path" *ngIf="item.path" [title]="slashed(item.path)">{{ slashed(item.path) }}</span>
        </span>
        <button mat-icon-button type="button" [attr.aria-label]="'Remove ' + item.title" [disabled]="disabled"
                (click)="removeFile(item.id)"><mat-icon>close</mat-icon></button>
      </li>
    </ul>

    <div class="entry" *ngIf="!file && !folder">
      <mat-form-field subscriptSizing="dynamic">
        <input matInput [formControl]="text" [placeholder]="placeholder || placeholders[selection]"
               [attr.aria-label]="(label || 'Heretto ' + (selection === 'folder' ? 'folder' : 'file')) + ' ID, URL or path'"
               [attr.aria-invalid]="!!error" [attr.aria-describedby]="error ? ids.error : (hint ? ids.hint : null)"
               (keydown.enter)="resolveText(); $event.preventDefault()" (blur)="onBlur()">
        <mat-spinner matSuffix diameter="18" *ngIf="resolving"></mat-spinner>
      </mat-form-field>
      <button *ngIf="required && !files.length" mat-flat-button color="primary" type="button" [disabled]="disabled"
              (click)="browse()">Browse…</button>
      <button *ngIf="!(required && !files.length)" mat-stroked-button type="button" [disabled]="disabled"
              (click)="browse()"><mat-icon>folder_open</mat-icon> Browse…</button>
    </div>

    <div class="error" *ngIf="error && !file && !folder" [id]="ids.error" role="alert">
      <mat-icon>error</mat-icon>
      <span>{{ error.message }}
        <button type="button" class="link" *ngIf="error.folder_id" (click)="browse(error.folder_id)">Browse this folder</button>
      </span>
    </div>
    <span class="hint" *ngIf="hint && !(error && !file && !folder)" [id]="ids.hint">{{ hint }}</span>
  `,
  styles: [`
    :host { display: flex; flex-direction: column; gap: 8px; }
    .label { font-weight: 600; font-size: 15px; color: var(--text-primary); }
    .card {
      display: flex; align-items: center; gap: 14px; padding: 14px 12px 14px 16px;
      background: var(--bg-primary); border: 1px solid var(--border-strong); border-radius: 8px;
    }
    .badge {
      width: 40px; height: 40px; flex-shrink: 0; display: flex; align-items: center; justify-content: center;
      border-radius: 8px; background: var(--color-accent-bg); color: var(--color-accent-text);
    }
    .info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
    .title { font-weight: 600; color: var(--text-primary); }
    .path {
      font-family: var(--font-mono); font-size: 12px; color: var(--text-secondary);
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .meta { font-size: 12px; color: var(--text-tertiary); }
    .card button[mat-icon-button] { color: var(--text-secondary); }
    .files { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
    .compact { gap: 12px; padding: 6px 6px 6px 10px; }
    .compact .badge { width: 32px; height: 32px; }
    .entry { display: flex; align-items: center; gap: 8px; }
    .entry mat-form-field { flex: 1; min-width: 0; margin-top: 0; }
    .entry button { flex-shrink: 0; }
    .error { display: flex; gap: 8px; font-size: 13px; line-height: 1.5; color: var(--color-error-text); }
    .error mat-icon { flex-shrink: 0; font-size: 18px; width: 18px; height: 18px; margin-top: 1px; }
    .link {
      padding: 0; border: 0; background: none; font: inherit; font-weight: 500; color: inherit;
      text-decoration: underline; cursor: pointer;
    }
    .hint { font-size: 12px; color: var(--text-secondary); }
    @media (max-width: 768px) { .card:not(.compact) { flex-wrap: wrap; } .card:not(.compact) .info { flex-basis: calc(100% - 54px); } }
  `],
})
export class HopHerettoFileFieldComponent implements ControlValueAccessor {
  private heretto = inject(HopHerettoService);
  private dialog = inject(MatDialog);
  private cdr = inject(ChangeDetectorRef);

  /** What the field holds: one file (the default), any number of files, or a folder. */
  @Input() selection: HerettoSelectionMode = 'file';
  /** Shown above the field. */
  @Input() label = '';
  /** Shown below the field, e.g. "The map this app publishes." */
  @Input() hint = '';
  /** The browser dialog's subtitle: what the file is for. */
  @Input() purpose = '';
  @Input() dialogTitle?: string;
  /** The kinds of file that can be chosen. Omit for any file; ignored for a folder. */
  @Input() accept: HerettoFileKind[] | null = null;
  /** Read and browse through this connection. Otherwise the organization's first, and the browser offers all. */
  @Input() credentialId: string | null = null;
  /** Makes Browse the primary action while the field is empty. */
  @Input() required = false;
  /** Defaults to a prompt for the selection mode. */
  @Input() placeholder = '';
  /** Where the app's Credentials page is; see `HopHerettoBrowserDialogData.credentialsLink`. */
  @Input() credentialsLink?: string | null;
  /** The value, as it changes (the form control gets it too). */
  @Output() fileChange = new EventEmitter<HerettoFieldValue>();

  readonly ids = (n => ({ label: `hop-hff-${n}-l`, hint: `hop-hff-${n}-h`, error: `hop-hff-${n}-e` }))(nextId++);
  readonly text = new FormControl('', { nonNullable: true });
  readonly placeholders = PLACEHOLDERS;

  file: HerettoFile | null = null;
  files: HerettoFile[] = [];
  folder: HerettoFolder | null = null;
  disabled = false;
  resolving = false;
  error: HerettoFailure | null = null;
  private resolvedText = '';
  private connections$?: Observable<HerettoConnection[]>;
  private onChange: (value: HerettoFieldValue) => void = () => undefined;
  private onTouched: () => void = () => undefined;

  icon(file: HerettoFile): string {
    return ICONS[file.kind];
  }

  kindLabel(file: HerettoFile): string {
    return HERETTO_KIND_LABELS[file.kind];
  }

  slashed(path: string): string {
    return path.startsWith('/') ? path : '/' + path;
  }

  trackId = (_: number, item: HerettoFile) => item.id;

  // ── ControlValueAccessor ────────────────────────────────────────────────

  writeValue(value: HerettoFieldValue): void {
    this.file = this.selection === 'file' ? (value as HerettoFile | null) ?? null : null;
    this.files = this.selection === 'files' && Array.isArray(value) ? [...value] : [];
    this.folder = this.selection === 'folder' ? (value as HerettoFolder | null) ?? null : null;
    this.error = null;
    this.text.setValue('', { emitEvent: false });
    this.resolvedText = '';
    this.cdr.markForCheck();
  }

  registerOnChange(fn: (value: HerettoFieldValue) => void): void {
    this.onChange = fn;
  }

  registerOnTouched(fn: () => void): void {
    this.onTouched = fn;
  }

  setDisabledState(disabled: boolean): void {
    this.disabled = disabled;
    if (disabled) this.text.disable({ emitEvent: false });
    else this.text.enable({ emitEvent: false });
    this.cdr.markForCheck();
  }

  // ── choosing ────────────────────────────────────────────────────────────

  onBlur(): void {
    this.onTouched();
    this.resolveText();
  }

  /** Checks the pasted text against Heretto and, if it names something acceptable, chooses it. */
  resolveText(): void {
    const identifier = this.text.value.trim();
    if (!identifier) {
      this.error = null;
      return;
    }
    if (this.resolving || identifier === this.resolvedText) return;
    this.resolving = true;
    this.resolvedText = identifier;
    const done = () => { this.resolving = false; this.cdr.markForCheck(); };
    const fail = (error: unknown) => { this.error = herettoFailure(error); done(); };

    if (this.selection === 'folder') {
      this.connection().pipe(
        switchMap(connection => this.heretto.resolveFolder(connection.id, null, identifier).pipe(
          map(listing => this.toFolder(listing, connection)),
        )),
      ).subscribe({ next: folder => { this.setFolder(folder); done(); }, error: fail });
      return;
    }
    this.connection().pipe(
      switchMap(connection => this.heretto.resolve(connection.id, identifier)),
    ).subscribe({
      next: file => {
        if (!this.accepts(file.kind)) {
          this.error = { message: `That's ${this.article(file.kind)}. ${this.acceptText}`, reason: 'error', folder_id: file.folder_id };
        } else if (this.selection === 'files') {
          if (this.files.some(f => f.id === file.id)) {
            this.error = { message: `${file.title} is already on the list.`, reason: 'error' };
          } else {
            this.setFiles([...this.files, file]);
          }
        } else {
          this.setFile(file);
        }
        done();
      },
      error: fail,
    });
  }

  /** Opens the browser — at what's chosen, at `folderId`, or where it was last left. */
  browse(folderId?: string | null): void {
    const base: HopHerettoBrowserDialogData = {
      title: this.dialogTitle,
      purpose: this.purpose || undefined,
      credentialsLink: this.credentialsLink,
      folderId: folderId ?? null,
    };
    if (this.selection === 'folder') {
      openHerettoFolderBrowser(this.dialog, {
        ...base,
        credentialId: (!folderId && this.folder?.credential_id) || this.credentialId,
        folderId: folderId ?? this.folder?.id ?? null,
      }).subscribe(folder => { if (folder) this.setFolder(folder); });
    } else if (this.selection === 'files') {
      openHerettoFilesBrowser(this.dialog, {
        ...base,
        accept: this.accept,
        credentialId: this.files[0]?.credential_id || this.credentialId,
        selected: this.files,
      }).subscribe(files => { if (files) this.setFiles(files); });
    } else {
      openHerettoFileBrowser(this.dialog, {
        ...base,
        accept: this.accept,
        credentialId: (!folderId && this.file?.credential_id) || this.credentialId,
        fileId: folderId ? null : this.file?.id ?? null,
      }).subscribe(file => { if (file) this.setFile(file); });
    }
  }

  clear(): void {
    if (this.selection === 'folder') this.setFolder(null);
    else if (this.selection === 'files') this.setFiles([]);
    else this.setFile(null);
  }

  removeFile(id: string): void {
    this.setFiles(this.files.filter(f => f.id !== id));
  }

  private setFile(file: HerettoFile | null): void {
    this.file = file;
    this.emit(file);
  }

  private setFiles(files: HerettoFile[]): void {
    this.files = files;
    this.emit([...files]);
  }

  private setFolder(folder: HerettoFolder | null): void {
    this.folder = folder;
    this.emit(folder);
  }

  private emit(value: HerettoFieldValue): void {
    this.error = null;
    this.text.setValue('', { emitEvent: false });
    this.resolvedText = '';
    this.onChange(value);
    this.onTouched();
    this.fileChange.emit(value);
    this.cdr.markForCheck();
  }

  private toFolder(listing: HerettoFolderListing, connection: HerettoConnection): HerettoFolder {
    const isRoot = listing.name === 'documents' && !!listing.repository && !listing.parent_id;
    return {
      id: listing.id,
      name: isRoot ? listing.repository! : listing.name,
      path: listing.path ?? null,
      branch: listing.branch ?? null,
      repository: listing.repository ?? null,
      credential_id: connection.id,
      credential_name: connection.name,
    };
  }

  /** The connection to read pasted identifiers through: `credentialId`, else the organization's first. */
  private connection(): Observable<HerettoConnection> {
    this.connections$ ??= this.heretto.connections().pipe(shareReplay(1));
    return this.connections$.pipe(map(connections => {
      const connection = this.credentialId ? connections.find(c => c.id === this.credentialId) : connections[0];
      if (!connection) {
        throw { error: { detail: { message: 'No Heretto connection is set up. Add one under Credentials.', reason: 'error' } } };
      }
      return connection;
    }));
  }

  private accepts(kind: HerettoFileKind): boolean {
    return !this.accept?.length || this.accept.includes(kind);
  }

  private get acceptText(): string {
    const names = (this.accept ?? []).map(kind => HERETTO_KIND_LABELS[kind].replace('DITA ', '').toLowerCase());
    if (!names.length) return '';
    const article = /^[aeiou]/.test(names[0]) ? 'an' : 'a';
    return `Choose ${article} ${names.length === 1 ? names[0] : names.slice(0, -1).join(', ') + ' or ' + names[names.length - 1]}.`;
  }

  private article(kind: HerettoFileKind): string {
    const label = HERETTO_KIND_LABELS[kind];
    return (/^[AEIOU]/.test(label) ? 'an ' : 'a ') + label;
  }
}
