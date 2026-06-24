import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, Validators, ReactiveFormsModule } from '@angular/forms';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

@Component({
  selector: 'hop-invite-dialog',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, MatDialogModule, MatButtonModule,
    MatFormFieldModule, MatInputModule, MatSelectModule, MatProgressSpinnerModule,
  ],
  template: `
    <h2 mat-dialog-title>Invite New Member</h2>
    <mat-dialog-content>
      <form [formGroup]="inviteForm">
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Email Address</mat-label>
          <input matInput type="email" formControlName="email" required>
          <mat-error *ngIf="inviteForm.get('email')?.hasError('required')">Email is required</mat-error>
          <mat-error *ngIf="inviteForm.get('email')?.hasError('email')">Please enter a valid email</mat-error>
        </mat-form-field>
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Role</mat-label>
          <mat-select formControlName="role" required>
            <mat-option value="member">Member</mat-option>
            <mat-option value="admin">Administrator</mat-option>
          </mat-select>
          <mat-error *ngIf="inviteForm.get('role')?.hasError('required')">Role is required</mat-error>
        </mat-form-field>
      </form>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button (click)="onCancel()">Cancel</button>
      <button mat-raised-button color="primary" [disabled]="!inviteForm.valid" (click)="onSubmit()">
        Send Invitation
      </button>
    </mat-dialog-actions>
  `,
  styles: [`.full-width { width: 100%; margin-bottom: 16px; } mat-dialog-content { min-width: 400px; }`],
})
export class HopInviteDialogComponent {
  private fb = inject(FormBuilder);
  private dialogRef = inject(MatDialogRef<HopInviteDialogComponent>);

  inviteForm = this.fb.group({
    email: ['', [Validators.required, Validators.email]],
    role: ['member', Validators.required],
  });

  onCancel(): void { this.dialogRef.close(); }
  onSubmit(): void { if (this.inviteForm.valid) this.dialogRef.close(this.inviteForm.value); }
}
