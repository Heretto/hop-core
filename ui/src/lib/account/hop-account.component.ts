import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatDividerModule } from '@angular/material/divider';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { HopAccountService, AccountInfo } from '../shared/hop-account.service';
import { HopAuthService } from '../auth/hop-auth.service';

@Component({
  selector: 'hop-account',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, MatCardModule, MatFormFieldModule, MatInputModule,
    MatButtonModule, MatIconModule, MatSnackBarModule, MatDividerModule, MatProgressSpinnerModule,
  ],
  template: `
    <div class="account-container">
      <h1>Account Settings</h1>

      <div *ngIf="loading" class="loading-container">
        <mat-spinner></mat-spinner>
        <p>Loading account information...</p>
      </div>

      <div *ngIf="!loading && accountInfo" class="account-content">
        <!-- Account Information Card -->
        <mat-card class="info-card">
          <mat-card-header>
            <mat-card-title>
              <mat-icon>account_circle</mat-icon>
              Account Information
            </mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <div class="info-grid">
              <div class="info-item">
                <label>User ID</label>
                <span class="value">{{ accountInfo.id }}</span>
              </div>
              <div class="info-item">
                <label>Current Email</label>
                <span class="value">{{ accountInfo.email }}</span>
              </div>
              <div class="info-item">
                <label>Account Status</label>
                <span class="value status" [class.active]="accountInfo.is_active">
                  {{ accountInfo.is_active ? 'Active' : 'Inactive' }}
                </span>
              </div>
              <div class="info-item">
                <label>Account Type</label>
                <span class="value">{{ accountInfo.is_superuser ? 'System Administrator' : 'Standard User' }}</span>
              </div>
              <div class="info-item" *ngIf="accountInfo.organization_name">
                <label>Organization</label>
                <span class="value">{{ accountInfo.organization_name }}</span>
              </div>
              <div class="info-item" *ngIf="accountInfo.organization_role">
                <label>Organization Role</label>
                <span class="value" [class.admin-role]="accountInfo.organization_role === 'admin'">
                  <mat-icon *ngIf="accountInfo.organization_role === 'admin'" inline>admin_panel_settings</mat-icon>
                  {{ accountInfo.organization_role === 'admin' ? 'Administrator' : 'Member' }}
                </span>
              </div>
              <div class="info-item">
                <label>Member Since</label>
                <span class="value">{{ formatDate(accountInfo.created_at) }}</span>
              </div>
            </div>
          </mat-card-content>
        </mat-card>

        <!-- Update Email Card -->
        <mat-card class="update-card">
          <mat-card-header>
            <mat-card-title>
              <mat-icon>email</mat-icon>
              Update Email Address
            </mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <form [formGroup]="emailForm" (ngSubmit)="updateEmail()">
              <mat-form-field appearance="outline" class="full-width">
                <mat-label>New Email Address</mat-label>
                <input matInput type="email" formControlName="email" placeholder="Enter new email address">
                <mat-icon matSuffix>email</mat-icon>
                <mat-error *ngIf="emailForm.get('email')?.hasError('required')">Email is required</mat-error>
                <mat-error *ngIf="emailForm.get('email')?.hasError('email')">Please enter a valid email address</mat-error>
              </mat-form-field>
              <div class="form-actions">
                <button mat-raised-button color="primary" type="submit" [disabled]="emailForm.invalid || updatingEmail">
                  <mat-icon *ngIf="!updatingEmail">save</mat-icon>
                  <mat-spinner *ngIf="updatingEmail" diameter="18"></mat-spinner>
                  {{ updatingEmail ? 'Updating...' : 'Update Email' }}
                </button>
              </div>
            </form>
          </mat-card-content>
        </mat-card>

        <!-- Change Password Card -->
        <mat-card class="update-card">
          <mat-card-header>
            <mat-card-title>
              <mat-icon>lock</mat-icon>
              Change Password
            </mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <form [formGroup]="passwordForm" (ngSubmit)="updatePassword()">
              <mat-form-field appearance="outline" class="full-width">
                <mat-label>Current Password</mat-label>
                <input matInput [type]="hideCurrentPassword ? 'password' : 'text'" formControlName="currentPassword">
                <button mat-icon-button matSuffix type="button" (click)="hideCurrentPassword = !hideCurrentPassword">
                  <mat-icon>{{ hideCurrentPassword ? 'visibility_off' : 'visibility' }}</mat-icon>
                </button>
                <mat-error *ngIf="passwordForm.get('currentPassword')?.hasError('required')">Current password is required</mat-error>
              </mat-form-field>
              <mat-form-field appearance="outline" class="full-width">
                <mat-label>New Password</mat-label>
                <input matInput [type]="hideNewPassword ? 'password' : 'text'" formControlName="newPassword">
                <button mat-icon-button matSuffix type="button" (click)="hideNewPassword = !hideNewPassword">
                  <mat-icon>{{ hideNewPassword ? 'visibility_off' : 'visibility' }}</mat-icon>
                </button>
                <mat-error *ngIf="passwordForm.get('newPassword')?.hasError('required')">New password is required</mat-error>
                <mat-error *ngIf="passwordForm.get('newPassword')?.hasError('minlength')">Password must be at least 8 characters</mat-error>
                <mat-hint>Minimum 8 characters</mat-hint>
              </mat-form-field>
              <mat-form-field appearance="outline" class="full-width">
                <mat-label>Confirm New Password</mat-label>
                <input matInput [type]="hideConfirmPassword ? 'password' : 'text'" formControlName="confirmPassword">
                <button mat-icon-button matSuffix type="button" (click)="hideConfirmPassword = !hideConfirmPassword">
                  <mat-icon>{{ hideConfirmPassword ? 'visibility_off' : 'visibility' }}</mat-icon>
                </button>
                <mat-error *ngIf="passwordForm.get('confirmPassword')?.hasError('required')">Please confirm your new password</mat-error>
                <mat-error *ngIf="passwordForm.hasError('passwordMismatch')">Passwords do not match</mat-error>
              </mat-form-field>
              <div class="form-actions">
                <button mat-raised-button color="primary" type="submit" [disabled]="passwordForm.invalid || updatingPassword">
                  <mat-icon *ngIf="!updatingPassword">lock</mat-icon>
                  <mat-spinner *ngIf="updatingPassword" diameter="18"></mat-spinner>
                  {{ updatingPassword ? 'Updating...' : 'Change Password' }}
                </button>
              </div>
            </form>
          </mat-card-content>
        </mat-card>

        <!-- Danger Zone -->
        <mat-card class="danger-card">
          <mat-card-header>
            <mat-card-title class="danger-title">
              <mat-icon>warning</mat-icon>
              Danger Zone
            </mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <div class="danger-content">
              <div class="danger-text">
                <h3>Delete Account</h3>
                <p>Once you delete your account, there is no going back. Please be certain.</p>
              </div>
              <button mat-stroked-button color="warn" (click)="confirmDeleteAccount()">
                <mat-icon>delete_forever</mat-icon>
                Delete Account
              </button>
            </div>
          </mat-card-content>
        </mat-card>
      </div>
    </div>
  `,
  styles: [`
    .account-container { max-width: 800px; margin: 0 auto; padding: 20px; }
    h1 { margin-bottom: 30px; color: #333; }
    .loading-container { display: flex; flex-direction: column; align-items: center; padding: 60px; }
    .loading-container p { margin-top: 20px; color: #666; }
    .account-content { display: flex; flex-direction: column; gap: 24px; }
    .info-card { background: var(--hop-gradient, linear-gradient(135deg, #667eea 0%, #764ba2 100%)); color: white; }
    .info-card mat-card-title { display: flex; align-items: center; gap: 10px; color: white; }
    .info-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-top: 20px; }
    .info-item { display: flex; flex-direction: column; gap: 5px; }
    .info-item label { font-size: 12px; opacity: 0.8; text-transform: uppercase; letter-spacing: 0.5px; }
    .info-item .value { font-size: 16px; font-weight: 500; }
    .info-item .status.active { color: #69f0ae; }
    .info-item .admin-role { color: #ffd54f; display: flex; align-items: center; gap: 4px; font-weight: 600; }
    .info-item .admin-role mat-icon { font-size: 18px; width: 18px; height: 18px; }
    .update-card mat-card-title { display: flex; align-items: center; gap: 10px; }
    .full-width { width: 100%; }
    .form-actions { display: flex; justify-content: flex-end; margin-top: 20px; }
    .form-actions button { display: flex; align-items: center; gap: 8px; }
    .danger-card { border: 2px solid #ff5252; background-color: #fff5f5; }
    .danger-title { color: #ff5252; display: flex; align-items: center; gap: 10px; }
    .danger-content { display: flex; justify-content: space-between; align-items: center; margin-top: 10px; }
    .danger-text h3 { margin: 0 0 8px 0; color: #d32f2f; }
    .danger-text p { margin: 0; color: #666; }
    @media (max-width: 600px) {
      .info-grid { grid-template-columns: 1fr; }
      .danger-content { flex-direction: column; align-items: flex-start; gap: 20px; }
    }
  `],
})
export class HopAccountComponent implements OnInit {
  private fb = inject(FormBuilder);
  private accountService = inject(HopAccountService);
  private authService = inject(HopAuthService);
  private snackBar = inject(MatSnackBar);

