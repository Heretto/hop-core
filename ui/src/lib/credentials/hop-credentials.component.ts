import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { forkJoin } from 'rxjs';
import {
  Credential, CredentialField, CredentialTestResult, CredentialTypeSpec, HopCredentialService,
} from './hop-credential.service';
import { HopConfirmDialogComponent } from '../shared/hop-confirm-dialog.component';
import {
  HopCredentialEditorDialogComponent, HopCredentialEditorResult,
} from './hop-credential-editor-dialog.component';
import {
  HopCredentialTestDialogComponent, HopCredentialTestDialogData,
} from './hop-credential-test-dialog.component';

/** One tab: a single type, or several types that share a group. */
interface CredentialGroup {
  key: string;
  label: string;
  icon: string;
  types: CredentialTypeSpec[];
  /** Columns drawn from the group's summary fields, union across its types. */
  summaryFields: CredentialField[];
  columns: string[];
  credentials: Credential[];
  /** True when any type in the group has a registered tester. */
  testable: boolean;
}

@Component({
  selector: 'hop-credentials',
  standalone: true,
  imports: [
    CommonModule, MatCardModule, MatTableModule, MatButtonModule, MatIconModule,
    MatTabsModule, MatTooltipModule, MatProgressSpinnerModule, MatDialogModule,
    MatSnackBarModule,
  ],
  template: `
    <div class="credentials-container hop-page">
      <h1>Credentials</h1>
      <p class="page-intro">
        Connections this application uses. Secrets are encrypted at rest and never
        sent back to the browser.
      </p>

      <mat-card class="loading-card" *ngIf="loading">
        <mat-card-content>
          <mat-spinner></mat-spinner>
          <p>Loading credentials...</p>
        </mat-card-content>
      </mat-card>

      <div class="empty-state" *ngIf="!loading && groups.length === 0">
        <span class="hop-icon-badge"><mat-icon>key_off</mat-icon></span>
        <h2>No credential types registered</h2>
        <p>
          This application has not registered any credential types, so there is
          nothing to configure yet.
        </p>
      </div>

      <mat-tab-group *ngIf="!loading && groups.length > 0"
                     [(selectedIndex)]="selectedTabIndex">
        <mat-tab *ngFor="let group of groups; trackBy: trackGroup">
          <ng-template mat-tab-label>
            <mat-icon class="tab-icon">{{ group.icon }}</mat-icon>
            {{ group.label }}
          </ng-template>

          <div class="tab-content">
            <div class="header-row">
              <h2>{{ group.label }} ({{ group.credentials.length }})</h2>
              <button mat-raised-button color="primary" (click)="addCredential(group)">
                <mat-icon>add</mat-icon>
                Add {{ group.label }}
              </button>
            </div>

            <table mat-table [dataSource]="group.credentials" class="full-width"
                   *ngIf="group.credentials.length > 0">
              <ng-container matColumnDef="name">
                <th mat-header-cell *matHeaderCellDef>Name</th>
                <td mat-cell *matCellDef="let credential">{{ credential.name }}</td>
              </ng-container>

              <ng-container matColumnDef="type">
                <th mat-header-cell *matHeaderCellDef>Provider</th>
                <td mat-cell *matCellDef="let credential">
                  {{ labelForType(group, credential.type) }}
                </td>
              </ng-container>

              <ng-container *ngFor="let field of group.summaryFields"
                            [matColumnDef]="'field:' + field.name">
                <th mat-header-cell *matHeaderCellDef>{{ field.label }}</th>
                <td mat-cell *matCellDef="let credential" class="value-cell">
                  {{ credential.values[field.name] || '—' }}
                </td>
              </ng-container>

              <ng-container matColumnDef="status">
                <th mat-header-cell *matHeaderCellDef>Last test</th>
                <td mat-cell *matCellDef="let credential">
                  <span class="hop-status-chip hop-status-chip-running"
                        *ngIf="testing.has(credential.id)">Testing…</span>
                  <button class="hop-status-chip result-chip"
                          type="button"
                          [class.hop-status-chip-completed]="results.get(credential.id)?.success"
                          [class.hop-status-chip-failed]="results.get(credential.id)?.success === false"
                          matTooltip="Show the full response"
                          (click)="showResult(credential)"
                          *ngIf="!testing.has(credential.id) && results.has(credential.id)">
                    {{ results.get(credential.id)?.success ? 'Connected' : 'Failed' }}
                  </button>
                  <span class="not-tested"
                        *ngIf="!testing.has(credential.id) && !results.has(credential.id)">—</span>
                </td>
              </ng-container>

              <ng-container matColumnDef="actions">
                <th mat-header-cell *matHeaderCellDef class="actions-header">Actions</th>
                <td mat-cell *matCellDef="let credential">
                  <button mat-icon-button matTooltip="Test connection"
                          *ngIf="group.testable"
                          [disabled]="testing.has(credential.id)"
                          (click)="testCredential(credential)">
                    <mat-spinner *ngIf="testing.has(credential.id)" diameter="20"></mat-spinner>
                    <mat-icon *ngIf="!testing.has(credential.id)">network_check</mat-icon>
                  </button>
                  <button mat-icon-button matTooltip="Edit"
                          (click)="editCredential(group, credential)">
                    <mat-icon>edit</mat-icon>
                  </button>
                  <button mat-icon-button matTooltip="Delete"
                          (click)="deleteCredential(credential)">
                    <mat-icon>delete</mat-icon>
                  </button>
                </td>
              </ng-container>

              <tr mat-header-row *matHeaderRowDef="group.columns"></tr>
              <tr mat-row *matRowDef="let row; columns: group.columns;"></tr>
            </table>

            <div class="no-data" *ngIf="group.credentials.length === 0">
              <mat-icon>{{ group.icon }}</mat-icon>
              <p>No {{ group.label }} credentials yet.</p>
            </div>
          </div>
        </mat-tab>
      </mat-tab-group>
    </div>
  `,
  styles: [`
    h1 { margin-bottom: 4px; }
    .page-intro { max-width: 70ch; margin: 0 0 24px; }
    .tab-icon { margin-right: 8px; }
    .tab-content { padding: 24px 0; }
    .header-row {
      display: flex; justify-content: space-between; align-items: center;
      gap: 16px; margin-bottom: 16px; flex-wrap: wrap;
    }
    .header-row h2 { margin: 0; font-size: 1.125rem; }
    .full-width { width: 100%; }
    .value-cell { overflow-wrap: anywhere; }
    .not-tested { color: var(--text-tertiary); }
    .result-chip { border: none; cursor: pointer; font: inherit; }
    .actions-header { text-align: right; }
    .loading-card { display: flex; justify-content: center; min-height: 200px; text-align: center; }
    .loading-card mat-card-content { display: flex; flex-direction: column; align-items: center; }
    .no-data { text-align: center; padding: 48px 16px; color: var(--text-tertiary); }
    .no-data mat-icon { font-size: 40px; height: 40px; width: 40px; }
    .no-data p { margin: 8px 0 0; }
    .empty-state { text-align: center; padding: 64px 24px; }
    .empty-state h2 { margin: 16px 0 4px; }
    .empty-state p { margin: 0 auto; max-width: 48ch; }
  `],
})
export class HopCredentialsComponent implements OnInit {
  private credentialService = inject(HopCredentialService);
  private dialog = inject(MatDialog);
  private snackBar = inject(MatSnackBar);

