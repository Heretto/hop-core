import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, Validators, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { HopAuthService } from './hop-auth.service';

@Component({
  selector: 'hop-reset-password',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, RouterLink,
    MatCardModule, MatFormFieldModule, MatInputModule, MatButtonModule, MatIconModule, MatProgressSpinnerModule,
  ],
  template: `
    <div class="reset-container">
      <mat-card class="reset-card">
        <mat-card-header><mat-card-title>Set New Password</mat-card-title></mat-card-header>
        <mat-card-content>
          <div *ngIf="!token" class="error-message">
            Invalid password reset link. Please request a new one.
          </div>
          <div *ngIf="successMessage" class="success-message">
            {{ successMessage }}
            <div class="back-link" style="margin-top: 16px;"><a routerLink="/login">Go to Login</a></div>
          </div>
          <form *ngIf="token && !successMessage" [formGroup]="form" (ngSubmit)="onSubmit()">
            <mat-form-field appearance="outline" class="full-width">
              <mat-label>New Password</mat-label>
              <input matInput [type]="hidePassword ? 'password' : 'text'" formControlName="newPassword" required>
              <button mat-icon-button matSuffix (click)="hidePassword = !hidePassword" type="button">
                <mat-icon>{{ hidePassword ? 'visibility_off' : 'visibility' }}</mat-icon>
              </button>
              <mat-error *ngIf="form.get('newPassword')?.hasError('required')">Password is required</mat-error>
              <mat-error *ngIf="form.get('newPassword')?.hasError('minlength')">Password must be at least 8 characters</mat-error>
            </mat-form-field>
            <mat-form-field appearance="outline" class="full-width">
              <mat-label>Confirm Password</mat-label>
              <input matInput [type]="hidePassword ? 'password' : 'text'" formControlName="confirmPassword" required>
              <mat-error *ngIf="form.get('confirmPassword')?.hasError('required')">Please confirm your password</mat-error>
            </mat-form-field>
            <div class="error-message" *ngIf="errorMessage">{{ errorMessage }}</div>
            <div class="button-row">
              <button mat-raised-button color="primary" type="submit" [disabled]="!form.valid || loading">
                <mat-spinner diameter="20" *ngIf="loading"></mat-spinner>
                <span *ngIf="!loading">Reset Password</span>
              </button>
            </div>
          </form>
          <div *ngIf="!successMessage" class="back-link"><a routerLink="/login">Back to Login</a></div>
        </mat-card-content>
      </mat-card>
    </div>
  `,
  styles: [`
    .reset-container {
      display: flex; justify-content: center; align-items: center;
      height: 100vh;
      background: var(--hop-gradient);
    }
    .reset-card { width: 100%; max-width: 400px; padding: 20px; }
    .full-width { width: 100%; }
    .button-row { display: flex; justify-content: center; margin-top: 20px; }
    .error-message { color: var(--color-error); margin-bottom: 15px; text-align: center; }
    .success-message { color: var(--color-success); text-align: center; }
    .back-link { text-align: center; margin-top: 16px; }
    .back-link a { color: var(--text-link); text-decoration: none; font-size: 14px; }
    mat-spinner { display: inline-block; margin-right: 10px; }
  `],
})
export class HopResetPasswordComponent implements OnInit {
  private fb = inject(FormBuilder);
  private route = inject(ActivatedRoute);
  private authService = inject(HopAuthService);

  token: string | null = null;
  hidePassword = true;
  loading = false;
  errorMessage = '';
  successMessage = '';

  form = this.fb.group({
    newPassword: ['', [Validators.required, Validators.minLength(8)]],
    confirmPassword: ['', [Validators.required]],
  });

  ngOnInit(): void {
    this.token = this.route.snapshot.queryParams['token'] || null;
  }

  onSubmit(): void {
    if (!this.form.valid || !this.token) return;
    const { newPassword, confirmPassword } = this.form.value;
    if (newPassword !== confirmPassword) {
      this.errorMessage = 'Passwords do not match.';
      return;
    }
    this.loading = true;
    this.errorMessage = '';
    this.authService.resetPassword(this.token, newPassword!).subscribe({
      next: res => { this.successMessage = res.message; this.loading = false; },
      error: err => {
        this.errorMessage = err.error?.detail || 'Password reset failed. The link may have expired.';
        this.loading = false;
      },
    });
  }
}
