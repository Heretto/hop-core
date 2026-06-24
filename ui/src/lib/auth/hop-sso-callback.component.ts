import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { HopAuthService } from './hop-auth.service';

@Component({
  selector: 'hop-sso-callback',
  standalone: true,
  imports: [CommonModule, MatProgressSpinnerModule],
  template: `
    <div class="sso-callback-container">
      <mat-spinner diameter="40"></mat-spinner>
      <p>Completing sign in...</p>
    </div>
  `,
  styles: [`
    .sso-callback-container {
      display: flex; flex-direction: column; align-items: center;
      justify-content: center; height: 100vh; gap: 16px;
      color: rgba(0,0,0,0.54);
    }
  `],
})
export class HopSSOCallbackComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private authService = inject(HopAuthService);

  ngOnInit(): void {
    const returnUrl = this.route.snapshot.queryParams['return_url'];
    this.authService.refreshToken().subscribe({
      next: () => this.authService.navigateToDashboard(returnUrl),
      error: () => this.authService.navigateToDashboard('/login?sso_error=session_failed'),
    });
  }
}
