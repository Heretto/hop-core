import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, FormGroup, Validators, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { HttpClient } from '@angular/common/http';
import { catchError, of } from 'rxjs';
import { HOP_API_URL } from '../tokens/hop-api-url.token';

export interface InvitationInfo {
  email: string;
  organization_name: string;
  role: string;
  invited_by_email: string;
  expires_at: string;
  is_existing_user: boolean;
}

@Component({
  selector: 'hop-accept-invitation',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, RouterLink, MatCardModule, MatFormFieldModule,
    MatInputModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule, MatSnackBarModule,
  ],
  template: `
    <div class="invitation-container">
      <mat-card class="invitation-card">
        <!-- Loading State -->
        <div *ngIf="loading" class="loading-state">
          <mat-spinner></mat-spinner>
          <p>Loading invitation details...</p>
        </div>

        <!-- Error State -->
        <div *ngIf="error && !loading" class="error-state">
          <mat-icon color="warn">error_outline</mat-icon>
          <h2>Invalid Invitation</h2>
          <p>{{ error }}</p>
          <button mat-raised-button color="primary" routerLink="/login">Go to Login</button>
        </div>

        <!-- Invitation Info -->
        <div *ngIf="invitationInfo && !loading && !error">
          <mat-card-header>
            <mat-icon mat-card-avatar class="invitation-icon">mail_outline</mat-icon>
            <mat-card-title>Organization Invitation</mat-card-title>
            <mat-card-subtitle>You've been invited to join an organization</mat-card-subtitle>
          </mat-card-header>
          <mat-card-content>
            <div class="invitation-details">
              <div class="detail-item">
                <mat-icon>business</mat-icon>
                <div><label>Organization</label><span>{{ invitationInfo.organization_name }}</span></div>
              </div>
              <div class="detail-item">
                <mat-icon>email</mat-icon>
                <div><label>Email</label><span>{{ invitationInfo.email }}</span></div>
              </div>
              <div class="detail-item">
                <mat-icon>{{ invitationInfo.role === 'admin' ? 'admin_panel_settings' : 'person' }}</mat-icon>
                <div>
                  <label>Role</label>
                  <span>{{ invitationInfo.role === 'admin' ? 'Administrator' : 'Member' }}</span>
                </div>
              </div>
              <div class="detail-item">
                <mat-icon>person_add</mat-icon>
                <div><label>Invited by</label><span>{{ invitationInfo.invited_by_email }}</span></div>
              </div>
            </div>

            <!-- New User Form -->
            <form *ngIf="!invitationInfo.is_existing_user" [formGroup]="acceptForm" (ngSubmit)="acceptInvitation()" class="accept-form">
              <h3>Create Your Account</h3>
              <p class="form-subtitle">Set a password to complete your registration</p>
              <mat-form-field appearance="outline" class="full-width">
                <mat-label>Password</mat-label>
                <input matInput [type]="hidePassword ? 'password' : 'text'" formControlName="password" required>
                <button mat-icon-button matSuffix type="button" (click)="hidePassword = !hidePassword">
                  <mat-icon>{{ hidePassword ? 'visibility_off' : 'visibility' }}</mat-icon>
                </button>
                <mat-hint>At least 8 characters</mat-hint>
                <mat-error *ngIf="acceptForm.get('password')?.hasError('required')">Password is required</mat-error>
                <mat-error *ngIf="acceptForm.get('password')?.hasError('minlength')">Password must be at least 8 characters</mat-error>
              </mat-form-field>
              <mat-form-field appearance="outline" class="full-width">
                <mat-label>Confirm Password</mat-label>
                <input matInput [type]="hideConfirmPassword ? 'password' : 'text'" formControlName="confirm_password" required>
                <button mat-icon-button matSuffix type="button" (click)="hideConfirmPassword = !hideConfirmPassword">
                  <mat-icon>{{ hideConfirmPassword ? 'visibility_off' : 'visibility' }}</mat-icon>
                </button>
                <mat-error *ngIf="acceptForm.get('confirm_password')?.hasError('required')">Please confirm your password</mat-error>
                <mat-error *ngIf="acceptForm.hasError('passwordMismatch')">Passwords do not match</mat-error>
              </mat-form-field>
              <button mat-raised-button color="primary" type="submit" class="full-width"
                      [disabled]="!acceptForm.valid || accepting">
                <mat-spinner diameter="20" *ngIf="accepting"></mat-spinner>
                <span *ngIf="!accepting">Accept Invitation & Create Account</span>
              </button>
            </form>

            <!-- Existing User Form -->
            <form *ngIf="invitationInfo.is_existing_user" [formGroup]="existingUserForm" (ngSubmit)="acceptAsExistingUser()" class="accept-form">
              <h3>Confirm Your Identity</h3>
              <p class="form-subtitle">Enter your password to join the organization</p>
              <mat-form-field appearance="outline" class="full-width">
                <mat-label>Password</mat-label>
                <input matInput type="password" formControlName="password" required>
                <mat-error *ngIf="existingUserForm.get('password')?.hasError('required')">Password is required</mat-error>
              </mat-form-field>
              <button mat-raised-button color="primary" type="submit" class="full-width"
                      [disabled]="!existingUserForm.valid || accepting">
                <mat-spinner diameter="20" *ngIf="accepting"></mat-spinner>
                <span *ngIf="!accepting">Join Organization</span>
              </button>
            </form>
          </mat-card-content>
        </div>

        <!-- Success State -->
        <div *ngIf="success" class="success-state">
          <mat-icon color="primary">check_circle</mat-icon>
          <h2>Invitation Accepted!</h2>
          <p>{{ successMessage }}</p>
          <button mat-raised-button color="primary" routerLink="/login">Go to Login</button>
        </div>
      </mat-card>
    </div>
  `,
  styles: [`
    .invitation-container {
      min-height: 100vh; display: flex; align-items: center; justify-content: center;
      background: var(--hop-gradient); padding: 20px;
    }
    .invitation-card { max-width: 500px; width: 100%; }
    .invitation-icon { background: var(--hop-gradient); color: #fff; }
    .loading-state, .error-state, .success-state { text-align: center; padding: 40px; }
    .loading-state mat-spinner { margin: 0 auto 20px; }
    .error-state mat-icon, .success-state mat-icon { font-size: 64px; height: 64px; width: 64px; margin: 0 auto 20px; }
    .invitation-details { margin: 20px 0 30px; padding: 20px; background: var(--surface-sunken); border-radius: 8px; }
    .detail-item { display: flex; align-items: flex-start; gap: 15px; margin-bottom: 15px; }
    .detail-item:last-child { margin-bottom: 0; }
    .detail-item mat-icon { color: var(--text-secondary); margin-top: 2px; }
    .detail-item label { display: block; font-size: 12px; color: var(--text-secondary); margin-bottom: 2px; }
    .detail-item span { display: block; font-size: 14px; font-weight: 500; color: var(--text-primary); }
    .accept-form { margin-top: 30px; }
    .accept-form h3 { margin: 0 0 10px; color: var(--text-primary); }
    .form-subtitle { color: var(--text-secondary); margin-bottom: 20px; }
    .full-width { width: 100%; }
    button[type="submit"] { margin-top: 10px; height: 48px; }
    button mat-spinner { display: inline-block; margin-right: 8px; }
  `],
})
export class HopAcceptInvitationComponent implements OnInit {
  private fb = inject(FormBuilder);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private http = inject(HttpClient);
  private snackBar = inject(MatSnackBar);
  private apiUrl = inject(HOP_API_URL);

