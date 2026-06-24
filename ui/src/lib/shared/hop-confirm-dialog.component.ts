import { Component, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatDialogModule, MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';

export interface HopConfirmDialogData {
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
}

@Component({
  selector: 'hop-confirm-dialog',
  standalone: true,
  imports: [CommonModule, MatDialogModule, MatButtonModule],
  template: `
    <h2 mat-dialog-title>{{ data.title }}</h2>
    <mat-dialog-content><p>{{ data.message }}</p></mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button (click)="onCancel()">{{ data.cancelText || 'Cancel' }}</button>
      <button mat-raised-button color="warn" (click)="onConfirm()">{{ data.confirmText || 'Confirm' }}</button>
    </mat-dialog-actions>
  `,
  styles: [`mat-dialog-content { min-width: 300px; padding: 20px 24px; }`],
})
export class HopConfirmDialogComponent {
  constructor(
    public dialogRef: MatDialogRef<HopConfirmDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: HopConfirmDialogData,
  ) {}
  onCancel(): void { this.dialogRef.close(false); }
  onConfirm(): void { this.dialogRef.close(true); }
}
