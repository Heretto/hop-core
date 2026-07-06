import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDividerModule } from '@angular/material/divider';

@Component({
  selector: 'app-auth-docs',
  standalone: true,
  imports: [RouterLink, MatCardModule, MatButtonModule, MatIconModule, MatDividerModule],
  template: `
    <div class="auth-docs">
      <a mat-button routerLink="/dashboard" class="back-link">
        <mat-icon>arrow_back</mat-icon>
        Back to Dashboard
      </a>

      <h1>Multi-tenant Auth</h1>
      <p class="subtitle">
        Everything hop-core ships for authentication and multi-tenancy, and how
        to wire it into your own app.
      </p>

      <!-- CAPABILITIES -->
      <h2>What you get</h2>
      <div class="capability-grid">
        <mat-card class="capability">
          <mat-card-header>
            <mat-icon mat-card-avatar>password</mat-icon>
            <mat-card-title>Email &amp; password</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <p>
              Registration and login with bcrypt hashing (automatic rehash),
              JWT access + refresh tokens, HttpOnly cookies, and a token-based
              password-reset flow with SMTP delivery.
            </p>
          </mat-card-content>
        </mat-card>

        <mat-card class="capability">
          <mat-card-header>
            <mat-icon mat-card-avatar>login</mat-icon>
            <mat-card-title>Single sign-on</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <p>
              Google (client-side ID token) and Microsoft (server-side OIDC)
              OAuth flows. Buttons appear on the login page automatically once
              the provider is configured. <code>SSO_ONLY=true</code> hides the
              password form entirely.
            </p>
          </mat-card-content>
        </mat-card>

        <mat-card class="capability">
          <mat-card-header>
            <mat-icon mat-card-avatar>business</mat-icon>
            <mat-card-title>Organizations &amp; roles</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <p>
              Every user belongs to one or more organizations with a role
              (admin / member). Org switching re-issues tokens scoped to the
              active org. <code>SINGLE_ORG_MODE=true</code> collapses the model
              to one org for simpler apps.
            </p>
          </mat-card-content>
        </mat-card>

        <mat-card class="capability">
          <mat-card-header>
            <mat-icon mat-card-avatar>mail</mat-icon>
            <mat-card-title>Invitations</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <p>
              Token-based email invitations for new and existing users, with an
              admin-managed pending list and an acceptance flow at
              <code>/invite/:token</code>.
            </p>
          </mat-card-content>
        </mat-card>

        <mat-card class="capability">
          <mat-card-header>
            <mat-icon mat-card-avatar>verified_user</mat-icon>
            <mat-card-title>Route protection</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <p>
              <code>hopAuthGuard</code>, <code>hopAdminGuard</code>, and
              <code>hopSuperuserGuard</code> gate your routes, and
              <code>hopAuthInterceptor</code> attaches the Bearer token and
              transparently refreshes it on 401.
            </p>
          </mat-card-content>
        </mat-card>

        <mat-card class="capability">
          <mat-card-header>
            <mat-icon mat-card-avatar>security</mat-icon>
            <mat-card-title>Security baseline</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <p>
              CSRF double-submit cookie protection, rate limiting, SSRF-safe
              URL validation, and security response headers — on by default in
              every hop-core backend.
            </p>
          </mat-card-content>
        </mat-card>
      </div>

      <!-- TRY IT -->
      <h2>Try it in this demo</h2>
      <mat-card class="section-card">
        <mat-card-content>
          <ul class="try-list">
            <li>
              <strong>Login &amp; registration</strong> — log out and you'll land on the
              login page (<code>HopLoginComponent</code>), which also hosts registration
              and the SSO buttons.
            </li>
            <li>
              <strong>Invitations &amp; roles</strong> — open
              <a routerLink="/admin">Organization Admin</a> to invite a member and manage
              roles (<code>HopAdminComponent</code>).
            </li>
            <li>
              <strong>Account self-service</strong> — change email or password under
              <a routerLink="/account">My Account</a> (<code>HopAccountComponent</code>).
            </li>
            <li>
              <strong>Org switching</strong> — create a second organization and use the
              switcher in the toolbar; note the re-issued token.
            </li>
          </ul>
        </mat-card-content>
      </mat-card>

      <!-- IMPLEMENTATION -->
      <h2>Implementing it in your app</h2>

      <mat-card class="section-card">
        <mat-card-header>
          <mat-card-title>1. Backend — create the app</mat-card-title>
        </mat-card-header>
        <mat-card-content>
          <p>
            Install hop-core and call <code>create_hop_app()</code>. All auth, SSO,
            organization, invitation, and account routes are registered under
            <code>/api/v1</code>, with CORS, CSRF, sessions, and rate limiting wired up.
          </p>
          <div class="hop-code-panel"><pre>{{ backendSnippet }}</pre></div>
          <p>Set the required environment variables:</p>
          <div class="hop-code-panel"><pre>{{ envSnippet }}</pre></div>
        </mat-card-content>
      </mat-card>

      <mat-card class="section-card">
        <mat-card-header>
          <mat-card-title>2. Frontend — wire the interceptor and routes</mat-card-title>
        </mat-card-header>
        <mat-card-content>
          <p>
            Register <code>hopAuthInterceptor</code> so every request carries the Bearer
            token (and refreshes it on 401), then mount the prebuilt components on your
            routes. <code>HOP_ROUTES</code> gives you the full set in one line, or pick
            routes individually:
          </p>
          <div class="hop-code-panel"><pre>{{ frontendSnippet }}</pre></div>
        </mat-card-content>
      </mat-card>

      <mat-card class="section-card">
        <mat-card-header>
          <mat-card-title>3. Enable SSO (optional)</mat-card-title>
        </mat-card-header>
        <mat-card-content>
          <p>
            <strong>Google</strong> — create an OAuth <em>Web application</em> client in
            Google Cloud Console and set <code>GOOGLE_OAUTH_CLIENT_ID</code>. The login
            page renders Google's button and posts the ID token to the backend — no
            client secret or redirect URI needed.
          </p>
          <p>
            <strong>Microsoft</strong> — register an app in Entra ID, set
            <code>MICROSOFT_OAUTH_CLIENT_ID</code> and
            <code>MICROSOFT_OAUTH_CLIENT_SECRET</code>, and add
            <code>https://your-app/auth/sso/complete</code> as the redirect URI. The
            backend runs the OIDC flow server-side and hands the session to
            <code>HopSSOCallbackComponent</code>.
          </p>
          <div class="hop-code-panel"><pre>{{ ssoSnippet }}</pre></div>
        </mat-card-content>
      </mat-card>

      <mat-card class="section-card">
        <mat-card-header>
          <mat-card-title>Auth API endpoints</mat-card-title>
        </mat-card-header>
        <mat-card-content>
          <p>All prefixed with <code>/api/v1</code>:</p>
          <table class="endpoint-table">
            <tr><th>Method</th><th>Path</th><th>Description</th></tr>
            <tr><td>POST</td><td><code>/auth/register</code></td><td>Create account (+ org)</td></tr>
            <tr><td>POST</td><td><code>/auth/login</code></td><td>Login, returns tokens</td></tr>
            <tr><td>POST</td><td><code>/auth/logout</code></td><td>Clear auth cookies</td></tr>
            <tr><td>POST</td><td><code>/auth/refresh</code></td><td>Refresh access token</td></tr>
            <tr><td>POST</td><td><code>/auth/forgot-password</code></td><td>Send reset email</td></tr>
            <tr><td>POST</td><td><code>/auth/reset-password</code></td><td>Reset with token</td></tr>
            <tr><td>GET</td><td><code>/sso/google</code></td><td>Google SSO</td></tr>
            <tr><td>GET</td><td><code>/sso/microsoft</code></td><td>Microsoft SSO</td></tr>
            <tr><td>POST</td><td><code>/organizations/switch/&#123;id&#125;</code></td><td>Switch active org (re-issues tokens)</td></tr>
          </table>
          <p class="table-note">
            The full API reference, including organization, invitation, and account
            endpoints, is in the hop-core README.
          </p>
        </mat-card-content>
      </mat-card>
    </div>
  `,
  styles: [`
    .auth-docs { max-width: 900px; margin: 0 auto; padding-bottom: 48px; }
    .back-link { margin-bottom: 16px; }
    h1 { margin-bottom: 8px; }
    .subtitle { color: var(--text-secondary); margin-bottom: 32px; }
    h2 { margin: 32px 0 16px; }

    .capability-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
    }
    .capability mat-icon[mat-card-avatar] {
      font-size: 32px; width: 32px; height: 32px; color: var(--color-accent);
    }
    .capability p, .section-card p { color: var(--text-secondary); line-height: 1.6; }

    .section-card { margin-bottom: 16px; }
    .try-list { margin: 0; padding-left: 20px; color: var(--text-secondary); line-height: 1.9; }

    .hop-code-panel { margin-bottom: 16px; }

    .endpoint-table { border-collapse: collapse; width: 100%; }
    .endpoint-table th {
      text-align: left; font-size: 0.78rem; text-transform: uppercase;
      letter-spacing: 0.04em; color: var(--text-tertiary);
      padding: 6px 12px 6px 0; border-bottom: 1px solid var(--border-default);
    }
    .endpoint-table td {
      padding: 6px 12px 6px 0; border-bottom: 1px solid var(--border-light);
      color: var(--text-secondary); font-size: 0.9rem;
    }
    .table-note { margin-top: 12px; font-size: 0.85rem; }
  `],
})
export class AuthDocsComponent {
  backendSnippet = `from functools import lru_cache
from hop_core.app_factory import create_hop_app
from hop_core.config import HopCoreSettings

class AppSettings(HopCoreSettings):
    pass  # add app-specific settings here

@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()

app = create_hop_app(
    settings_factory=get_settings,
    title="My App",
    version="1.0.0",
)`;

