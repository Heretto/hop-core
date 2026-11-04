import { Component, OnInit, AfterViewInit, inject, NgZone, ElementRef, Input, ViewChild, ChangeDetectionStrategy, ChangeDetectorRef } from '@angular/core';
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
import { HOP_LOGO_SRC } from '../tokens/hop-logo-src.token';
import { HOP_LOGIN_CONFIG, HopLoginConfig } from '../tokens/hop-login-config.token';

@Component({
  changeDetection: ChangeDetectionStrategy.Eager,
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
    <div class="login-page" [style]="backgroundStyle">
      <!-- Organization Selection Step -->
      <mat-card class="login-card" *ngIf="showOrgSelection">
        <div class="card-brand" *ngIf="resolvedLogoSrc || resolvedAppName">
          <img *ngIf="resolvedLogoSrc" [src]="resolvedLogoSrc" class="brand-logo" alt="">
          <span *ngIf="resolvedAppName" class="brand-name">{{ resolvedAppName }}</span>
        </div>
        <h2 class="card-heading">Select organization</h2>
        <p class="card-subtitle">You belong to multiple organizations. Select one to continue.</p>
        <mat-nav-list class="org-list">
          <a mat-list-item *ngFor="let org of userOrganizations"
             (click)="selectOrganization(org)" class="org-list-item">
            <mat-icon matListItemIcon>business</mat-icon>
            <span matListItemTitle>{{ org.name }}</span>
            <span matListItemLine class="org-role">{{ org.role }}</span>
          </a>
        </mat-nav-list>
        <div *ngIf="loading" class="loading-row">
          <mat-spinner diameter="20"></mat-spinner>
          <span>Switching…</span>
        </div>
        <div class="error-message" *ngIf="errorMessage">{{ errorMessage }}</div>
      </mat-card>

      <!-- Login / Register Form -->
      <mat-card class="login-card" *ngIf="!showOrgSelection">
        <!-- Brand mark -->
        <div class="card-brand" *ngIf="resolvedLogoSrc || resolvedAppName">
          <img *ngIf="resolvedLogoSrc" [src]="resolvedLogoSrc" class="brand-logo" alt="">
          <span *ngIf="resolvedAppName" class="brand-name">{{ resolvedAppName }}</span>
        </div>

        <h2 class="card-heading">{{ isRegisterMode ? 'Create account' : 'Sign in' }}</h2>
        <p class="card-subtitle" *ngIf="resolvedSubtitle && !isRegisterMode">{{ resolvedSubtitle }}</p>

        <!-- SSO Buttons -->
        <div class="sso-buttons" *ngIf="googleEnabled || microsoftEnabled">
          <div #googleBtnContainer *ngIf="googleEnabled" class="google-btn-wrapper"></div>
          <button mat-stroked-button class="sso-btn" type="button"
                  *ngIf="microsoftEnabled" (click)="loginWithMicrosoft()">
            <mat-icon>login</mat-icon>
            Continue with Microsoft
          </button>
          <div class="sso-divider" *ngIf="!ssoOnly">
            <mat-divider></mat-divider>
            <span class="sso-divider-text">or sign in with email</span>
            <mat-divider></mat-divider>
          </div>
        </div>

        <!-- SSO_ONLY: the provider buttons are the only way in. -->
        <ng-container *ngIf="ssoOnly">
          <p class="sso-only-hint" *ngIf="googleEnabled || microsoftEnabled">
            Sign in with your organization account.
          </p>
          <p class="sso-only-hint" *ngIf="!googleEnabled && !microsoftEnabled">
            No sign-in method is configured. Contact your administrator.
          </p>
          <div class="error-message" *ngIf="errorMessage">{{ errorMessage }}</div>
        </ng-container>

        <!-- Held back until the providers load, so it doesn't flash under SSO_ONLY. -->
        <form [formGroup]="loginForm" (ngSubmit)="onSubmit()" *ngIf="providersLoaded && !ssoOnly">
          <mat-form-field appearance="outline" class="full-width"
                          *ngIf="isRegisterMode && !singleOrgMode">
            <mat-label>Organization name</mat-label>
            <input matInput type="text" formControlName="organizationName" required>
            <mat-hint>Enter your company or team name</mat-hint>
            <mat-error *ngIf="loginForm.get('organizationName')?.hasError('required')">
              Organization name is required
            </mat-error>
          </mat-form-field>

          <mat-form-field appearance="outline" class="full-width">
            <mat-label>Email</mat-label>
            <input matInput type="email" formControlName="email" required autocomplete="email">
            <mat-error *ngIf="loginForm.get('email')?.hasError('required')">Email is required</mat-error>
            <mat-error *ngIf="loginForm.get('email')?.hasError('email')">Enter a valid email address</mat-error>
          </mat-form-field>

          <mat-form-field appearance="outline" class="full-width">
            <mat-label>Password</mat-label>
            <input matInput [type]="hidePassword ? 'password' : 'text'"
                   formControlName="password" required
                   [autocomplete]="isRegisterMode ? 'new-password' : 'current-password'">
            <button mat-icon-button matSuffix (click)="hidePassword = !hidePassword" type="button"
                    [attr.aria-label]="hidePassword ? 'Show password' : 'Hide password'">
              <mat-icon>{{ hidePassword ? 'visibility_off' : 'visibility' }}</mat-icon>
            </button>
            <mat-error *ngIf="loginForm.get('password')?.hasError('required')">Password is required</mat-error>
          </mat-form-field>

          <div class="error-message" *ngIf="errorMessage">{{ errorMessage }}</div>

          <button mat-raised-button color="accent" type="submit" class="submit-btn"
                  [disabled]="!loginForm.valid || loading">
            <mat-spinner diameter="18" *ngIf="loading"></mat-spinner>
            <span *ngIf="!loading">{{ isRegisterMode ? 'Create account' : 'Log in' }}</span>
          </button>

          <div class="form-footer">
            <a routerLink="/forgot-password" class="text-link" *ngIf="!isRegisterMode">Forgot password?</a>
            <button mat-button type="button" class="switch-btn" (click)="switchToRegister()" *ngIf="!ssoOnly">
              {{ isRegisterMode ? 'Already have an account? Sign in' : 'Create account' }}
            </button>
          </div>
        </form>
      </mat-card>
    </div>
  `,
  styles: [`
    /* -----------------------------------------------------------------------
       Page shell — background is set via the [backgroundStyle] binding which
       reads the --hop-login-bg CSS property.  Apps override it in their
       global stylesheet:

         :root { --hop-login-bg: #1a2f4e; }
         :root { --hop-login-bg: url('/assets/bg.jpg') center/cover no-repeat; }
    ----------------------------------------------------------------------- */
    .login-page {
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
      padding: 24px 16px;
      background: var(--hop-login-bg, var(--surface-sunken));
    }

    /* Card */
    .login-card {
      width: 100%;
      max-width: 420px;
      padding: 32px 32px 24px;
    }

    /* Brand mark — logo + app name above the heading */
    .card-brand {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 20px;
    }
    .brand-logo {
      height: 24px;
      width: auto;
      flex-shrink: 0;
    }
    .brand-name {
      font-size: 0.95rem;
      font-weight: 600;
      color: var(--text-primary);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    /* Heading & subtitle */
    .card-heading {
      margin: 0 0 6px;
      font-size: 1.5rem;
      font-weight: 700;
      color: var(--text-primary);
      letter-spacing: -0.02em;
    }
    .card-subtitle {
      margin: 0 0 20px;
      color: var(--text-secondary);
      font-size: 0.9rem;
      line-height: 1.5;
    }

    /* Form */
    .full-width { width: 100%; }

    .submit-btn {
      width: 100%;
      height: 44px;
      margin-top: 4px;
      font-size: 0.95rem;
      font-weight: 600;
      letter-spacing: 0.01em;
    }
    .submit-btn mat-spinner { display: inline-block; }

    .form-footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 4px;
      margin-top: 12px;
    }
    .text-link {
      color: var(--text-link);
      text-decoration: none;
      font-size: 0.85rem;
      &:hover { text-decoration: underline; }
    }
    .switch-btn { font-size: 0.85rem; color: var(--text-secondary); margin-left: auto; }

    .error-message { color: var(--color-error); font-size: 0.875rem; margin-bottom: 12px; }

    /* Org selection */
    .org-list { margin: 0 -16px; }
    .org-list-item { cursor: pointer; }
    .org-role { text-transform: capitalize; color: var(--text-secondary); }
    .loading-row { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 16px; }

    /* SSO */
    .sso-buttons { margin-bottom: 4px; }
    .google-btn-wrapper { display: flex; justify-content: center; margin-bottom: 8px; }
    .sso-btn { width: 100%; margin-bottom: 8px; height: 42px; }
    .sso-divider { display: flex; align-items: center; gap: 12px; margin: 16px 0 4px; }
    .sso-divider mat-divider { flex: 1; }
    .sso-divider-text { color: var(--text-tertiary); font-size: 13px; white-space: nowrap; }
    .sso-only-hint { text-align: center; color: var(--text-secondary); font-size: 14px; }

    @media (max-width: 480px) {
      .login-card { padding: 24px 20px 20px; }
    }
  `],
})
export class HopLoginComponent implements OnInit, AfterViewInit {
  private fb = inject(FormBuilder);
  private route = inject(ActivatedRoute);
  private authService = inject(HopAuthService);
  private organizationService = inject(HopOrganizationService);
  private ngZone = inject(NgZone);
  private apiUrl = inject(HOP_API_URL);
  private cdr = inject(ChangeDetectorRef);
  private tokenLogoSrc = inject(HOP_LOGO_SRC, { optional: true });
  private loginConfig = inject(HOP_LOGIN_CONFIG, { optional: true }) as HopLoginConfig | null;

  @ViewChild('googleBtnContainer') googleBtnContainer?: ElementRef;

  /**
   * URL for the logo shown at the top of the login card.
   * Falls back to the HOP_LOGO_SRC injection token when not set.
   */
  @Input() logoSrc: string | null = null;

  /**
   * App name shown next to the logo.
   * Falls back to HOP_LOGIN_CONFIG.appName when not set as an input.
   */
  @Input() appName = '';

  /**
   * Short tagline shown below "Sign in". Use it to describe what the app does,
   * e.g. "Review discoveries and manage the pipeline."
   * Falls back to HOP_LOGIN_CONFIG.subtitle when not set as an input.
   */
  @Input() subtitle = '';

  /** Resolved logo URL — input wins, then HOP_LOGO_SRC token, then nothing. */
  get resolvedLogoSrc(): string | null {
    return this.logoSrc ?? this.tokenLogoSrc ?? null;
  }

  /** Resolved app name — input wins, then HOP_LOGIN_CONFIG token. */
  get resolvedAppName(): string {
    return this.appName || this.loginConfig?.appName || '';
  }

  /** Resolved subtitle — input wins, then HOP_LOGIN_CONFIG token. */
  get resolvedSubtitle(): string {
    return this.subtitle || this.loginConfig?.subtitle || '';
  }

  /**
   * CSS `background` value applied to the page shell. Set the custom property
   * `--hop-login-bg` in your global stylesheet instead of binding this input;
   * the shell reads it automatically.  This input is an escape hatch for
   * programmatic overrides.
   *
   * Examples:
   *   '#1a2f4e'
   *   'url(/assets/login-bg.jpg) center/cover no-repeat'
   */
  @Input()
  get backgroundStyle(): string {
    return this._backgroundStyle;
  }
  set backgroundStyle(value: string) {
    this._backgroundStyle = value ? `background: ${value}` : '';
  }
  private _backgroundStyle = '';

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
  providersLoaded = false;

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
        this.providersLoaded = true;
        if (providers.google && providers.google_client_id) {
          this.googleClientId = providers.google_client_id;
          this.loadGoogleScript();
        }
        this.cdr.markForCheck();
      },
      // Unknown configuration: fall back to the password form rather than a blank card.
      error: () => {
        this.providersLoaded = true;
        this.cdr.markForCheck();
      },
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
          this.cdr.markForCheck();
          this.authService.navigateToDashboard(this.returnUrl);
        },
        error: err => {
          this.errorMessage = err.error?.detail || 'Google sign-in failed. Please try again.';
          this.loading = false;
          this.cdr.markForCheck();
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
          this.cdr.markForCheck();
        },
        error: error => {
          this.errorMessage = error.error?.detail || 'Registration failed';
          this.loading = false;
          this.cdr.markForCheck();
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
          this.cdr.markForCheck();
        },
        error: error => {
          this.errorMessage = error.error?.detail || 'Login failed';
          this.loading = false;
          this.cdr.markForCheck();
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
        this.cdr.markForCheck();
        this.authService.navigateToDashboard(this.returnUrl);
      },
      error: error => {
        this.errorMessage = error.error?.detail || 'Failed to switch organization';
        this.loading = false;
        this.cdr.markForCheck();
      },
    });
  }

  switchToRegister(): void {
    this.isRegisterMode = !this.isRegisterMode;
    this.errorMessage = '';
    const orgNameControl = this.loginForm.get('organizationName');
    if (this.isRegisterMode && !this.singleOrgMode) {
      orgNameControl?.setValidators([Validators.required]);
    } else {
      orgNameControl?.clearValidators();
    }
    orgNameControl?.updateValueAndValidity();
  }
}