  loading = true;
  accountInfo: AccountInfo | null = null;

  emailForm: FormGroup;
  passwordForm: FormGroup;

  updatingEmail = false;
  updatingPassword = false;

  hideCurrentPassword = true;
  hideNewPassword = true;
  hideConfirmPassword = true;

  constructor() {
    this.emailForm = this.fb.group({
      email: ['', [Validators.required, Validators.email]],
    });
    this.passwordForm = this.fb.group({
      currentPassword: ['', Validators.required],
      newPassword: ['', [Validators.required, Validators.minLength(8)]],
      confirmPassword: ['', Validators.required],
    }, { validators: this.passwordMatchValidator });
  }

  ngOnInit(): void {
    this.loadAccountInfo();
  }

  loadAccountInfo(): void {
    this.loading = true;
    this.accountService.getAccountInfo().subscribe({
      next: info => {
        this.accountInfo = info;
        this.emailForm.patchValue({ email: info.email });
        this.loading = false;
      },
      error: () => {
        this.snackBar.open('Failed to load account information', 'Close', { duration: 3000 });
        this.loading = false;
      },
    });
  }

  updateEmail(): void {
    if (this.emailForm.invalid || !this.accountInfo) return;
    const newEmail = this.emailForm.get('email')?.value;
    if (newEmail === this.accountInfo.email) {
      this.snackBar.open('Email is already set to this value', 'Close', { duration: 3000 });
      return;
    }
    this.updatingEmail = true;
    this.accountService.updateAccount({ email: newEmail }).subscribe({
      next: () => {
        this.snackBar.open('Email updated successfully', 'Close', { duration: 3000 });
        this.updatingEmail = false;
        this.loadAccountInfo();
      },
      error: error => {
        this.snackBar.open(error.error?.detail || 'Failed to update email', 'Close', { duration: 5000 });
        this.updatingEmail = false;
      },
    });
  }

