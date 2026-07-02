import { Component, OnInit, AfterViewInit, inject, NgZone, ElementRef, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, FormGroup, Validators, ReactiveFormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatListModule } from '@angular/material/list';
import { MatDividerModule } from '@angular/material/divider';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { HopAuthService, UserOrganizationInfo } from './hop-auth.service';
import { HopOrganizationService } from '../shared/hop-organization.service';
import { HOP_API_URL } from '../tokens/hop-api-url.token';

@Component({
  selector: 'hop-login',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatListModule,
    MatDividerModule,
    RouterLink,
  ],
  template: `
    <div class="login-container">
      <!-- Organization Selection Step -->
      <mat-card class="login-card" *ngIf="showOrgSelection">
        <mat-card-header>
          <mat-card-title>Select Organization</mat-card-title>
        </mat-card-header>
        <mat-card-content>
          <p class="org-select-hint">You belong to multiple organizations. Select one to continue.</p>
          <mat-nav-list>
            <a mat-list-item *ngFor="let org of userOrganizations"
               (click)="selectOrganization(org)" class="org-list-item">
              <mat-icon matListItemIcon>business</mat-icon>
              <span matListItemTitle>{{ org.name }}</span>
              <span matListItemLine class="org-role">{{ org.role }}</span>
            </a>
          </mat-nav-list>
          <div *ngIf="loading" class="loading-row">
            <mat-spinner diameter="20"></mat-spinner>
            <span>Switching...</span>
          </div>
          <div class="error-message" *ngIf="errorMessage">{{ errorMessage }}</div>
        </mat-card-content>
      </mat-card>

      <!-- Login / Register Form -->
      <mat-card class="login-card" *ngIf="!showOrgSelection">
        <mat-card-header>
          <mat-card-title>{{ isRegisterMode ? 'Create Account' : 'Login' }}</mat-card-title>
        </mat-card-header>
        <mat-card-content>
          <!-- SSO Buttons -->
          <div class="sso-buttons" *ngIf="googleEnabled || microsoftEnabled">
            <div #googleBtnContainer *ngIf="googleEnabled" class="google-btn-wrapper"></div>
            <button mat-stroked-button class="sso-btn" type="button"
                    *ngIf="microsoftEnabled" (click)="loginWithMicrosoft()">
              <mat-icon>login</mat-icon>
              Continue with Microsoft
            </button>
            <div class="sso-divider">
              <mat-divider></mat-divider>
              <span class="sso-divider-text">or sign in with email</span>
              <mat-divider></mat-divider>
            </div>
          </div>

          <form [formGroup]="loginForm" (ngSubmit)="onSubmit()">
            <mat-form-field appearance="outline" class="full-width"
                            *ngIf="isRegisterMode && !singleOrgMode">
              <mat-label>Organization Name</mat-label>
              <input matInput type="text" formControlName="organizationName" required>
              <mat-hint>Enter your company or team name</mat-hint>
              <mat-error *ngIf="loginForm.get('organizationName')?.hasError('required')">
                Organization name is required
              </mat-error>
            </mat-form-field>

            <mat-form-field appearance="outline" class="full-width">
              <mat-label>Email</mat-label>
              <input matInput type="email" formControlName="email" required>
              <mat-error *ngIf="loginForm.get('email')?.hasError('required')">Email is required</mat-error>
              <mat-error *ngIf="loginForm.get('email')?.hasError('email')">Please enter a valid email</mat-error>
            </mat-form-field>

            <mat-form-field appearance="outline" class="full-width">
              <mat-label>Password</mat-label>
              <input matInput [type]="hidePassword ? 'password' : 'text'"
                     formControlName="password" required>
              <button mat-icon-button matSuffix (click)="hidePassword = !hidePassword" type="button">
                <mat-icon>{{ hidePassword ? 'visibility_off' : 'visibility' }}</mat-icon>
              </button>
              <mat-error *ngIf="loginForm.get('password')?.hasError('required')">Password is required</mat-error>
            </mat-form-field>

            <div class="error-message" *ngIf="errorMessage">{{ errorMessage }}</div>

            <div class="button-row">
              <button mat-raised-button color="primary" type="submit"
                      [disabled]="!loginForm.valid || loading">
                <mat-spinner diameter="20" *ngIf="loading"></mat-spinner>
                <span *ngIf="!loading">{{ isRegisterMode ? 'Create Account' : 'Login' }}</span>
              </button>
              <button mat-button type="button" (click)="switchToRegister()" *ngIf="!ssoOnly">
                {{ isRegisterMode ? 'Already have an account?' : 'Create Account' }}
              </button>
            </div>

            <div class="forgot-password-row" *ngIf="!isRegisterMode">
              <a routerLink="/forgot-password" class="forgot-password-link">Forgot Password?</a>
            </div>
          </form>
        </mat-card-content>
      </mat-card>
    </div>
  `,
  styles: [`
    .login-container {
      display: flex;
      justify-content: center;
      align-items: center;
      height: 100vh;
      background: var(--hop-gradient);
    }
    .login-card { width: 100%; max-width: 400px; padding: 20px; }
    .full-width { width: 100%; margin-bottom: 15px; }
    .button-row { display: flex; justify-content: space-between; margin-top: 20px; }
    .error-message { color: var(--color-error); margin-bottom: 15px; text-align: center; }
    mat-spinner { display: inline-block; margin-right: 10px; }
    .org-select-hint { color: var(--text-secondary); margin-bottom: 8px; }
    .org-list-item { cursor: pointer; }
    .org-role { text-transform: capitalize; color: var(--text-secondary); }
    .loading-row { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 16px; }
    .forgot-password-row { text-align: center; margin-top: 12px; }
    .forgot-password-link { color: var(--text-link); text-decoration: none; font-size: 14px; }
    .sso-buttons { margin-bottom: 16px; }
    .google-btn-wrapper { display: flex; justify-content: center; margin-bottom: 8px; }
    .sso-btn { width: 100%; margin-bottom: 8px; height: 42px; }
    .sso-divider { display: flex; align-items: center; gap: 12px; margin: 16px 0; }
    .sso-divider mat-divider { flex: 1; }
    .sso-divider-text { color: var(--text-tertiary); font-size: 13px; white-space: nowrap; }
  `],
})
export class HopLoginComponent implements OnInit, AfterViewInit {
  private fb = inject(FormBuilder);
  private route = inject(ActivatedRoute);
  private authService = inject(HopAuthService);
  private organizationService = inject(HopOrganizationService);
  private ngZone = inject(NgZone);
  private apiUrl = inject(HOP_API_URL);

