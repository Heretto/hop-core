import { Component, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatDialogModule, MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';

export interface HopInviteSuccessDialogData {
  email: string;
  role: string;
  orgName: string;
  inviteUrl: string;
}

@Component({
  selector: 'hop-invite-success-dialog',
  standalone: true,
  imports: [CommonModule, MatDialogModule, MatButtonModule, MatIconModule, MatSnackBarModule],
  template: `
    <h2 mat-dialog-title>Invitation Created</h2>
    <mat-dialog-content>
      <p class="hint">Copy the message below and send it to <strong>{{ data.email }}</strong> via email, Slack, or any other channel.</p>
      <div class="invite-message-block" (click)="copyMessage()">
        <pre>{{ inviteMessage }}</pre>
        <button mat-icon-button class="copy-btn" (click)="copyMessage(); $event.stopPropagation()" matTooltip="Copy to clipboard">
          <mat-icon>content_copy</mat-icon>
        </button>
      </div>
      <p class="copied-hint" *ngIf="copied">Copied to clipboard!</p>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-raised-button color="primary" (click)="copyAndClose()">
        <mat-icon>content_copy</mat-icon>
        Copy & Close
      </button>
      <button mat-button (click)="dialogRef.close()">Close</button>
    </mat-dialog-actions>
  `,
  styles: [`
    mat-dialog-content { min-width: 480px; max-width: 560px; }
    .hint { color: var(--text-secondary); margin-bottom: 16px; font-size: 14px; }
    .invite-message-block {
      position: relative; background: var(--surface-sunken); border: 1px solid var(--border-default);
      border-radius: 8px; padding: 16px; padding-right: 48px; cursor: pointer;
    }
    .invite-message-block:hover { background: var(--hover-overlay); }
    .invite-message-block pre {
      margin: 0; white-space: pre-wrap; word-wrap: break-word;
      font-family: var(--font-mono);
      font-size: 13px; line-height: 1.6; color: var(--text-primary);
    }
    .copy-btn { position: absolute; top: 8px; right: 8px; }
    .copied-hint { color: var(--color-success); font-size: 13px; margin-top: 8px; margin-bottom: 0; }
  `],
})
export class HopInviteSuccessDialogComponent {
  copied = false;
  inviteMessage: string;

  constructor(
    @Inject(MAT_DIALOG_DATA) public data: HopInviteSuccessDialogData,
    public dialogRef: MatDialogRef<HopInviteSuccessDialogComponent>,
    private snackBar: MatSnackBar,
  ) {
    const roleName = data.role === 'admin' ? 'an Administrator' : 'a Member';
    this.inviteMessage =
`You've been invited to join "${data.orgName}" as ${roleName}.

Click the link below to accept the invitation:
${data.inviteUrl}

This invitation will expire in 7 days.`;
  }

  copyMessage(): void {
    this.copyToClipboard(this.inviteMessage).then(() => { this.copied = true; });
  }

  copyAndClose(): void {
    this.copyToClipboard(this.inviteMessage).then(() => {
      this.snackBar.open('Invitation message copied!', 'OK', { duration: 2000 });
      this.dialogRef.close();
    });
  }

  private copyToClipboard(text: string): Promise<void> {
    if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(text);
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
    return Promise.resolve();
  }
}