  updatePassword(): void {
    if (this.passwordForm.invalid) return;
    const currentPassword = this.passwordForm.get('currentPassword')?.value;
    const newPassword = this.passwordForm.get('newPassword')?.value;
    this.updatingPassword = true;
    this.accountService.updateAccount({ current_password: currentPassword, new_password: newPassword }).subscribe({
      next: () => {
        this.snackBar.open('Password changed successfully', 'Close', { duration: 3000 });
        this.updatingPassword = false;
        this.passwordForm.reset();
      },
      error: error => {
        this.snackBar.open(error.error?.detail || 'Failed to update password', 'Close', { duration: 5000 });
        this.updatingPassword = false;
      },
    });
  }

  confirmDeleteAccount(): void {
    if (confirm('Are you sure you want to delete your account? This action cannot be undone.')) {
      const doubleConfirm = prompt('Type "DELETE" to confirm account deletion:');
      if (doubleConfirm === 'DELETE') {
        this.deleteAccount();
      } else {
        this.snackBar.open('Account deletion cancelled', 'Close', { duration: 3000 });
      }
    }
  }

  private deleteAccount(): void {
    this.accountService.deleteAccount(true).subscribe({
      next: () => {
        this.snackBar.open('Account deleted successfully', 'Close', { duration: 3000 });
        this.authService.logout();
      },
      error: () => {
        this.snackBar.open('Failed to delete account', 'Close', { duration: 3000 });
      },
    });
  }

  private passwordMatchValidator(group: FormGroup): { [key: string]: boolean } | null {
    const newPassword = group.get('newPassword')?.value;
    const confirmPassword = group.get('confirmPassword')?.value;
    if (newPassword && confirmPassword && newPassword !== confirmPassword) {
      return { passwordMismatch: true };
    }
    return null;
  }

  formatDate(dateStr: string): string {
    return new Date(dateStr).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
  }
}