  @ViewChild('googleBtnContainer') googleBtnContainer?: ElementRef;

  private returnUrl: string | undefined;
  private googleClientId: string | null = null;
  private googleScriptLoaded = false;

  hidePassword = true;
  loading = false;
  errorMessage = '';
  isRegisterMode = false;
  showOrgSelection = false;
  userOrganizations: UserOrganizationInfo[] = [];

  googleEnabled = false;
  microsoftEnabled = false;
  ssoOnly = false;
  singleOrgMode = false;

  loginForm: FormGroup = this.fb.group({
    organizationName: ['', []],
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(8)]],
  });

  ngOnInit(): void {
    this.returnUrl = this.route.snapshot.queryParams['returnUrl'];

    const ssoError = this.route.snapshot.queryParams['sso_error'];
    if (ssoError) {
      const messages: Record<string, string> = {
        token_exchange_failed: 'SSO sign-in failed. Please try again.',
        no_user_info: 'Could not retrieve your account information from the provider.',
        email_not_verified: 'Your email is not verified with the SSO provider.',
        session_failed: 'SSO session could not be established. Please try again.',
      };
      this.errorMessage = messages[ssoError] ?? 'SSO sign-in failed. Please try again.';
    }

    this.authService.getSSOProviders().subscribe({
      next: providers => {
        this.googleEnabled = providers.google;
        this.microsoftEnabled = providers.microsoft;
        this.ssoOnly = providers.sso_only ?? false;
        this.singleOrgMode = providers.single_org_mode ?? false;
        if (providers.google && providers.google_client_id) {
          this.googleClientId = providers.google_client_id;
          this.loadGoogleScript();
        }
      },
      error: () => {},
    });
  }

  ngAfterViewInit(): void {
    this.tryRenderGoogleButton();
  }

  private loadGoogleScript(): void {
    if (this.googleScriptLoaded || document.getElementById('google-gsi-script')) {
      this.googleScriptLoaded = true;
      this.tryRenderGoogleButton();
      return;
    }
    const script = document.createElement('script');
    script.id = 'google-gsi-script';
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.onload = () => {
      this.googleScriptLoaded = true;
      this.tryRenderGoogleButton();
    };
    document.head.appendChild(script);
  }

  private tryRenderGoogleButton(): void {
    if (!this.googleScriptLoaded || !this.googleClientId || !this.googleBtnContainer) return;
    const google = (window as any)['google'];
    if (!google?.accounts?.id) return;
    google.accounts.id.initialize({
      client_id: this.googleClientId,
      callback: (response: any) => this.handleGoogleCredential(response),
      auto_select: false,
    });
    google.accounts.id.renderButton(this.googleBtnContainer.nativeElement, {
      type: 'standard', theme: 'outline', size: 'large', width: 360, text: 'continue_with',
    });
  }

  private handleGoogleCredential(response: any): void {
    this.ngZone.run(() => {
      this.loading = true;
      this.errorMessage = '';
      this.authService.loginWithGoogleToken(response.credential).subscribe({
        next: () => {
          this.loading = false;
          this.authService.navigateToDashboard(this.returnUrl);
        },
        error: err => {
          this.errorMessage = err.error?.detail || 'Google sign-in failed. Please try again.';
          this.loading = false;
        },
      });
    });
  }

  loginWithMicrosoft(): void {
    const returnParam = encodeURIComponent(this.returnUrl || '/dashboard');
    window.location.href = `${this.apiUrl}/auth/sso/microsoft?return_url=${returnParam}`;
  }

  onSubmit(): void {
    if (!this.loginForm.valid) return;
    this.loading = true;
    this.errorMessage = '';
    const { organizationName, email, password } = this.loginForm.value;

    if (this.isRegisterMode) {
      this.authService.register(email, password, organizationName).subscribe({
        next: () => {
          this.isRegisterMode = false;
          this.errorMessage = 'Account created! Please login.';
          this.loading = false;
        },
        error: error => {
          this.errorMessage = error.error?.detail || 'Registration failed';
          this.loading = false;
        },
      });
    } else {
      this.authService.login(email, password).subscribe({
        next: response => {
          this.loading = false;
          const orgs = response.organizations || [];
          if (orgs.length > 1) {
            this.userOrganizations = orgs;
            this.showOrgSelection = true;
          } else {
            this.authService.navigateToDashboard(this.returnUrl);
          }
        },
        error: error => {
          this.errorMessage = error.error?.detail || 'Login failed';
          this.loading = false;
        },
      });
    }
  }

  selectOrganization(org: UserOrganizationInfo): void {
    this.loading = true;
    this.errorMessage = '';
    this.organizationService.switchOrganization(org.id).subscribe({
      next: response => {
        this.authService.updateTokens(response);
        this.loading = false;
        this.authService.navigateToDashboard(this.returnUrl);
      },
      error: error => {
        this.errorMessage = error.error?.detail || 'Failed to switch organization';
        this.loading = false;
      },
    });
  }

  switchToRegister(): void {
    this.isRegisterMode = !this.isRegisterMode;
    this.errorMessage = '';
    const orgNameControl = this.loginForm.get('organizationName');
    if (this.isRegisterMode) {
      orgNameControl?.setValidators([Validators.required]);
    } else {
      orgNameControl?.clearValidators();
    }
    orgNameControl?.updateValueAndValidity();
  }
}
