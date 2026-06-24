import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, Validators, ReactiveFormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTabsModule } from '@angular/material/tabs';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatDialogModule, MatDialog } from '@angular/material/dialog';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatChipsModule } from '@angular/material/chips';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatMenuModule } from '@angular/material/menu';
import { HopOrganizationService, Organization, OrganizationMember, OrganizationInvitation } from '../shared/hop-organization.service';
import { HopAccountService } from '../shared/hop-account.service';
import { HopConfirmDialogComponent } from '../shared/hop-confirm-dialog.component';
import { HopInviteDialogComponent } from './hop-invite-dialog.component';
import { HopInviteSuccessDialogComponent } from '../shared/hop-invite-success-dialog.component';

@Component({
  selector: 'hop-admin',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, MatCardModule, MatTableModule, MatButtonModule,
    MatIconModule, MatTabsModule, MatFormFieldModule, MatInputModule, MatSelectModule,
    MatDialogModule, MatSnackBarModule, MatProgressSpinnerModule, MatChipsModule,
    MatTooltipModule, MatMenuModule,
  ],
  template: `
    <div class="admin-container">
      <h1>Organization Administration</h1>

      <mat-card class="org-info-card">
        <mat-card-header>
          <mat-card-title>{{ organization?.name }}</mat-card-title>
          <mat-card-subtitle>Organization Settings</mat-card-subtitle>
        </mat-card-header>
        <mat-card-content>
          <form [formGroup]="orgForm" (ngSubmit)="updateOrganization()">
            <mat-form-field appearance="outline" class="full-width">
              <mat-label>Organization Name</mat-label>
              <input matInput formControlName="name" required>
              <mat-error *ngIf="orgForm.get('name')?.hasError('required')">Organization name is required</mat-error>
            </mat-form-field>
            <button mat-raised-button color="primary" type="submit"
                    [disabled]="!orgForm.valid || !orgForm.dirty || updatingOrg">
              <mat-spinner diameter="20" *ngIf="updatingOrg"></mat-spinner>
              <span *ngIf="!updatingOrg">Update Organization</span>
            </button>
          </form>
        </mat-card-content>
      </mat-card>

      <mat-tab-group>
        <!-- Members Tab -->
        <mat-tab label="Members">
          <div class="tab-content">
            <div class="members-header">
              <h2>Organization Members ({{ members.length }})</h2>
              <button mat-raised-button color="primary" (click)="openInviteDialog()">
                <mat-icon>person_add</mat-icon>
                Invite Member
              </button>
            </div>

            <mat-card *ngIf="loadingMembers" class="loading-card">
              <mat-card-content>
                <mat-spinner></mat-spinner>
                <p>Loading members...</p>
              </mat-card-content>
            </mat-card>

            <table mat-table [dataSource]="members" class="members-table" *ngIf="!loadingMembers">
              <ng-container matColumnDef="email">
                <th mat-header-cell *matHeaderCellDef>Email</th>
                <td mat-cell *matCellDef="let member">{{ member.user_email }}</td>
              </ng-container>
              <ng-container matColumnDef="role">
                <th mat-header-cell *matHeaderCellDef>Role</th>
                <td mat-cell *matCellDef="let member">
                  <mat-chip-set>
                    <mat-chip [color]="member.role === 'admin' ? 'accent' : 'primary'" selected>
                      {{ member.role | uppercase }}
                    </mat-chip>
                  </mat-chip-set>
                </td>
              </ng-container>
              <ng-container matColumnDef="joined">
                <th mat-header-cell *matHeaderCellDef>Joined</th>
                <td mat-cell *matCellDef="let member">{{ member.joined_at | date:'short' }}</td>
              </ng-container>
              <ng-container matColumnDef="actions">
                <th mat-header-cell *matHeaderCellDef>Actions</th>
                <td mat-cell *matCellDef="let member">
                  <button mat-icon-button [matMenuTriggerFor]="memberMenu" [disabled]="isCurrentUser(member)">
                    <mat-icon>more_vert</mat-icon>
                  </button>
                  <mat-menu #memberMenu="matMenu">
                    <button mat-menu-item (click)="toggleRole(member)" [disabled]="!canChangeRole(member)">
                      <mat-icon>swap_horiz</mat-icon>
                      <span>{{ member.role === 'admin' ? 'Make Member' : 'Make Admin' }}</span>
                    </button>
                    <button mat-menu-item (click)="removeMember(member)" [disabled]="!canRemoveMember(member)">
                      <mat-icon>person_remove</mat-icon>
                      <span>Remove from Organization</span>
                    </button>
                  </mat-menu>
                </td>
              </ng-container>
              <tr mat-header-row *matHeaderRowDef="memberColumns"></tr>
              <tr mat-row *matRowDef="let row; columns: memberColumns;"></tr>
            </table>

            <div class="no-data" *ngIf="!loadingMembers && members.length === 0">
              <mat-icon>group_off</mat-icon><p>No members found</p>
            </div>
          </div>
        </mat-tab>

        <!-- Invitations Tab -->
        <mat-tab label="Pending Invitations">
          <div class="tab-content">
            <div class="invitations-header">
              <h2>Pending Invitations ({{ invitations.length }})</h2>
            </div>

            <mat-card *ngIf="loadingInvitations" class="loading-card">
              <mat-card-content><mat-spinner></mat-spinner><p>Loading invitations...</p></mat-card-content>
            </mat-card>

            <table mat-table [dataSource]="invitations" class="invitations-table" *ngIf="!loadingInvitations">
              <ng-container matColumnDef="email">
                <th mat-header-cell *matHeaderCellDef>Email</th>
                <td mat-cell *matCellDef="let inv">{{ inv.email }}</td>
              </ng-container>
              <ng-container matColumnDef="role">
                <th mat-header-cell *matHeaderCellDef>Role</th>
                <td mat-cell *matCellDef="let inv">
                  <mat-chip-set>
                    <mat-chip [color]="inv.role === 'admin' ? 'accent' : 'primary'" selected>
                      {{ inv.role | uppercase }}
                    </mat-chip>
                  </mat-chip-set>
                </td>
              </ng-container>
              <ng-container matColumnDef="invitedBy">
                <th mat-header-cell *matHeaderCellDef>Invited By</th>
                <td mat-cell *matCellDef="let inv">{{ inv.invited_by_email }}</td>
              </ng-container>
              <ng-container matColumnDef="expires">
                <th mat-header-cell *matHeaderCellDef>Expires</th>
                <td mat-cell *matCellDef="let inv">{{ inv.expires_at | date:'short' }}</td>
              </ng-container>
              <ng-container matColumnDef="actions">
                <th mat-header-cell *matHeaderCellDef>Actions</th>
                <td mat-cell *matCellDef="let inv">
                  <button mat-icon-button matTooltip="Copy Invitation Link" (click)="copyInvitationLink(inv)">
                    <mat-icon>content_copy</mat-icon>
                  </button>
                  <button mat-icon-button matTooltip="Cancel Invitation" (click)="cancelInvitation(inv)">
                    <mat-icon>cancel</mat-icon>
                  </button>
                </td>
              </ng-container>
              <tr mat-header-row *matHeaderRowDef="invitationColumns"></tr>
              <tr mat-row *matRowDef="let row; columns: invitationColumns;"></tr>
            </table>

            <div class="no-data" *ngIf="!loadingInvitations && invitations.length === 0">
              <mat-icon>mail_outline</mat-icon><p>No pending invitations</p>
            </div>
          </div>
        </mat-tab>
      </mat-tab-group>
    </div>
  `,
  styles: [`
    .admin-container { max-width: 1200px; margin: 0 auto; }
    .org-info-card { margin-bottom: 24px; }
    .full-width { width: 100%; margin-bottom: 16px; }
    .tab-content { padding: 24px; }
    .members-header, .invitations-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
    .members-table, .invitations-table { width: 100%; background: white; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    .loading-card { display: flex; justify-content: center; align-items: center; min-height: 200px; text-align: center; }
    .loading-card mat-card-content { display: flex; flex-direction: column; align-items: center; }
    .no-data { text-align: center; padding: 48px; color: #999; }
    .no-data mat-icon { font-size: 64px; height: 64px; width: 64px; margin-bottom: 16px; }
    mat-spinner { display: inline-block; margin-right: 8px; }
  `],
})
export class HopAdminComponent implements OnInit {
  private fb = inject(FormBuilder);
  private organizationService = inject(HopOrganizationService);
  private accountService = inject(HopAccountService);
  private dialog = inject(MatDialog);
  private snackBar = inject(MatSnackBar);

