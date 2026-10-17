import {
  Component, DestroyRef, Input, OnInit, inject, ChangeDetectionStrategy, ChangeDetectorRef,
} from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { CommonModule } from '@angular/common';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule } from '@angular/material/menu';
import { MatDividerModule } from '@angular/material/divider';
import { HopAuthService } from '../auth/hop-auth.service';
import { HopOrganizationService, Organization } from '../shared/hop-organization.service';
import { HopAccountService } from '../shared/hop-account.service';
import { NavItem } from './nav-item.model';
import { HOP_LOGO_SRC } from '../tokens/hop-logo-src.token';
import { HERETTO_OPEN_PROJECTS_LOGO } from './heretto-open-projects-logo';

export type HopNavMode = 'pinned' | 'collapsed';

const NAV_STORAGE_KEY = 'hop-nav-pinned';
/** Long enough that sweeping the pointer across the rail doesn't open it. */
const HOVER_OPEN_DELAY_MS = 150;
/** Forgiving enough that briefly overshooting the open nav doesn't close it. */
const HOVER_CLOSE_DELAY_MS = 250;
const NARROW_QUERY = '(max-width: 768px)';

function readNavPreference(): boolean | null {
  try {
    const value = localStorage.getItem(NAV_STORAGE_KEY);
    return value === null ? null : value === 'true';
  } catch {
    return null;
  }
}

function writeNavPreference(pinned: boolean): void {
  try {
    localStorage.setItem(NAV_STORAGE_KEY, String(pinned));
  } catch {
    // Storage unavailable: the choice lasts until the page reloads.
  }
}

