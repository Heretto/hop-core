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
import { Observable, map, of, switchMap } from 'rxjs';
import {
  HERETTO_KIND_LABELS, HerettoFailure, HerettoFile, HerettoFileKind, HopHerettoService, herettoFailure,
} from './hop-heretto.service';
import { openHerettoFileBrowser } from './hop-heretto-browser-dialog.component';

const ICONS: Record<HerettoFileKind, string> = {
  map: 'account_tree', topic: 'description', image: 'image', other: 'draft',
};
let nextId = 0;

/**
 * A form control holding one Heretto file: paste a file ID, Heretto URL or
 * repository path, or browse for it. Shows the chosen file as a card with
 * Change and Remove. The value is a `HerettoFile`, or null.
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

    <div class="card" *ngIf="value" role="group" [attr.aria-labelledby]="label ? ids.label : null">
      <span class="badge"><mat-icon>{{ icon }}</mat-icon></span>
      <span class="info">
        <span class="title">{{ value.title }}</span>
        <span class="path" *ngIf="value.path" [title]="location">{{ location }}</span>
        <span class="meta">{{ kindLabel }} · {{ value.credential_name }}</span>
      </span>
      <button mat-stroked-button type="button" [disabled]="disabled" (click)="browse()">Change</button>
      <button mat-icon-button type="button" [attr.aria-label]="'Remove ' + (label || 'file').toLowerCase()"
              [disabled]="disabled" (click)="clear()"><mat-icon>close</mat-icon></button>
    </div>

    <div class="entry" *ngIf="!value">
      <mat-form-field subscriptSizing="dynamic">
        <input matInput [formControl]="text" [placeholder]="placeholder"
               [attr.aria-label]="(label || 'Heretto file') + ' ID, URL or path'"
               [attr.aria-invalid]="!!error" [attr.aria-describedby]="error ? ids.error : (hint ? ids.hint : null)"
               (keydown.enter)="resolveText(); $event.preventDefault()" (blur)="onBlur()">
        <mat-spinner matSuffix diameter="18" *ngIf="resolving"></mat-spinner>
      </mat-form-field>
      <button *ngIf="required" mat-flat-button color="primary" type="button" [disabled]="disabled" (click)="browse()">
        Browse…
      </button>
      <button *ngIf="!required" mat-stroked-button type="button" [disabled]="disabled" (click)="browse()">
        <mat-icon>folder_open</mat-icon> Browse…
      </button>
    </div>

    <div class="error" *ngIf="error && !value" [id]="ids.error" role="alert">
      <mat-icon>error</mat-icon>
      <span>{{ error.message }}
        <button type="button" class="link" *ngIf="error.folder_id" (click)="browse(error.folder_id)">Browse this folder</button>
      </span>
    </div>
    <span class="hint" *ngIf="hint && !(error && !value)" [id]="ids.hint">{{ hint }}</span>
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
    @media (max-width: 768px) { .card { flex-wrap: wrap; } .info { flex-basis: calc(100% - 54px); } }
  `],
})
export class HopHerettoFileFieldComponent implements ControlValueAccessor {
  private heretto = inject(HopHerettoService);
  private dialog = inject(MatDialog);
  private cdr = inject(ChangeDetectorRef);

  /** Shown above the field. */
  @Input() label = '';
  /** Shown below the field, e.g. "The map this app publishes." */
  @Input() hint = '';
  /** The browser dialog's subtitle: what the file is for. */
  @Input() purpose = '';
  @Input() dialogTitle?: string;
  /** The kinds that can be chosen. Omit for any file. */
  @Input() accept: HerettoFileKind[] | null = null;
  /** Read and browse through this connection. Otherwise the organization's first, and the browser offers all. */
  @Input() credentialId: string | null = null;
  /** Makes Browse the primary action while the field is empty. */
  @Input() required = false;
  @Input() placeholder = 'Paste a file ID, Heretto URL or repository path';
  /** Where the app's Credentials page is; see `HopHerettoBrowserDialogData.credentialsLink`. */
  @Input() credentialsLink?: string | null;
  /** The chosen file, as it changes (the form control gets it too). */
  @Output() fileChange = new EventEmitter<HerettoFile | null>();

  readonly ids = (n => ({ label: `hop-hff-${n}-l`, hint: `hop-hff-${n}-h`, error: `hop-hff-${n}-e` }))(nextId++);
  readonly text = new FormControl('', { nonNullable: true });

  value: HerettoFile | null = null;
  disabled = false;
  resolving = false;
  error: HerettoFailure | null = null;
  private resolvedText = '';
  private onChange: (value: HerettoFile | null) => void = () => undefined;
  private onTouched: () => void = () => undefined;

  get icon(): string {
    return this.value ? ICONS[this.value.kind] : 'draft';
  }

  get kindLabel(): string {
    return this.value ? HERETTO_KIND_LABELS[this.value.kind] : '';
  }

  get location(): string {
    const path = this.value?.path ?? '';
    return path.startsWith('/') ? path : '/' + path;
  }

  // ── ControlValueAccessor ────────────────────────────────────────────────

  writeValue(value: HerettoFile | null): void {
    this.value = value ?? null;
    this.error = null;
    this.text.setValue('', { emitEvent: false });
    this.resolvedText = '';
    this.cdr.markForCheck();
  }

  registerOnChange(fn: (value: HerettoFile | null) => void): void {
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

  /** Checks the pasted text against Heretto and, if it names an acceptable file, chooses it. */
  resolveText(): void {
    const identifier = this.text.value.trim();
    if (!identifier) {
      this.error = null;
      return;
    }
    if (this.resolving || identifier === this.resolvedText) return;
    this.resolving = true;
    this.resolvedText = identifier;
    this.connection().pipe(
      switchMap(credentialId => this.heretto.resolve(credentialId, identifier)),
    ).subscribe({
      next: file => {
        this.resolving = false;
        if (this.accepts(file.kind)) {
          this.set(file);
        } else {
          this.error = { message: `That's ${this.article(file.kind)}. ${this.acceptText}`, reason: 'error', folder_id: file.folder_id };
        }
        this.cdr.markForCheck();
      },
      error: error => {
        this.resolving = false;
        this.error = herettoFailure(error);
        this.cdr.markForCheck();
      },
    });
  }

  /** Opens the browser — at the chosen file, at `folderId`, or where it was last left. */
  browse(folderId?: string | null): void {
    openHerettoFileBrowser(this.dialog, {
      title: this.dialogTitle,
      purpose: this.purpose || undefined,
      accept: this.accept,
      credentialId: (!folderId && this.value?.credential_id) || this.credentialId,
      fileId: folderId ? null : this.value?.id ?? null,
      folderId: folderId ?? null,
      credentialsLink: this.credentialsLink,
    }).subscribe(file => {
      if (file) this.set(file);
    });
  }

  clear(): void {
    this.set(null);
  }

  private set(file: HerettoFile | null): void {
    this.value = file;
    this.error = null;
    this.text.setValue('', { emitEvent: false });
    this.resolvedText = '';
    this.onChange(file);
    this.onTouched();
    this.fileChange.emit(file);
    this.cdr.markForCheck();
  }

  private connection(): Observable<string> {
    if (this.credentialId) return of(this.credentialId);
    return this.heretto.connections().pipe(map(connections => {
      if (!connections.length) throw { error: { detail: { message: 'No Heretto connection is set up. Add one under Credentials.', reason: 'error' } } };
      return connections[0].id;
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