  organization: Organization | null = null;
  members: OrganizationMember[] = [];
  invitations: OrganizationInvitation[] = [];

  loadingMembers = false;
  loadingInvitations = false;
  updatingOrg = false;

  memberColumns = ['email', 'role', 'joined', 'actions'];
  invitationColumns = ['email', 'role', 'invitedBy', 'expires', 'actions'];

  orgForm = this.fb.group({ name: ['', Validators.required] });

  ngOnInit(): void {
    this.loadOrganization();
    this.loadMembers();
    this.loadInvitations();
  }

  private loadOrganization(): void {
    this.organizationService.getCurrentOrganization().subscribe({
      next: org => {
        this.organization = org;
        this.orgForm.patchValue({ name: org.name });
      },
    });
  }

  private loadMembers(): void {
    this.loadingMembers = true;
    this.organizationService.listMembers().subscribe({
      next: members => { this.members = members; this.loadingMembers = false; },
      error: () => { this.loadingMembers = false; },
    });
  }

  private loadInvitations(): void {
    this.loadingInvitations = true;
    this.organizationService.listInvitations().subscribe({
      next: invitations => { this.invitations = invitations; this.loadingInvitations = false; },
      error: () => { this.loadingInvitations = false; },
    });
  }

  updateOrganization(): void {
    if (!this.orgForm.valid || !this.orgForm.dirty) return;
    this.updatingOrg = true;
    const name = this.orgForm.get('name')?.value;
    if (!name) return;
    this.organizationService.updateOrganization({ name }).subscribe({
      next: org => {
        this.organization = org;
        this.orgForm.markAsPristine();
        this.updatingOrg = false;
        this.snackBar.open('Organization updated successfully', 'Close', { duration: 3000 });
      },
      error: () => {
        this.updatingOrg = false;
        this.snackBar.open('Failed to update organization', 'Close', { duration: 3000 });
      },
    });
  }

