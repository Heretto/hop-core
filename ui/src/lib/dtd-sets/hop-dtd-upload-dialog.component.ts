import {
  ChangeDetectionStrategy, ChangeDetectorRef, Component, DestroyRef, inject,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { Subscription, switchMap, takeWhile, timer } from 'rxjs';
import { DtdSetVersion, HopDtdSetService } from './hop-dtd-set.service';

/** Opens the dialog for a new set, or for a new version of `setId`. */
export interface HopDtdUploadDialogData {
  maxUploadMb: number;
  setId?: string;
  setName?: string;
}

/** Closes with the version that was uploaded, or undefined if nothing was. */
export interface HopDtdUploadDialogResult {
  dtdSetId: string;
  versionId: string;
  status: DtdSetVersion['status'];
}

@Component({
  changeDetection: ChangeDetectionStrategy.Eager,
  selector: 'hop-dtd-upload-dialog',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, MatDialogModule, MatButtonModule, MatFormFieldModule,
    MatInputModule, MatIconModule, MatProgressSpinnerModule,
  ],
  template: `
    <div class="dialog-head">
      <div>
        <h2 mat-dialog-title>{{ isNewVersion ? 'Upload new version' : 'Upload DTD set' }}</h2>
        <p class="subtitle" *ngIf="version">{{ title }} · {{ version.label }}</p>
        <p class="subtitle" *ngIf="!version && isNewVersion">{{ data.setName }}</p>
      </div>
      <button mat-icon-button type="button" aria-label="Close" (click)="close()">
        <mat-icon>close</mat-icon>
      </button>
    </div>

    <mat-dialog-content>
      <!-- Choose the zip -->
      <form *ngIf="!version" [formGroup]="form" (ngSubmit)="submit()" id="dtd-upload-form">
        <label class="drop-zone" [class.has-file]="file" [class.dragging]="dragging"
               (dragover)="$event.preventDefault(); dragging = true" (dragleave)="dragging = false"
               (drop)="onDrop($event)">
          <input type="file" accept=".zip,application/zip" (change)="onPick($event)" hidden>
          <mat-icon>{{ file ? 'folder_zip' : 'upload_file' }}</mat-icon>
          <span *ngIf="!file">Choose a .zip, or drop it here</span>
          <span *ngIf="file" class="file-name">{{ file.name }}</span>
          <span class="hint">{{ file ? formatSize(file.size) : 'Up to ' + data.maxUploadMb + ' MB' }}</span>
        </label>

        <mat-form-field appearance="outline" class="full-width" *ngIf="!isNewVersion">
          <mat-label>Name</mat-label>
          <input matInput formControlName="name" placeholder="Acme Product DITA" required>
        </mat-form-field>
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Version</mat-label>
          <input matInput formControlName="version" placeholder="v1.0" required>
        </mat-form-field>
        <mat-form-field appearance="outline" class="full-width" *ngIf="!isNewVersion">
          <mat-label>Description (optional)</mat-label>
          <input matInput formControlName="description" placeholder="Product documentation DTDs with Acme specializations">
        </mat-form-field>
        <p class="error-text" *ngIf="error">{{ error }}</p>
      </form>

      <!-- Processing -->
      <ng-container *ngIf="version">
        <div class="file-box">
          <mat-icon>description</mat-icon>
          <span class="file-name">{{ version.filename }}</span>
          <span class="size">{{ formatSize(version.size_bytes) }}</span>
        </div>
        <ol class="steps">
          <li *ngFor="let step of version.steps" [class]="'step ' + step.state">
            <span class="marker" [attr.aria-label]="step.state">
              <mat-icon *ngIf="step.state === 'done'">check</mat-icon>
              <mat-icon *ngIf="step.state === 'failed'">close</mat-icon>
              <mat-spinner *ngIf="step.state === 'running'" diameter="16"></mat-spinner>
            </span>
            <span class="step-text">
              <span class="step-label">{{ step.label }}</span>
              <span class="step-detail" *ngIf="step.detail || stepHint(step.key)">{{ step.detail || stepHint(step.key) }}</span>
            </span>
            <span class="step-state">{{ stateLabel(step.state) }}</span>
          </li>
        </ol>
        <p class="note" *ngIf="version.status === 'processing'">
          You can close this dialog. Processing continues, and the set shows as Processing in the
          list until it's ready.
        </p>
        <p class="note ready" *ngIf="version.status === 'ready'">
          Ready. {{ isNewVersion ? 'Apps now validate against this version.' : 'Make it the organization default, or choose it on an agent.' }}
        </p>
        <p class="note failed" *ngIf="version.status === 'failed'">
          {{ isNewVersion ? 'The current version stays in use.' : 'The set can\\'t be used until a version processes successfully.' }}
          Fix the zip and upload it again.
        </p>
      </ng-container>
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <ng-container *ngIf="!version">
        <button mat-button type="button" (click)="close()">Cancel</button>
        <button mat-raised-button color="primary" type="submit" form="dtd-upload-form"
                [disabled]="!file || form.invalid || uploading">
          <mat-spinner diameter="18" *ngIf="uploading"></mat-spinner>
          <span *ngIf="!uploading">Upload</span>
        </button>
      </ng-container>
      <button mat-stroked-button type="button" *ngIf="version" (click)="close()">Close</button>
    </mat-dialog-actions>
  `,
  styles: [`
    :host { display: block; width: 560px; max-width: 100%; }
    .dialog-head { display: flex; align-items: flex-start; justify-content: space-between; padding: 8px 8px 0 0; }
    .dialog-head h2 { margin-bottom: 0; }
    .subtitle { margin: -4px 0 0 24px; color: var(--text-tertiary); font-size: 0.86rem; }
    .full-width { width: 100%; }
    .drop-zone {
      display: flex; flex-direction: column; align-items: center; gap: 4px;
      padding: 24px 16px; margin-bottom: 8px; cursor: pointer; text-align: center;
      border: 1px dashed var(--border-strong); border-radius: 8px; color: var(--text-secondary);
    }
    .drop-zone:hover, .drop-zone.dragging { background: var(--hover-overlay); }
    .drop-zone.has-file { border-style: solid; }
    .drop-zone mat-icon { color: var(--text-tertiary); }
    .drop-zone .hint { color: var(--text-tertiary); font-size: 0.82rem; }
    .file-name { font-family: var(--font-mono); font-size: 0.86rem; overflow-wrap: anywhere; }
    .file-box {
      display: flex; align-items: center; gap: 12px; padding: 12px 16px; margin-bottom: 16px;
      border: 1px solid var(--border-default); border-radius: 8px;
    }
    .file-box mat-icon { color: var(--text-tertiary); }
    .file-box .file-name { flex: 1; }
    .file-box .size { color: var(--text-tertiary); font-size: 0.86rem; }
    .steps { list-style: none; margin: 0; padding: 0; }
    .step { display: flex; align-items: flex-start; gap: 12px; padding: 8px 0; }
    .marker {
      flex: none; width: 24px; height: 24px; border-radius: 50%; margin-top: 1px;
      display: inline-flex; align-items: center; justify-content: center;
      border: 1.5px solid var(--border-strong);
    }
    .marker mat-icon { font-size: 16px; width: 16px; height: 16px; }
    .done .marker { border: none; background: var(--color-success-bg); color: var(--color-success); }
    .failed .marker { border: none; background: var(--color-error-bg); color: var(--color-error); }
    .running .marker { border: none; }
    .step-text { flex: 1; display: flex; flex-direction: column; }
    .step-label { font-weight: 500; color: var(--text-primary); }
    .pending .step-label { color: var(--text-secondary); }
    .step-detail { color: var(--text-tertiary); font-size: 0.82rem; overflow-wrap: anywhere; }
    .failed .step-detail { color: var(--color-error-text); }
    .step-state { color: var(--text-tertiary); font-size: 0.82rem; }
    .note { margin: 16px 0 0; color: var(--text-secondary); }
    .note.ready { color: var(--color-success-text); }
    .note.failed { color: var(--color-error-text); }
    .error-text { color: var(--color-error-text); margin: 0; }
    mat-spinner { display: inline-block; }
  `],
})
export class HopDtdUploadDialogComponent {
  readonly data = inject<HopDtdUploadDialogData>(MAT_DIALOG_DATA);
  private dialogRef = inject(MatDialogRef<HopDtdUploadDialogComponent, HopDtdUploadDialogResult>);
  private service = inject(HopDtdSetService);
  private cdr = inject(ChangeDetectorRef);
  private fb = inject(FormBuilder);

