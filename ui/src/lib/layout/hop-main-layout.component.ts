import { Component, Input, OnInit, inject } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { CommonModule } from '@angular/common';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatListModule } from '@angular/material/list';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule } from '@angular/material/menu';
import { MatDividerModule } from '@angular/material/divider';
import { HopAuthService } from '../auth/hop-auth.service';
import { HopOrganizationService, Organization } from '../shared/hop-organization.service';
import { HopAccountService } from '../shared/hop-account.service';
import { NavItem } from './nav-item.model';

@Component({
  selector: 'hop-main-layout',
  standalone: true,
  imports: [
    CommonModule,
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    MatToolbarModule,
    MatSidenavModule,
    MatListModule,
    MatIconModule,
    MatButtonModule,
    MatMenuModule,
    MatDividerModule,
  ],
  template: `
    <div class="layout-shell">
      <mat-toolbar class="top-bar">
        <a class="brand" routerLink="/">
          <ng-container *ngIf="logoSrc; else brandText">
            <!-- Decorative alt when the name renders beside it; otherwise the
                 logo carries the accessible label. -->
            <img class="brand-logo" [src]="logoSrc" [alt]="appTitle ? '' : 'Home'" />
            <ng-container *ngIf="appTitle">
              <span class="brand-sep"></span>
              <span class="brand-name">{{ appTitle }}</span>
            </ng-container>
          </ng-container>
          <ng-template #brandText>
            <mat-icon class="brand-mark">hub</mat-icon>
            <span class="brand-name">{{ appTitle }}</span>
          </ng-template>
        </a>
        <span class="spacer"></span>

        <div class="top-bar-actions">
          <button mat-icon-button [matMenuTriggerFor]="userMenu" aria-label="Account">
            <mat-icon>account_circle</mat-icon>
          </button>
          <mat-menu #userMenu="matMenu">
            <button mat-menu-item routerLink="/account">
              <mat-icon>account_circle</mat-icon>
              <span>My Account</span>
            </button>
            <mat-divider></mat-divider>
            <button mat-menu-item (click)="logout()">
              <mat-icon>logout</mat-icon>
              <span>Logout</span>
            </button>
          </mat-menu>

          <ng-container *ngIf="currentOrganization$ | async as org">
            <span class="top-bar-sep"></span>
            <button mat-icon-button [matMenuTriggerFor]="settingsMenu" aria-label="Organization settings">
              <mat-icon>settings</mat-icon>
            </button>
            <mat-menu #settingsMenu="matMenu">
              <div mat-menu-item disabled class="org-menu-header">
                <strong>{{ org.name }}</strong>
              </div>
              <mat-divider></mat-divider>
              <ng-container *ngIf="userOrganizations.length > 1">
                <div class="org-switch-label" mat-menu-item disabled>
                  <small>Switch Organization</small>
                </div>
                <button mat-menu-item *ngFor="let switchOrg of userOrganizations"
                        [disabled]="switchOrg.id === org.id"
                        (click)="switchToOrg(switchOrg)">
                  <mat-icon>{{ switchOrg.id === org.id ? 'check' : 'business' }}</mat-icon>
                  <span>{{ switchOrg.name }}</span>
                </button>
                <mat-divider></mat-divider>
              </ng-container>
              <button mat-menu-item routerLink="/admin" *ngIf="isAdmin$ | async">
                <mat-icon>admin_panel_settings</mat-icon>
                <span>Manage Organization</span>
              </button>
            </mat-menu>
          </ng-container>
        </div>
      </mat-toolbar>

      <mat-sidenav-container class="sidenav-container">
        <mat-sidenav mode="side" [opened]="true" class="sidenav">
          <mat-nav-list>
            <ng-container *ngFor="let item of navItems">
              <a mat-list-item
                 *ngIf="(!item.adminOnly && !item.superuserOnly)
                        || (item.adminOnly && (isAdmin$ | async))
                        || (item.superuserOnly && (isSuperuser$ | async))"
                 [routerLink]="item.route"
                 routerLinkActive="active">
                <mat-icon matListItemIcon>{{ item.icon }}</mat-icon>
                <span matListItemTitle>{{ item.label }}</span>
              </a>
            </ng-container>
            <!-- Platform routes always available -->
            <a mat-list-item routerLink="/account" routerLinkActive="active">
              <mat-icon matListItemIcon>account_circle</mat-icon>
              <span matListItemTitle>Account</span>
            </a>
            <a mat-list-item routerLink="/admin" routerLinkActive="active" *ngIf="isAdmin$ | async">
              <mat-icon matListItemIcon>admin_panel_settings</mat-icon>
              <span matListItemTitle>Administration</span>
            </a>
            <a mat-list-item routerLink="/superadmin" routerLinkActive="active" *ngIf="isSuperuser$ | async">
              <mat-icon matListItemIcon>security</mat-icon>
              <span matListItemTitle>System Admin</span>
            </a>
          </mat-nav-list>
        </mat-sidenav>

        <mat-sidenav-content>
          <div class="content">
            <router-outlet></router-outlet>
          </div>
        </mat-sidenav-content>
      </mat-sidenav-container>
    </div>
  `,
  styles: [`
    :host { display: block; height: 100%; }

    .layout-shell { display: flex; flex-direction: column; height: 100%; }

    /* Full-width top bar (white in light mode) with the brand pinned left. */
    .top-bar {
      position: sticky; top: 0; z-index: 10;
      display: flex; align-items: center;
      height: 56px; min-height: 56px;
      padding: 0;
      background: var(--header-bg);
      color: var(--text-primary);
      border-bottom: 1px solid var(--header-border);
    }
    .brand {
      display: flex; align-items: center; gap: 10px;
      height: 100%; padding: 0 20px;
      color: var(--text-primary); text-decoration: none; cursor: pointer;
      font-weight: 600; font-size: 1.1rem; letter-spacing: -0.01em;
    }
    .brand:hover { text-decoration: none; color: var(--text-primary); }
    .brand-logo { display: block; height: 36px; width: auto; }
    .brand-sep { width: 1px; height: 22px; flex: none; background: var(--border-default); margin: 0 2px; }
    .brand-mark { color: var(--color-accent); }
    .spacer { flex: 1 1 auto; }

    .top-bar-actions { display: flex; align-items: center; gap: 4px; padding-right: 12px; }
    .top-bar-actions button { color: var(--text-secondary); }
    .top-bar-actions .mat-mdc-icon-button:hover { background: var(--hover-overlay); }

    /* Body: one shared background below the header; the sidebar is delineated
       by a hairline, not a different surface color. */
    .sidenav-container { flex: 1 1 auto; min-height: 0; background: var(--bg-secondary); }
    .sidenav {
      width: var(--hop-sidebar-width, 250px);
      padding-top: 8px;
      background: var(--bg-secondary);
      border-right: 1px solid var(--border-default);
    }
    .content { padding: 24px; min-height: 100%; background: var(--bg-secondary); }

    /* Nav items: inset rounded rows; active = simple soft teal highlight. */
    .sidenav .mat-mdc-list-item {
      width: calc(100% - 16px);
      margin: 2px 8px;
      border-radius: 8px;
    }
    .sidenav .active {
      --mdc-list-list-item-label-text-color: var(--color-accent-text);
      --mdc-list-list-item-hover-label-text-color: var(--color-accent-text);
      --mdc-list-list-item-leading-icon-color: var(--color-accent-text);
      --mdc-list-list-item-hover-leading-icon-color: var(--color-accent-text);
      background-color: var(--color-accent-bg);
    }

    .top-bar-sep {
      width: 1px; height: 20px; flex: none;
      background: var(--border-default);
      margin: 0 6px;
    }
    .org-menu-header { padding: 8px 16px; cursor: default; }
    .org-switch-label { cursor: default; opacity: 0.7; }
  `],
})
export class HopMainLayoutComponent implements OnInit {
  @Input() appTitle = 'App';
  /** Brand image for the top bar (e.g. 'assets/logo.png'). Rendered at the
   *  far left; when appTitle is also set, the name appears beside it after a
   *  thin divider. Set appTitle to '' for a logo-only brand. */
  @Input() logoSrc?: string;
  @Input() navItems: NavItem[] = [];

  private authService = inject(HopAuthService);
  private organizationService = inject(HopOrganizationService);
  private accountService = inject(HopAccountService);

  currentOrganization$ = this.organizationService.currentOrganization$;
  isAdmin$ = this.accountService.isAdmin$;
  isSuperuser$ = this.accountService.isSuperuser$;
  userOrganizations: Organization[] = [];

  ngOnInit(): void {
    this.accountService.getAccountInfo().subscribe({
      next: () => {
        this.organizationService.getCurrentOrganization().subscribe();
        this.organizationService.listUserOrganizations().subscribe({
          next: orgs => { this.userOrganizations = orgs; },
        });
      },
    });
  }

  logout(): void {
    this.accountService.clearAccountInfo();
    this.authService.logout();
  }

  switchToOrg(org: Organization): void {
    this.organizationService.switchOrganization(org.id).subscribe({
      next: response => {
        this.authService.updateTokens(response);
        window.location.reload();
      },
    });
  }
}