  token = '';
  invitationInfo: InvitationInfo | null = null;
  loading = true;
  error = '';
  accepting = false;
  success = false;
  successMessage = '';

  hidePassword = true;
  hideConfirmPassword = true;

  acceptForm = this.fb.group({
    password: ['', [Validators.required, Validators.minLength(8)]],
    confirm_password: ['', Validators.required],
  }, { validators: this.passwordMatchValidator });

  existingUserForm = this.fb.group({
    password: ['', Validators.required],
  });

  ngOnInit(): void {
    this.token = this.route.snapshot.paramMap.get('token') || '';
    if (!this.token) {
      this.error = 'No invitation token provided';
      this.loading = false;
      return;
    }
    this.loadInvitationInfo();
  }

  loadInvitationInfo(): void {
    this.http.get<InvitationInfo>(`${this.apiUrl}/invitations/info/${this.token}`).pipe(
      catchError(error => {
        this.error = error.error?.detail || 'Failed to load invitation details';
        this.loading = false;
        return of(null);
      })
    ).subscribe(info => {
      if (info) this.invitationInfo = info;
      this.loading = false;
    });
  }

  acceptInvitation(): void {
    if (this.acceptForm.invalid || this.accepting) return;
    this.accepting = true;
    const formValue = this.acceptForm.value;
    this.http.post(`${this.apiUrl}/invitations/accept/${this.token}`, {
      password: formValue.password,
      confirm_password: formValue.confirm_password,
    }).subscribe({
      next: (response: any) => {
        this.success = true;
        this.successMessage = response.message || 'Invitation accepted successfully!';
        this.accepting = false;
        setTimeout(() => this.router.navigate(['/login']), 3000);
      },
      error: error => {
        this.accepting = false;
        if (error.status === 409 && this.invitationInfo) {
          this.invitationInfo.is_existing_user = true;
          this.snackBar.open(
            'An account with this email already exists. Please enter your current password to join.',
            'Close', { duration: 5000 }
          );
        } else {
          this.snackBar.open(error.error?.detail || 'Failed to accept invitation', 'Close', { duration: 5000 });
        }
      },
    });
  }

  acceptAsExistingUser(): void {
    if (this.existingUserForm.invalid || this.accepting) return;
    this.accepting = true;
    const password = this.existingUserForm.value.password;
    this.http.post(`${this.apiUrl}/invitations/accept-existing/${this.token}`, { password }).subscribe({
      next: (response: any) => {
        this.success = true;
        this.successMessage = response.message || 'You have been added to the organization!';
        this.accepting = false;
        setTimeout(() => this.router.navigate(['/login']), 3000);
      },
      error: error => {
        this.accepting = false;
        this.snackBar.open(error.error?.detail || 'Failed to join organization', 'Close', { duration: 5000 });
      },
    });
  }

  private passwordMatchValidator(form: FormGroup): { [key: string]: boolean } | null {
    const password = form.get('password');
    const confirmPassword = form.get('confirm_password');
    if (password && confirmPassword && password.value !== confirmPassword.value) {
      return { passwordMismatch: true };
    }
    return null;
  }
}