  groups: CredentialGroup[] = [];
  loading = false;
  /**
   * Which tab is open. Bound two-way so a refresh after adding a credential
   * leaves the user on the tab they were working in.
   */
  selectedTabIndex = 0;

  /** Credential ids with a test in flight. */
  testing = new Set<string>();
  /** Last test result per credential, for this page view only. */
  results = new Map<string, CredentialTestResult>();

  ngOnInit(): void { this.load(); }

  trackGroup(_index: number, group: CredentialGroup): string { return group.key; }

  /** Full load: registered types never change while the page is open. */
  private load(): void {
    this.loading = true;
    forkJoin({
      types: this.credentialService.listTypes(),
      credentials: this.credentialService.listCredentials(),
    }).subscribe({
      next: ({ types, credentials }) => {
        this.groups = this.buildGroups(types, credentials);
        this.loading = false;
      },
      error: () => {
        this.loading = false;
        this.snackBar.open('Failed to load credentials', 'Close', { duration: 3000 });
      },
    });
  }

  /**
   * Refresh the rows after a change, without rebuilding the tabs.
   *
   * Re-running the full load would replace `groups`, which recreates every
   * tab and drops the user back on the first one — and toggling `loading`
   * would destroy the tab group outright. Only the credentials change here,
   * so only the credentials are refetched.
   */
  private refreshCredentials(): void {
    this.credentialService.listCredentials().subscribe({
      next: credentials => {
        for (const group of this.groups) {
          const typeKeys = new Set(group.types.map(t => t.type));
          // A new array so the table re-renders; the group object survives.
          group.credentials = credentials.filter(c => typeKeys.has(c.type));
        }

        // Drop test results for credentials that no longer exist.
        const liveIds = new Set(credentials.map(c => c.id));
        for (const id of [...this.results.keys()]) {
          if (!liveIds.has(id)) this.results.delete(id);
        }
      },
      error: () => {
        this.snackBar.open('Failed to refresh credentials', 'Close', { duration: 3000 });
      },
    });
  }