  readonly isNewVersion = !!this.data.setId;
  file: File | null = null;
  dragging = false;
  uploading = false;
  error = '';
  version: DtdSetVersion | null = null;
  private polling?: Subscription;

  form = this.fb.group({
    name: [this.data.setName ?? '', this.isNewVersion ? [] : [Validators.required]],
    version: ['v1.0', Validators.required],
    description: [''],
  });

  constructor() {
    inject(DestroyRef).onDestroy(() => this.polling?.unsubscribe());
  }

  get title(): string {
    return this.isNewVersion ? (this.data.setName ?? '') : (this.form.value.name ?? '');
  }

  onPick(event: Event): void {
    this.setFile((event.target as HTMLInputElement).files?.[0] ?? null);
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.dragging = false;
    this.setFile(event.dataTransfer?.files?.[0] ?? null);
  }

  private setFile(file: File | null): void {
    this.error = '';
    if (file && !file.name.toLowerCase().endsWith('.zip')) {
      this.error = 'Choose a .zip file.';
      return;
    }
    if (file && file.size > this.data.maxUploadMb * 1024 * 1024) {
      this.error = `That zip is larger than ${this.data.maxUploadMb} MB.`;
      return;
    }
    this.file = file;
    if (file && !this.isNewVersion && !this.form.value.name) {
      // Offer the file name as a starting point: acme-product-dita-2.3.zip -> "acme product dita 2.3"
      this.form.patchValue({ name: file.name.replace(/\.zip$/i, '').replace(/[-_]+/g, ' ') });
    }
  }