  envSnippet = `APP_SECRET_KEY=<32+ chars>       # session signing
JWT_SECRET_KEY=<32+ chars>       # JWT signing
ENCRYPTION_KEY=<16+ chars>       # credential encryption
DATABASE_URL=sqlite:///./app.db  # or postgresql://...
CORS_ORIGINS=http://localhost:4200`;

  frontendSnippet = `// app.config.ts
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { hopAuthInterceptor } from '@heretto/hop-ui';

export const appConfig: ApplicationConfig = {
  providers: [
    provideRouter(routes),
    provideHttpClient(withInterceptors([hopAuthInterceptor])),
    provideAnimations(),
  ],
};

// app.routes.ts — everything in one line...
import { HOP_ROUTES } from '@heretto/hop-ui';
export const routes: Routes = [...HOP_ROUTES, /* your routes */];

// ...or pick routes individually and guard your own:
import { hopAuthGuard, hopAdminGuard } from '@heretto/hop-ui';
export const routes: Routes = [
  { path: 'login',
    loadComponent: () => import('@heretto/hop-ui').then(m => m.HopLoginComponent) },
  { path: 'auth/sso/complete',
    loadComponent: () => import('@heretto/hop-ui').then(m => m.HopSSOCallbackComponent) },
  { path: '', canActivate: [hopAuthGuard], component: ShellComponent, children: [
    { path: 'admin', canActivate: [hopAdminGuard],
      loadComponent: () => import('@heretto/hop-ui').then(m => m.HopAdminComponent) },
  ]},
];`;

  ssoSnippet = `# Google — client-side ID token flow
GOOGLE_OAUTH_CLIENT_ID=1234567890-abc.apps.googleusercontent.com

# Microsoft — server-side OIDC flow
MICROSOFT_OAUTH_CLIENT_ID=00000000-0000-0000-0000-000000000000
MICROSOFT_OAUTH_CLIENT_SECRET=<from Entra ID>

# Optional behavior flags
SSO_ONLY=false          # true: hide the email/password form
SINGLE_ORG_MODE=false   # true: one org, no switching`;
}
