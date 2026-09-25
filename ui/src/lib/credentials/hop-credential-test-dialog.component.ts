import { Component, inject, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatDialogModule, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { CredentialTestResult } from './hop-credential.service';

export interface HopCredentialTestDialogData {
  credentialName: string;
  typeLabel: string;
  /** Null while the test is still running. */
  result: CredentialTestResult | null;
}

@Component({
  changeDetection: ChangeDetectionStrategy.Eager,
  selector: 'hop-credential-test-dialog',
  standalone: true,
  imports: [
    CommonModule, MatDialogModule, MatButtonModule, MatIconModule,
    MatProgressSpinnerModule, MatTooltipModule,
  ],
  template: `
    <h2 mat-dialog-title>Test {{ data.credentialName }}</h2>

    <mat-dialog-content>
      <!-- Running -->
      <div class="testing" *ngIf="!data.result">
        <mat-spinner diameter="32"></mat-spinner>
        <p>Contacting {{ data.typeLabel }}…</p>
      </div>

      <ng-container *ngIf="data.result as result">
        <div class="callout" [class.success]="result.success" [class.error]="!result.success">
          <mat-icon>{{ result.success ? 'check_circle' : 'error' }}</mat-icon>
          <div>
            <strong>{{ result.success ? 'Connection successful' : 'Connection failed' }}</strong>
            <p>{{ result.message }}</p>
          </div>
        </div>

        <dl class="facts" *ngIf="result.exchange as exchange">
          <div>
            <dt>Status</dt>
            <dd>
              <span class="hop-status-chip"
                    [class.hop-status-chip-completed]="result.success"
                    [class.hop-status-chip-failed]="!result.success">
                HTTP {{ exchange.status_code ?? '—' }}
              </span>
            </dd>
          </div>
          <div *ngIf="exchange.duration_ms !== null">
            <dt>Took</dt>
            <dd>{{ exchange.duration_ms }} ms</dd>
          </div>
          <div class="wide">
            <dt>Request</dt>
            <dd class="mono">{{ exchange.method }} {{ exchange.url }}</dd>
          </div>
        </dl>

        <ng-container *ngIf="result.exchange as exchange">
          <h3 *ngIf="exchange.response_body">Response</h3>
          <div class="hop-code-panel" *ngIf="exchange.response_body">
            <pre>{{ formatBody(exchange.response_body) }}</pre>
          </div>
          <p class="truncated" *ngIf="exchange.body_truncated">
            The response was longer than this and has been truncated.
          </p>
        </ng-container>

        <!-- Nothing was sent: a URL refused before the request, say. -->
        <p class="no-exchange" *ngIf="!result.exchange">
          No request was made, so there is no response to show.
        </p>

        <dl class="facts" *ngIf="detailKeys.length > 0">
          <div *ngFor="let key of detailKeys">
            <dt>{{ key }}</dt>
            <dd>{{ result.details[key] }}</dd>
          </div>
        </dl>

        <p class="tested-at">Tested {{ result.tested_at | date:'medium' }}</p>
      </ng-container>
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-button type="button"
              *ngIf="data.result?.exchange?.response_body"
              (click)="copyResponse()">
        <mat-icon>content_copy</mat-icon>
        Copy response
      </button>
      <button mat-raised-button color="primary" type="button" (click)="close()">Close</button>
    </mat-dialog-actions>
  `,
  styles: [`
    mat-dialog-content { width: 620px; max-width: 100%; padding: 4px 24px 8px; }

    .testing { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 40px 0; }
    .testing p { margin: 0; color: var(--text-secondary); }

    .callout {
      display: flex; gap: 12px; align-items: flex-start;
      padding: 12px 16px; border-radius: 8px; border: 1px solid transparent;
    }
    .callout strong { display: block; }
    .callout p { margin: 4px 0 0; color: inherit; }
    .callout.success {
      background: var(--color-success-bg); color: var(--color-success-text);
      border-color: var(--color-success-border);
    }
    .callout.error {
      background: var(--color-error-bg); color: var(--color-error-text);
      border-color: var(--color-error-border);
    }

    .facts {
      display: flex; flex-wrap: wrap; gap: 8px 32px;
      margin: 20px 0 0; padding: 0;
    }
    .facts > div { min-width: 0; }
    .facts > div.wide { flex-basis: 100%; }
    dt { color: var(--text-tertiary); font-size: 0.875rem; }
    dd { margin: 2px 0 0; }
    .mono { font-family: var(--font-mono); font-size: 0.875rem; overflow-wrap: anywhere; }

    h3 { margin: 24px 0 8px; font-size: 1rem; }
    .hop-code-panel { max-height: 280px; overflow: auto; }
    .hop-code-panel pre { white-space: pre-wrap; overflow-wrap: anywhere; }

    .truncated, .no-exchange { color: var(--text-tertiary); margin: 8px 0 0; }
    .tested-at { color: var(--text-tertiary); font-size: 0.875rem; margin: 20px 0 0; }

    @media (max-width: 768px) { mat-dialog-content { width: 100%; } }
  `],
})
export class HopCredentialTestDialogComponent {
  private dialogRef = inject(MatDialogRef<HopCredentialTestDialogComponent>);
  data = inject<HopCredentialTestDialogData>(MAT_DIALOG_DATA);

  get detailKeys(): string[] {
    return Object.keys(this.data.result?.details ?? {});
  }

  /** Pretty-print JSON when it is JSON; leave anything else alone. */
  formatBody(body: string): string {
    try {
      return JSON.stringify(JSON.parse(body), null, 2);
    } catch {
      return body;
    }
  }

  copyResponse(): void {
    const body = this.data.result?.exchange?.response_body ?? '';
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(body);
      return;
    }
    const textarea = document.createElement('textarea');
    textarea.value = body;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
  }

  close(): void { this.dialogRef.close(); }
}
