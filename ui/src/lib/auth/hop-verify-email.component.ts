import { Component, OnInit, inject, ChangeDetectionStrategy, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { HopAuthService } from './hop-auth.service';

/** Landing page for the emailed link: confirms the address as soon as it opens. */
@Component({
  changeDetection: ChangeDetectionStrategy.Eager,
  selector: 'hop-verify-email',
  standalone: true,
  imports: [CommonModule, RouterLink, MatCardModule, MatIconModule, MatProgressSpinnerModule],
  template: `
    <div class="verify-container">
      <mat-card class="verify-card">
        <mat-card-header><mat-card-title>Verify Email</mat-card-title></mat-card-header>
        <mat-card-content>
          <div *ngIf="loading" class="status-row">
            <mat-spinner diameter="24"></mat-spinner>
            <span>Verifying your email address…</span>
          </div>
          <div *ngIf="successMessage" class="success-message">
            <mat-icon>verified</mat-icon>
            <p>{{ successMessage }}</p>
          </div>
          <div *ngIf="errorMessage" class="error-message">
            <p>{{ errorMessage }}</p>
            <p class="hint">Sign in with your email and password to get a new link.</p>
          </div>
          <div *ngIf="!loading" class="back-link"><a routerLink="/login">Go to Login</a></div>
        </mat-card-content>
      </mat-card>
    </div>
  `,
  styles: [`
    .verify-container {
      display: flex; justify-content: center; align-items: center;
      height: 100vh;
      background: var(--hop-gradient);
    }
    .verify-card { width: 100%; max-width: 400px; padding: 20px; }
    .status-row { display: flex; align-items: center; justify-content: center; gap: 12px; padding: 16px 0; color: var(--text-secondary); }
    .success-message, .error-message { text-align: center; }
    .success-message p { color: var(--color-success-text); }
    .success-message mat-icon { color: var(--color-success); }
    .error-message p { color: var(--color-error-text); }
    .error-message p.hint { color: var(--text-secondary); font-size: 14px; }
    .back-link { text-align: center; margin-top: 16px; }
    .back-link a { color: var(--text-link); text-decoration: none; font-size: 14px; }
  `],
})
export class HopVerifyEmailComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private authService = inject(HopAuthService);
  private cdr = inject(ChangeDetectorRef);

  loading = false;
  successMessage = '';
  errorMessage = '';

  ngOnInit(): void {
    const token = this.route.snapshot.queryParams['token'];
    if (!token) {
      this.errorMessage = 'This verification link is incomplete.';
      return;
    }
    this.loading = true;
    this.authService.verifyEmail(token).subscribe({
      next: res => { this.successMessage = res.message; this.loading = false; this.cdr.markForCheck(); },
      error: err => {
        this.errorMessage = err.error?.detail || 'This verification link is not valid.';
        this.loading = false;
        this.cdr.markForCheck();
      },
    });
  }
}
