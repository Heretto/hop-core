import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import {
  Credential, CredentialField, CredentialTypeSpec,
} from './hop-credential.service';

export interface HopCredentialEditorDialogData {
  /** The credential being edited, or null to create a new one. */
  credential: Credential | null;
  /**
   * The types this form can produce. More than one means a grouped tab (the
   * AI providers, say), and the form shows a picker to choose between them.
   */
  types: CredentialTypeSpec[];
  /** Tab label, used in the dialog title. */
  groupLabel: string;
}

export interface HopCredentialEditorResult {
  type: string;
  name: string;
  credentials: Record<string, any>;
}

@Component({
  selector: 'hop-credential-editor-dialog',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, MatDialogModule, MatButtonModule, MatIconModule,
    MatFormFieldModule, MatInputModule, MatSelectModule,
  ],
  template: `
    <h2 mat-dialog-title>{{ isNew ? 'Add ' + data.groupLabel : 'Edit ' + data.groupLabel }}</h2>

    <mat-dialog-content>
      <form [formGroup]="form">
        <p class="type-description" *ngIf="selectedType?.description">
          {{ selectedType?.description }}
        </p>

        <!-- Only a grouped tab needs this; a single-type tab already knows. -->
        <mat-form-field appearance="outline" class="full-width" *ngIf="data.types.length > 1">
          <mat-label>Provider</mat-label>
          <mat-select formControlName="type" required [disabled]="!isNew">
            <mat-option *ngFor="let type of data.types" [value]="type.type">
              {{ type.label }}
            </mat-option>
          </mat-select>
          <mat-hint *ngIf="!isNew">A credential's provider cannot be changed.</mat-hint>
        </mat-form-field>

        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Name</mat-label>
          <input matInput formControlName="name" required
                 placeholder="How you will recognise this credential">
          <mat-error *ngIf="form.get('name')?.hasError('required')">
            A name is required
          </mat-error>
        </mat-form-field>

        <ng-container *ngFor="let field of fields">
          <mat-form-field appearance="outline" class="full-width"
                          *ngIf="field.type !== 'select'">
            <mat-label>{{ field.label }}</mat-label>
            <textarea *ngIf="field.type === 'textarea'" matInput rows="4"
                      [formControlName]="field.name"
                      [placeholder]="placeholderFor(field)"></textarea>
            <input *ngIf="field.type !== 'textarea'" matInput
                   [type]="inputTypeFor(field)"
                   [formControlName]="field.name"
                   [placeholder]="placeholderFor(field)">
            <mat-hint *ngIf="hintFor(field)">{{ hintFor(field) }}</mat-hint>
            <mat-error *ngIf="form.get(field.name)?.hasError('required')">
              {{ field.label }} is required
            </mat-error>
            <mat-error *ngIf="form.get(field.name)?.hasError('email')">
              Enter a valid email address
            </mat-error>
          </mat-form-field>

          <mat-form-field appearance="outline" class="full-width"
                          *ngIf="field.type === 'select'">
            <mat-label>{{ field.label }}</mat-label>
            <mat-select [formControlName]="field.name">
              <mat-option *ngIf="!field.required" [value]="''">None</mat-option>
              <mat-option *ngFor="let option of field.options" [value]="option.value">
                {{ option.label }}
              </mat-option>
            </mat-select>
            <mat-hint *ngIf="field.help">{{ field.help }}</mat-hint>
          </mat-form-field>
        </ng-container>
      </form>
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-button type="button" (click)="cancel()">Cancel</button>
      <button mat-raised-button color="primary" type="button"
              [disabled]="form.invalid" (click)="save()">
        {{ isNew ? 'Add Credential' : 'Save Changes' }}
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    mat-dialog-content { width: 520px; max-width: 100%; padding: 4px 24px 0; }
    .full-width { width: 100%; }
    .type-description { color: var(--text-tertiary); margin: 0 0 8px; }
    @media (max-width: 768px) { mat-dialog-content { width: 100%; } }
  `],
})
export class HopCredentialEditorDialogComponent implements OnInit {
  private fb = inject(FormBuilder);
  private dialogRef = inject(MatDialogRef<HopCredentialEditorDialogComponent>);
  data = inject<HopCredentialEditorDialogData>(MAT_DIALOG_DATA);

  form: FormGroup = this.fb.group({
    type: ['', Validators.required],
    name: ['', Validators.required],
  });

  get isNew(): boolean { return !this.data.credential; }

  get selectedType(): CredentialTypeSpec | undefined {
    const type = this.form.get('type')?.value;
    return this.data.types.find(t => t.type === type) ?? this.data.types[0];
  }

  get fields(): CredentialField[] { return this.selectedType?.fields ?? []; }

  ngOnInit(): void {
    const credential = this.data.credential;
    this.form.patchValue({
      type: credential?.type ?? this.data.types[0]?.type ?? '',
      name: credential?.name ?? '',
    });

    this.buildFieldControls();
    // Switching provider on a new credential swaps the whole field set.
    this.form.get('type')!.valueChanges.subscribe(() => this.buildFieldControls());
  }

  /** Rebuild the per-field controls for whichever type is selected. */
  private buildFieldControls(): void {
    for (const name of Object.keys(this.form.controls)) {
      if (name !== 'type' && name !== 'name') this.form.removeControl(name);
    }

    const stored = this.data.credential?.values ?? {};
    for (const field of this.fields) {
      const validators = [];
      // A stored secret stays stored: the form never receives it, so blank
      // means "keep it" and requiring a value would block every other edit.
      if (field.required && !(field.secret && this.hasStoredSecret(field))) {
        validators.push(Validators.required);
      }
      if (field.type === 'email') validators.push(Validators.email);

      this.form.addControl(
        field.name,
        this.fb.control(field.secret ? '' : (stored[field.name] ?? ''), validators),
      );
    }
  }

  hasStoredSecret(field: CredentialField): boolean {
    return (this.data.credential?.secrets_set ?? []).includes(field.name);
  }

  inputTypeFor(field: CredentialField): string {
    if (field.type === 'password') return 'password';
    if (field.type === 'email') return 'email';
    return 'text';
  }

  placeholderFor(field: CredentialField): string {
    if (field.secret && this.hasStoredSecret(field)) return 'Leave blank to keep the current value';
    return field.placeholder;
  }

  hintFor(field: CredentialField): string {
    if (field.secret && this.hasStoredSecret(field)) {
      return field.help
        ? `${field.help} Leave blank to keep the stored value.`
        : 'Leave blank to keep the stored value.';
    }
    return field.help;
  }

  save(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const value = this.form.getRawValue();
    const credentials: Record<string, any> = {};
    for (const field of this.fields) {
      const fieldValue = (value[field.name] ?? '').toString().trim();
      // Omit a blank secret entirely so the backend leaves the stored one be.
      if (field.secret && !fieldValue) continue;
      credentials[field.name] = fieldValue;
    }

    const result: HopCredentialEditorResult = {
      type: value.type,
      name: (value.name ?? '').trim(),
      credentials,
    };
    this.dialogRef.close(result);
  }

  cancel(): void { this.dialogRef.close(); }
}
