import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, Validators, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { HopAuthService } from './hop-auth.service';

@Component({
  selector: 'hop-forgot-password',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, RouterLink,
    MatCardModule, MatFormFieldModule, MatInputModule, MatButtonModule, MatProgressSpinnerModule,
  ],
  template: `
    <div class="forgot-container">
      <mat-card class="forgot-card">
        <mat-card-header><mat-card-title>Reset Password</mat-card-title></mat-card-header>
        <mat-card-content>
          <div *ngIf="successMessage" class="success-message">{{ successMessage }}</div>

          <form *ngIf="!successMessage" [formGroup]="form" (ngSubmit)="onSubmit()">
            <p class="hint">Enter your email address and we'll send you a link to reset your password.</p>
            <mat-form-field appearance="outline" class="full-width">
              <mat-label>Email</mat-label>
              <input matInput type="email" formControlName="email" required>
              <mat-error *ngIf="form.get('email')?.hasError('required')">Email is required</mat-error>
              <mat-error *ngIf="form.get('email')?.hasError('email')">Please enter a valid email</mat-error>
            </mat-form-field>
            <div class="error-message" *ngIf="errorMessage">{{ errorMessage }}</div>
            <div class="button-row">
              <button mat-raised-button color="primary" type="submit" [disabled]="!form.valid || loading">
                <mat-spinner diameter="20" *ngIf="loading"></mat-spinner>
                <span *ngIf="!loading">Send Reset Link</span>
              </button>
            </div>
          </form>

          <div class="back-link"><a routerLink="/login">Back to Login</a></div>
        </mat-card-content>
      </mat-card>
    </div>
  `,
  styles: [`
    .forgot-container {
      display: flex; justify-content: center; align-items: center;
      height: 100vh;
      background: var(--hop-gradient);
    }
    .forgot-card { width: 100%; max-width: 400px; padding: 20px; }
    .full-width { width: 100%; margin-bottom: 15px; }
    .hint { color: var(--text-secondary); margin-bottom: 16px; }
    .button-row { display: flex; justify-content: center; margin-top: 20px; }
    .error-message { color: var(--color-error); margin-bottom: 15px; text-align: center; }
    .success-message { color: var(--color-success); margin-bottom: 15px; text-align: center; }
    .back-link { text-align: center; margin-top: 16px; }
    .back-link a { color: var(--text-link); text-decoration: none; font-size: 14px; }
    mat-spinner { display: inline-block; margin-right: 10px; }
  `],
})
export class HopForgotPasswordComponent {
  private fb = inject(FormBuilder);
  private authService = inject(HopAuthService);

  form = this.fb.group({ email: ['', [Validators.required, Validators.email]] });
  loading = false;
  errorMessage = '';
  successMessage = '';

  onSubmit(): void {
    if (!this.form.valid) return;
    this.loading = true;
    this.errorMessage = '';
    this.authService.forgotPassword(this.form.value.email!).subscribe({
      next: res => { this.successMessage = res.message; this.loading = false; },
      error: err => { this.errorMessage = err.error?.detail || 'An error occurred. Please try again.'; this.loading = false; },
    });
  }
}
