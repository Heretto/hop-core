import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

@Component({
    selector: 'app-dashboard',
    imports: [RouterLink, MatCardModule, MatButtonModule, MatIconModule],
    template: `
    <div class="dashboard">
      <h1>Welcome to Hop Demo</h1>
      <p class="subtitle">
        This demo runs the out-of-the-box interfaces included in <strong>hop-core</strong>
        and <strong>&#64;heretto/hop-ui</strong>.
      </p>

      <div class="cards">
        <mat-card class="feature-card">
          <mat-card-header>
            <mat-icon mat-card-avatar>lock</mat-icon>
            <mat-card-title>Multi-tenant Auth</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <p>
              JWT-based login and registration with organization switching, SSO support
              (Google &amp; Microsoft), invite-based onboarding, and role-based access
              control — all wired up and ready.
            </p>
          </mat-card-content>
        </mat-card>

        <mat-card class="feature-card">
          <mat-card-header>
            <mat-icon mat-card-avatar>fact_check</mat-icon>
            <mat-card-title>DITA Validation</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <p>
              DITA 1.3 validation as a reusable module — DTD validation against
              bundled OASIS grammars, structural fallback, deterministic
              auto-fixes, and an AI-driven correct-until-valid loop.
            </p>
          </mat-card-content>
          <mat-card-actions>
            <a mat-button color="primary" routerLink="/docs/dita">Learn More</a>
          </mat-card-actions>
        </mat-card>

        <mat-card class="feature-card">
          <mat-card-header>
            <mat-icon mat-card-avatar>admin_panel_settings</mat-icon>
            <mat-card-title>Organization Admin</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <p>
              Manage organization members, send invitations, change roles, and revoke
              access — all from the built-in admin panel.
            </p>
          </mat-card-content>
          <mat-card-actions>
            <a mat-button color="primary" routerLink="/admin">Open Admin</a>
          </mat-card-actions>
        </mat-card>

        <mat-card class="feature-card">
          <mat-card-header>
            <mat-icon mat-card-avatar>account_circle</mat-icon>
            <mat-card-title>Account Management</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <p>
              Built-in account settings page for updating email, changing password, and
              managing your profile, including a danger zone for account deletion.
            </p>
          </mat-card-content>
          <mat-card-actions>
            <a mat-button color="primary" routerLink="/account">My Account</a>
          </mat-card-actions>
        </mat-card>

        <mat-card class="feature-card">
          <mat-card-header>
            <mat-icon mat-card-avatar>widgets</mat-icon>
            <mat-card-title>Widget Library</mat-card-title>
          </mat-card-header>
          <mat-card-content>
            <p>
              A living reference of the UI building blocks in hop-core — color tokens,
              typography, buttons, forms, tables, dialogs, and more — all driven by the
              &#64;heretto/hop-ui design system.
            </p>
          </mat-card-content>
          <mat-card-actions>
            <a mat-button color="primary" routerLink="/widgets">Browse Widgets</a>
          </mat-card-actions>
        </mat-card>
      </div>
    </div>
  `,
    styles: [`
    .dashboard { max-width: 1100px; margin: 0 auto; }
    h1 { margin-bottom: 8px; }
    .subtitle { color: rgba(0,0,0,0.54); margin-bottom: 32px; }
    .cards {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 24px;
    }
    mat-card-content p { color: rgba(0,0,0,0.6); line-height: 1.6; }
  `]
})
export class DashboardComponent {}