  submit(): void {
    if (!this.file || this.form.invalid || this.uploading) return;
    const { name, version, description } = this.form.getRawValue();
    this.uploading = true;
    this.error = '';
    const request = this.isNewVersion
      ? this.service.uploadVersion(this.data.setId!, this.file, (version ?? '').trim())
      : this.service.upload(this.file, (name ?? '').trim(), (version ?? '').trim(), (description ?? '').trim());
    request.subscribe({
      next: version => {
        this.uploading = false;
        this.version = version;
        this.cdr.markForCheck();
        this.poll();
      },
      error: err => {
        this.uploading = false;
        this.error = err?.error?.detail || 'The upload failed.';
        this.cdr.markForCheck();
      },
    });
  }

  private poll(): void {
    const v = this.version!;
    this.polling = timer(1000, 1000).pipe(
      switchMap(() => this.service.getVersion(v.dtd_set_id, v.id)),
      takeWhile(version => version.status === 'processing', true),
    ).subscribe(version => {
      this.version = version;
      this.cdr.markForCheck();
    });
  }

  stateLabel(state: string): string {
    return { done: 'Done', running: 'Running', failed: 'Failed', pending: '' }[state] ?? '';
  }

  /** The mock's quiet descriptions, shown until a step reports its own detail. */
  stepHint(key: string): string {
    return {
      compile: 'Indexes each document type for validation',
      test: 'Loads each document type to prove it compiles',
    }[key] ?? '';
  }

  formatSize(bytes: number): string {
    return bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
  }

  close(): void {
    this.dialogRef.close(this.version
      ? { dtdSetId: this.version.dtd_set_id, versionId: this.version.id, status: this.version.status }
      : undefined);
  }
}