@Component({
  changeDetection: ChangeDetectionStrategy.Eager,
  selector: 'hop-main-layout',
  standalone: true,
  imports: [
    CommonModule,
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    MatToolbarModule,
    MatIconModule,
    MatButtonModule,
    MatMenuModule,
    MatDividerModule,
  ],
  template: `
    <div class="layout-shell">
      <mat-toolbar class="top-bar">
        <a class="brand" routerLink="/">
          <ng-container *ngIf="brandLogoSrc; else brandText">
            <!-- Decorative alt when the name renders beside it; otherwise the
                 logo carries the accessible label. -->
            <img class="brand-logo" [src]="brandLogoSrc" [alt]="appTitle ? '' : 'Home'" />
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

      <div class="body">
        <!-- The rail reserves the nav's width in the layout; the panel inside it
             is the nav itself, which floats over the content when a collapsed
             nav springs open. -->
        <div class="rail" [class.collapsed]="collapsed">
          <nav class="sidenav" aria-label="Main" [class.open]="!collapsed || expanded"
               [class.floating]="collapsed && expanded"
               (mouseenter)="hoverStart()" (mouseleave)="hoverEnd()"
               (focusin)="focusIn($event)" (focusout)="focusOut($event)" (keydown.escape)="close()">
            <div class="nav-items">
              <ng-container *ngFor="let item of navItems">
                <a class="nav-link"
                   *ngIf="(!item.adminOnly && !item.superuserOnly)
                          || (item.adminOnly && (isAdmin$ | async))
                          || (item.superuserOnly && (isSuperuser$ | async))"
                   [routerLink]="item.route" routerLinkActive="active" (click)="navigated()">
                  <mat-icon>{{ item.icon }}</mat-icon>
                  <span class="nav-label">{{ item.label }}</span>
                </a>
              </ng-container>
              <!-- Platform routes always available -->
              <a class="nav-link" routerLink="/account" routerLinkActive="active" (click)="navigated()">
                <mat-icon>account_circle</mat-icon>
                <span class="nav-label">Account</span>
              </a>
              <a class="nav-link" routerLink="/admin" routerLinkActive="active" *ngIf="isAdmin$ | async"
                 (click)="navigated()">
                <mat-icon>admin_panel_settings</mat-icon>
                <span class="nav-label">Administration</span>
              </a>
              <a class="nav-link" routerLink="/superadmin" routerLinkActive="active" *ngIf="isSuperuser$ | async"
                 (click)="navigated()">
                <mat-icon>security</mat-icon>
                <span class="nav-label">System Admin</span>
              </a>
            </div>
            <div class="nav-foot">
              <button type="button" class="nav-link nav-toggle" (click)="toggle()"
                      [attr.aria-label]="toggleLabel" [attr.aria-expanded]="narrow ? expanded : null"
                      [title]="toggleLabel">
                <mat-icon>{{ toggleIcon }}</mat-icon>
                <span class="nav-label">{{ toggleLabel }}</span>
              </button>
            </div>
          </nav>
        </div>

        <main class="content-scroll">
          <div class="content">
            <router-outlet></router-outlet>
          </div>
        </main>
      </div>
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
    .body { flex: 1 1 auto; min-height: 0; display: flex; background: var(--bg-secondary); }
    .rail {
      position: relative; z-index: 5; flex: none;
      width: var(--hop-sidebar-width, 250px);
      transition: width 200ms ease;
    }
    .rail.collapsed { width: var(--hop-sidebar-rail-width, 64px); }
    .sidenav {
      position: absolute; inset: 0 auto 0 0; box-sizing: border-box;
      display: flex; flex-direction: column;
      width: var(--hop-sidebar-rail-width, 64px); padding: 8px 0;
      overflow: hidden; background: var(--bg-secondary);
      border-right: 1px solid var(--border-default);
      transition: width 200ms ease, box-shadow 200ms ease;
    }
    .sidenav.open { width: var(--hop-sidebar-width, 250px); }
    /* Sprung open over the content: lift it off the page. */
    .sidenav.floating { box-shadow: var(--shadow-lg); }
    .nav-items { flex: 1 1 auto; min-height: 0; overflow-x: hidden; overflow-y: auto; }
    .content-scroll { flex: 1 1 auto; min-width: 0; overflow: auto; }
    .content { padding: 24px; min-height: 100%; box-sizing: border-box; background: var(--bg-secondary); }

    /* Nav items: inset rounded rows; active = simple soft teal highlight. The
       icon sits where it does in the rail, so opening the nav only reveals labels. */
    .nav-link {
      display: flex; align-items: center; gap: 16px; box-sizing: border-box;
      width: calc(100% - 16px); height: 44px; margin: 2px 8px; padding: 0 12px;
      border: 0; border-radius: 8px; background: transparent;
      font: inherit; font-size: 0.95rem; color: var(--text-primary);
      text-decoration: none; text-align: left; white-space: nowrap; cursor: pointer;
    }
    .nav-link:hover { background: var(--hover-overlay); color: var(--text-primary); text-decoration: none; }
    .nav-link mat-icon { flex: none; color: var(--text-secondary); }
    .nav-link.active { background: var(--color-accent-bg); color: var(--color-accent-text); }
    .nav-link.active mat-icon { color: var(--color-accent-text); }
    .nav-label { overflow: hidden; text-overflow: ellipsis; transition: opacity 150ms ease; }
    .sidenav:not(.open) .nav-label { opacity: 0; }
    .nav-foot { flex: none; margin-top: 8px; padding-top: 6px; border-top: 1px solid var(--border-default); }
    .nav-toggle { color: var(--text-secondary); }

    @media (prefers-reduced-motion: reduce) {
      .rail, .sidenav, .nav-label { transition: none; }
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
   *  thin divider. Set appTitle to '' for a logo-only brand.
   *  When unset, resolves via `brandLogoSrc` to the HOP_LOGO_SRC token or the
   *  embedded Heretto Open Projects brand logo. */
  @Input() logoSrc: string | undefined;
  private readonly hopLogoSrc = inject(HOP_LOGO_SRC, { optional: true });
  @Input() navItems: NavItem[] = [];
  /** How the nav starts for someone who hasn't chosen yet: `pinned` open, or
   *  `collapsed` to an icon rail that springs open on hover. Each user's own
   *  choice (the toggle at the bottom of the nav) is remembered in the browser. */
  @Input() navMode: HopNavMode = 'pinned';

  /** Brand logo resolved at render time — explicit [logoSrc] input, then the
   *  HOP_LOGO_SRC token, then the embedded Heretto Open Projects logo. Computed
   *  in a getter (not a field default) so router `withComponentInputBinding()`,
   *  which resets unbound inputs to undefined, can't clobber the fallback. */
  get brandLogoSrc(): string {
    return this.logoSrc ?? this.hopLogoSrc ?? HERETTO_OPEN_PROJECTS_LOGO;
  }

  private authService = inject(HopAuthService);
  private organizationService = inject(HopOrganizationService);
  private accountService = inject(HopAccountService);
  private cdr = inject(ChangeDetectorRef);
  private destroyRef = inject(DestroyRef);

  /** The user pinned the nav open. */
  pinned = true;
  /** A collapsed nav is sprung open (hover, focus, or the toggle on a narrow screen). */
  expanded = false;
  /** Narrow screens always use the rail; there is no hover to spring it open. */
  narrow = false;
  /** Set when the user collapses the nav with the pointer still on it, so it
   *  doesn't spring straight back open; cleared when the pointer leaves. */
  private hoverSuppressed = false;
  private hoverTimer?: ReturnType<typeof setTimeout>;

  currentOrganization$ = this.organizationService.currentOrganization$;
  isAdmin$ = this.accountService.isAdmin$;
  isSuperuser$ = this.accountService.isSuperuser$;
  userOrganizations: Organization[] = [];

  ngOnInit(): void {
    this.pinned = readNavPreference() ?? this.navMode !== 'collapsed';
    this.watchWidth();
    this.accountService.getAccountInfo().subscribe({
      next: () => {
        this.organizationService.getCurrentOrganization().subscribe();
        this.organizationService.listUserOrganizations().subscribe({
          next: orgs => { this.userOrganizations = orgs; this.cdr.markForCheck(); },
        });
      },
    });
  }

  // ── Collapsible nav ───────────────────────────────────────────────────────

  get collapsed(): boolean {
    return this.narrow || !this.pinned;
  }

  get toggleLabel(): string {
    if (this.narrow) return this.expanded ? 'Close menu' : 'Open menu';
    return this.pinned ? 'Collapse menu' : 'Keep menu open';
  }

  get toggleIcon(): string {
    if (this.narrow) return this.expanded ? 'left_panel_close' : 'left_panel_open';
    return this.pinned ? 'left_panel_close' : 'keep';
  }

  toggle(): void {
    this.clearHoverTimer();
    if (this.narrow) {
      this.expanded = !this.expanded;
      return;
    }
    this.pinned = !this.pinned;
    this.expanded = false;
    // Collapsing with the pointer on the nav would otherwise spring it open again.
    this.hoverSuppressed = !this.pinned;
    writeNavPreference(this.pinned);
  }

  hoverStart(): void {
    if (!this.collapsed || this.narrow || this.hoverSuppressed) return;
    this.schedule(true, HOVER_OPEN_DELAY_MS);
  }

  hoverEnd(): void {
    this.hoverSuppressed = false;
    if (!this.collapsed || this.narrow) return;
    this.schedule(false, HOVER_CLOSE_DELAY_MS);
  }

  /** Keyboard users get the labels too: tabbing into a collapsed nav opens it. */
  focusIn(event: FocusEvent): void {
    // A click focuses the link too; only keyboard focus should open the nav.
    const target = event.target as HTMLElement | null;
    if (!this.collapsed || this.hoverSuppressed || !target?.matches(':focus-visible')) return;
    this.clearHoverTimer();
    this.expanded = true;
  }

  focusOut(event: FocusEvent): void {
    const nav = event.currentTarget as HTMLElement;
    if (!this.collapsed || nav.contains(event.relatedTarget as Node | null)) return;
    if (nav.matches(':hover') && !this.narrow) return;
    this.expanded = false;
  }

  close(): void {
    this.clearHoverTimer();
    this.expanded = false;
  }

  /** On a narrow screen the open nav covers the page, so following a link closes it. */
  navigated(): void {
    if (this.narrow) this.expanded = false;
  }

  private schedule(open: boolean, delay: number): void {
    this.clearHoverTimer();
    if (this.expanded === open) return;
    this.hoverTimer = setTimeout(() => {
      this.expanded = open;
      this.cdr.markForCheck();
    }, delay);
  }

  private clearHoverTimer(): void {
    if (this.hoverTimer !== undefined) clearTimeout(this.hoverTimer);
    this.hoverTimer = undefined;
  }

  private watchWidth(): void {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const query = window.matchMedia(NARROW_QUERY);
    const update = () => {
      this.narrow = query.matches;
      this.expanded = false;
      this.cdr.markForCheck();
    };
    update();
    query.addEventListener('change', update);
    this.destroyRef.onDestroy(() => {
      query.removeEventListener('change', update);
      this.clearHoverTimer();
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