  openInviteDialog(): void {
    const dialogRef = this.dialog.open(HopInviteDialogComponent, { width: '400px' });
    dialogRef.afterClosed().subscribe(result => { if (result) this.sendInvitation(result); });
  }

  sendInvitation(data: { email: string; role: 'admin' | 'member' }): void {
    this.organizationService.createInvitation(data).subscribe({
      next: invitation => {
        this.loadInvitations();
        const inviteUrl = `${window.location.origin}/invite/${invitation.token}`;
        this.dialog.open(HopInviteSuccessDialogComponent, {
          data: { email: invitation.email, role: invitation.role, orgName: invitation.organization_name, inviteUrl },
        });
      },
      error: error => {
        this.snackBar.open(error.error?.detail || 'Failed to send invitation', 'Close', { duration: 3000 });
      },
    });
  }

  toggleRole(member: OrganizationMember): void {
    const newRole = member.role === 'admin' ? 'member' : 'admin';
    this.organizationService.updateMemberRole(member.id, newRole).subscribe({
      next: updated => {
        member.role = updated.role;
        this.snackBar.open('Member role updated', 'Close', { duration: 3000 });
      },
      error: () => this.snackBar.open('Failed to update member role', 'Close', { duration: 3000 }),
    });
  }

  removeMember(member: OrganizationMember): void {
    const dialogRef = this.dialog.open(HopConfirmDialogComponent, {
      data: { title: 'Remove Member', message: `Are you sure you want to remove ${member.user_email} from the organization?` },
    });
    dialogRef.afterClosed().subscribe(confirmed => {
      if (confirmed) {
        this.organizationService.removeMember(member.id).subscribe({
          next: () => { this.loadMembers(); this.snackBar.open('Member removed successfully', 'Close', { duration: 3000 }); },
          error: () => this.snackBar.open('Failed to remove member', 'Close', { duration: 3000 }),
        });
      }
    });
  }

  cancelInvitation(invitation: OrganizationInvitation): void {
    this.organizationService.cancelInvitation(invitation.id).subscribe({
      next: () => { this.loadInvitations(); this.snackBar.open('Invitation cancelled', 'Close', { duration: 3000 }); },
      error: () => this.snackBar.open('Failed to cancel invitation', 'Close', { duration: 3000 }),
    });
  }

  copyInvitationLink(invitation: OrganizationInvitation): void {
    const link = `${window.location.origin}/invite/${invitation.token}`;
    this.copyToClipboard(link).then(() => {
      this.snackBar.open('Invitation link copied to clipboard', 'Close', { duration: 3000 });
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

  isCurrentUser(member: OrganizationMember): boolean {
    return member.user_email === this.accountService.getCurrentEmail();
  }

  canChangeRole(member: OrganizationMember): boolean {
    if (this.isCurrentUser(member)) return false;
    if (member.role === 'admin') return this.members.filter(m => m.role === 'admin').length > 1;
    return true;
  }

  canRemoveMember(member: OrganizationMember): boolean {
    if (this.isCurrentUser(member)) return false;
    if (member.role === 'admin') return this.members.filter(m => m.role === 'admin').length > 1;
    return true;
  }
}