  /**
   * One tab per registered type, except that types sharing a `group` collapse
   * into one — which is how three AI providers become a single tab.
   */
  private buildGroups(types: CredentialTypeSpec[], credentials: Credential[]): CredentialGroup[] {
    const groups: CredentialGroup[] = [];
    const byKey = new Map<string, CredentialGroup>();

    for (const type of types) {
      const key = type.group || type.type;
      let group = byKey.get(key);

      if (!group) {
        group = {
          key,
          label: (type.group ? type.group_label : type.label) || type.label,
          icon: type.icon,
          types: [],
          summaryFields: [],
          columns: [],
          credentials: [],
          testable: false,
        };
        byKey.set(key, group);
        groups.push(group);
      }

      group.types.push(type);
      group.testable = group.testable || type.testable;
      for (const field of type.fields) {
        if (field.summary && !group.summaryFields.some(f => f.name === field.name)) {
          group.summaryFields.push(field);
        }
      }
    }

    for (const group of groups) {
      const typeKeys = new Set(group.types.map(t => t.type));
      group.credentials = credentials.filter(c => typeKeys.has(c.type));
      group.columns = [
        'name',
        // Only a grouped tab needs to say which provider a row is.
        ...(group.types.length > 1 ? ['type'] : []),
        ...group.summaryFields.map(f => 'field:' + f.name),
        ...(group.testable ? ['status'] : []),
        'actions',
      ];
    }

    return groups;
  }

  /**
   * Run the test and show the result in a dialog. The dialog opens straight
   * away with a spinner: a failure is exactly when someone wants the detail,
   * and a snackbar is no place to read an HTTP body.
   */
  testCredential(credential: Credential): void {
    const group = this.groups.find(g => g.types.some(t => t.type === credential.type));
    const data: HopCredentialTestDialogData = {
      credentialName: credential.name,
      typeLabel: group ? this.labelForType(group, credential.type) : credential.type,
      result: null,
    };
    const dialogRef = this.dialog.open(HopCredentialTestDialogComponent, {
      width: '660px',
      maxWidth: '95vw',
      data,
    });

    this.testing.add(credential.id);
    this.results.delete(credential.id);

    this.credentialService.testCredential(credential.id).subscribe({
      next: result => {
        this.testing.delete(credential.id);
        this.results.set(credential.id, result);
        data.result = result;
      },
      error: error => {
        this.testing.delete(credential.id);
        const result: CredentialTestResult = {
          success: false,
          message: error?.error?.detail || 'The test could not be run.',
          details: {},
          exchange: null,
          tested_at: new Date().toISOString(),
        };
        this.results.set(credential.id, result);
        data.result = result;
      },
    });

    // Nothing to do on close; the row chip keeps the outcome.
    dialogRef.afterClosed().subscribe();
  }

  /** Reopen the last result for a credential, from its status chip. */
  showResult(credential: Credential): void {
    const result = this.results.get(credential.id);
    if (!result) return;

    const group = this.groups.find(g => g.types.some(t => t.type === credential.type));
    this.dialog.open(HopCredentialTestDialogComponent, {
      width: '660px',
      maxWidth: '95vw',
      data: {
        credentialName: credential.name,
        typeLabel: group ? this.labelForType(group, credential.type) : credential.type,
        result,
      },
    });
  }

  labelForType(group: CredentialGroup, type: string): string {
    return group.types.find(t => t.type === type)?.label ?? type;
  }

  addCredential(group: CredentialGroup): void {
    this.openEditor(group, null).subscribe(result => {
      if (!result) return;
      this.credentialService.createCredential(result).subscribe({
        next: () => {
          this.refreshCredentials();
          this.snackBar.open('Credential added', 'Close', { duration: 3000 });
        },
        error: error => this.showError(error, 'Failed to add credential'),
      });
    });
  }

  editCredential(group: CredentialGroup, credential: Credential): void {
    this.openEditor(group, credential).subscribe(result => {
      if (!result) return;
      this.credentialService.updateCredential(credential.id, {
        name: result.name,
        credentials: result.credentials,
      }).subscribe({
        next: () => {
          this.refreshCredentials();
          this.snackBar.open('Credential saved', 'Close', { duration: 3000 });
        },
        error: error => this.showError(error, 'Failed to save credential'),
      });
    });
  }

  deleteCredential(credential: Credential): void {
    this.dialog.open(HopConfirmDialogComponent, {
      data: {
        title: 'Delete Credential',
        message: `Delete "${credential.name}"? Anything configured to use it stops working.`,
        confirmText: 'Delete',
      },
    }).afterClosed().subscribe(confirmed => {
      if (!confirmed) return;
      this.credentialService.deleteCredential(credential.id).subscribe({
        next: () => {
          this.refreshCredentials();
          this.snackBar.open('Credential deleted', 'Close', { duration: 3000 });
        },
        error: error => this.showError(error, 'Failed to delete credential'),
      });
    });
  }

  private openEditor(group: CredentialGroup, credential: Credential | null) {
    return this.dialog.open(HopCredentialEditorDialogComponent, {
      width: '560px',
      maxWidth: '95vw',
      data: {
        credential,
        // Editing is pinned to the row's own type; adding offers the group.
        types: credential
          ? group.types.filter(t => t.type === credential.type)
          : group.types,
        groupLabel: group.label,
      },
    }).afterClosed();
  }

  private showError(error: any, fallback: string): void {
    this.snackBar.open(error?.error?.detail || fallback, 'Close', { duration: 4000 });
  }
}
