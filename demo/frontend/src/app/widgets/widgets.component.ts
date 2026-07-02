import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatRadioModule } from '@angular/material/radio';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSliderModule } from '@angular/material/slider';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTableModule } from '@angular/material/table';
import { MatListModule } from '@angular/material/list';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatBadgeModule } from '@angular/material/badge';
import { MatDividerModule } from '@angular/material/divider';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { HopConfirmDialogComponent, HopConfirmDialogData } from '@heretto/hop-ui';

interface Swatch {
  name: string;
  token: string;
}

interface SwatchGroup {
  title: string;
  swatches: Swatch[];
}

interface MemberRow {
  name: string;
  email: string;
  role: string;
  status: string;
}

@Component({
  selector: 'app-widgets',
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatIconModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatCheckboxModule,
    MatRadioModule,
    MatSlideToggleModule,
    MatSliderModule,
    MatChipsModule,
    MatProgressSpinnerModule,
    MatProgressBarModule,
    MatTabsModule,
    MatTableModule,
    MatListModule,
    MatMenuModule,
    MatTooltipModule,
    MatBadgeModule,
    MatDividerModule,
    MatDialogModule,
    MatSnackBarModule,
  ],
  template: `
    <div class="widgets">
      <header class="page-head">
        <h1>Widget Library</h1>
        <p class="subtitle">
          A living reference of the UI building blocks available in
          <strong>hop-core</strong>. Everything here is driven by the
          <strong>&#64;heretto/hop-ui</strong> design tokens and Angular Material M3,
          so what you see is exactly what you get in your own hop-core app.
        </p>
      </header>

      <!-- COLORS ---------------------------------------------------------- -->
      <section>
        <h2>Color tokens</h2>
        <p class="section-note">
          Semantic CSS custom properties. Reference them as
          <code>var(--color-primary)</code> — never hard-code hex values.
        </p>
        <div class="swatch-groups">
          @for (group of swatchGroups; track group.title) {
            <div class="swatch-group">
              <h3>{{ group.title }}</h3>
              <div class="swatches">
                @for (s of group.swatches; track s.token) {
                  <div class="swatch">
                    <span class="chip" [style.background]="'var(' + s.token + ')'"></span>
                    <div class="swatch-meta">
                      <span class="swatch-name">{{ s.name }}</span>
                      <code>{{ s.token }}</code>
                    </div>
                  </div>
                }
              </div>
            </div>
          }
        </div>
      </section>

      <!-- TYPOGRAPHY ------------------------------------------------------ -->
      <section>
        <h2>Typography</h2>
        <mat-card class="demo-card">
          <mat-card-content>
            <h1>Heading 1 — Inter Semibold</h1>
            <h2>Heading 2 — Inter Semibold</h2>
            <h3>Heading 3 — Inter Semibold</h3>
            <h4>Heading 4</h4>
            <p>
              Body text uses Inter at a tool-UI scale. Inline
              <a href="javascript:void(0)">links</a> pick up the accent color and a
              little <code>inline code</code> renders in {{ '{' }} Roboto Mono {{ '}' }}.
            </p>
            <p class="text-secondary">Secondary text — for supporting copy.</p>
            <p class="text-tertiary">Tertiary text — for hints and metadata.</p>
            <pre><code>const hop = 'core'; // block code</code></pre>
          </mat-card-content>
        </mat-card>
      </section>

      <!-- CARDS ----------------------------------------------------------- -->
      <section>
        <h2>Cards</h2>
        <p class="section-note">
          Two kinds: a <strong>normal card</strong> — a quiet hairline-bordered
          surface — and an <strong>accent card</strong>
          (<code>hop-card-accent</code>) whose colored left edge marks the
          active or highlighted item. The edge defaults to the teal accent and
          can be overridden per instance via
          <code>--hop-card-accent-color</code>.
        </p>
        <div class="card-stack">
          <mat-card class="demo-card">
            <mat-card-content>
              <h4 class="card-title">Normal card</h4>
              <p class="text-secondary card-body">
                The default surface for grouped content — hairline border on
                every side, no shadow.
              </p>
              <span class="card-meta">Added Jun 13, 2026 · original page</span>
            </mat-card-content>
          </mat-card>

          <mat-card class="demo-card hop-card-accent">
            <mat-card-content>
              <h4 class="card-title">Accent card</h4>
              <p class="text-secondary card-body">
                The teal left edge draws the eye to the selected or most
                relevant item in a stack.
              </p>
              <span class="card-meta">Added Jun 13, 2026 · original page</span>
            </mat-card-content>
          </mat-card>

          <mat-card class="demo-card hop-card-accent" style="--hop-card-accent-color: var(--color-warning)">
            <mat-card-content>
              <h4 class="card-title">Accent card — custom color</h4>
              <p class="text-secondary card-body">
                Re-point the edge at any status token, e.g.
                <code>--hop-card-accent-color: var(--color-warning)</code>.
              </p>
              <span class="card-meta">Added Jun 13, 2026 · original page</span>
            </mat-card-content>
          </mat-card>
        </div>
      </section>

      <!-- BUTTONS --------------------------------------------------------- -->
      <section>
        <h2>Buttons</h2>
        <mat-card class="demo-card">
          <mat-card-content>
            <div class="row">
              <button mat-button>Basic</button>
              <button mat-raised-button color="primary">Primary</button>
              <button mat-raised-button color="accent">Accent</button>
              <button mat-raised-button color="warn">Warn</button>
              <button mat-stroked-button>Stroked</button>
              <button mat-flat-button color="primary">Flat</button>
              <button mat-raised-button color="primary" disabled>Disabled</button>
            </div>
            <mat-divider></mat-divider>
            <div class="row">
              <button mat-icon-button color="primary" matTooltip="Icon button">
                <mat-icon>favorite</mat-icon>
              </button>
              <button mat-fab color="primary" matTooltip="FAB">
                <mat-icon>add</mat-icon>
              </button>
              <button mat-mini-fab color="accent" matTooltip="Mini FAB">
                <mat-icon>edit</mat-icon>
              </button>
              <button mat-stroked-button>
                <mat-icon>download</mat-icon>
                With icon
              </button>
            </div>
          </mat-card-content>
        </mat-card>
      </section>

      <!-- FORM CONTROLS --------------------------------------------------- -->
      <section>
        <h2>Form controls</h2>
        <mat-card class="demo-card">
          <mat-card-content>
            <div class="form-grid">
              <mat-form-field appearance="outline">
                <mat-label>Full name</mat-label>
                <input matInput placeholder="Ada Lovelace" [(ngModel)]="sampleName" />
                <mat-icon matSuffix>person</mat-icon>
              </mat-form-field>

              <mat-form-field appearance="outline">
                <mat-label>Email</mat-label>
                <input matInput type="email" placeholder="ada@example.com" />
                <mat-hint>We'll never share it.</mat-hint>
              </mat-form-field>

              <mat-form-field appearance="outline">
                <mat-label>Role</mat-label>
                <mat-select [(ngModel)]="selectedRole">
                  @for (role of roles; track role) {
                    <mat-option [value]="role">{{ role }}</mat-option>
                  }
                </mat-select>
              </mat-form-field>

              <mat-form-field appearance="outline">
                <mat-label>Notes</mat-label>
                <textarea matInput rows="1" placeholder="Optional notes…"></textarea>
              </mat-form-field>
            </div>

            <mat-divider></mat-divider>

            <div class="row toggles">
              <mat-checkbox [(ngModel)]="agree">Accept terms</mat-checkbox>
              <mat-slide-toggle [(ngModel)]="notifications">Email notifications</mat-slide-toggle>
              <mat-radio-group [(ngModel)]="plan" class="row">
                <mat-radio-button value="free">Free</mat-radio-button>
                <mat-radio-button value="pro">Pro</mat-radio-button>
                <mat-radio-button value="enterprise">Enterprise</mat-radio-button>
              </mat-radio-group>
            </div>

            <div class="slider-wrap">
              <label>Seat limit: {{ seats }}</label>
              <mat-slider min="1" max="50" step="1" showTickMarks discrete>
                <input matSliderThumb [(ngModel)]="seats" />
              </mat-slider>
            </div>
          </mat-card-content>
        </mat-card>
      </section>

      <!-- CHIPS & BADGES -------------------------------------------------- -->
      <section>
        <h2>Chips &amp; badges</h2>
        <mat-card class="demo-card">
          <mat-card-content>
            <mat-chip-set>
              <mat-chip>Default</mat-chip>
              <mat-chip highlighted color="primary">Primary</mat-chip>
              <mat-chip highlighted color="accent">Accent</mat-chip>
              <mat-chip>
                <mat-icon matChipAvatar>check</mat-icon>
                With icon
              </mat-chip>
              <mat-chip (removed)="removeChip()">
                Removable
                <button matChipRemove aria-label="Remove"><mat-icon>cancel</mat-icon></button>
              </mat-chip>
            </mat-chip-set>
            <mat-divider></mat-divider>
            <div class="row badge-row">
              <button mat-stroked-button matBadge="4" matBadgeColor="warn">Inbox</button>
              <mat-icon matBadge="12" matBadgeColor="accent">notifications</mat-icon>
              <mat-icon matBadge="!" matBadgeColor="warn">error</mat-icon>
            </div>
          </mat-card-content>
        </mat-card>
      </section>

      <!-- STATUS CALLOUTS ------------------------------------------------- -->
      <section>
        <h2>Status callouts</h2>
        <p class="section-note">
          Built from status tokens (<code>--color-success</code>,
          <code>--color-warning</code>, <code>--color-error</code>,
          <code>--color-info</code>) so they stay on-brand and are dark-mode ready.
        </p>
        <div class="callouts">
          <div class="callout success">
            <mat-icon>check_circle</mat-icon>
            <span>Changes saved successfully.</span>
          </div>
          <div class="callout info">
            <mat-icon>info</mat-icon>
            <span>A new organization invite is pending.</span>
          </div>
          <div class="callout warning">
            <mat-icon>warning</mat-icon>
            <span>Your plan is approaching its seat limit.</span>
          </div>
          <div class="callout error">
            <mat-icon>error</mat-icon>
            <span>We couldn't reach the server. Try again.</span>
          </div>
        </div>
      </section>

      <!-- PROGRESS -------------------------------------------------------- -->
      <section>
        <h2>Progress</h2>
        <mat-card class="demo-card">
          <mat-card-content>
            <div class="row progress-row">
              <mat-spinner diameter="36"></mat-spinner>
              <mat-progress-bar mode="indeterminate"></mat-progress-bar>
            </div>
            <mat-progress-bar mode="determinate" [value]="seats * 2"></mat-progress-bar>
          </mat-card-content>
        </mat-card>
      </section>

      <!-- TABS ------------------------------------------------------------ -->
      <section>
        <h2>Tabs</h2>
        <mat-card class="demo-card">
          <mat-card-content>
            <mat-tab-group>
              <mat-tab label="Overview">
                <p class="tab-body">Overview content lives here.</p>
              </mat-tab>
              <mat-tab label="Members">
                <p class="tab-body">Member management content.</p>
              </mat-tab>
              <mat-tab label="Settings">
                <p class="tab-body">Settings content.</p>
              </mat-tab>
            </mat-tab-group>
          </mat-card-content>
        </mat-card>
      </section>

      <!-- TABLE ----------------------------------------------------------- -->
      <section>
        <h2>Data table</h2>
        <mat-card class="demo-card no-pad">
          <table mat-table [dataSource]="members" class="full-width">
            <ng-container matColumnDef="name">
              <th mat-header-cell *matHeaderCellDef>Name</th>
              <td mat-cell *matCellDef="let m">{{ m.name }}</td>
            </ng-container>
            <ng-container matColumnDef="email">
              <th mat-header-cell *matHeaderCellDef>Email</th>
              <td mat-cell *matCellDef="let m">{{ m.email }}</td>
            </ng-container>
            <ng-container matColumnDef="role">
              <th mat-header-cell *matHeaderCellDef>Role</th>
              <td mat-cell *matCellDef="let m">
                <mat-chip highlighted color="primary">{{ m.role }}</mat-chip>
              </td>
            </ng-container>
            <ng-container matColumnDef="status">
              <th mat-header-cell *matHeaderCellDef>Status</th>
              <td mat-cell *matCellDef="let m">
                <span class="dot" [class.active]="m.status === 'Active'"></span>
                {{ m.status }}
              </td>
            </ng-container>
            <tr mat-header-row *matHeaderRowDef="memberColumns"></tr>
            <tr mat-row *matRowDef="let row; columns: memberColumns"></tr>
          </table>
        </mat-card>
      </section>

      <!-- LISTS & MENUS --------------------------------------------------- -->
      <section>
        <h2>Lists &amp; menus</h2>
        <div class="two-col">
          <mat-card class="demo-card no-pad">
            <mat-list>
              <mat-list-item>
                <mat-icon matListItemIcon>dashboard</mat-icon>
                <span matListItemTitle>Dashboard</span>
                <span matListItemLine>Overview of your workspace</span>
              </mat-list-item>
              <mat-divider></mat-divider>
              <mat-list-item>
                <mat-icon matListItemIcon>group</mat-icon>
                <span matListItemTitle>Members</span>
                <span matListItemLine>Manage your team</span>
              </mat-list-item>
              <mat-divider></mat-divider>
              <mat-list-item>
                <mat-icon matListItemIcon>settings</mat-icon>
                <span matListItemTitle>Settings</span>
                <span matListItemLine>Organization preferences</span>
              </mat-list-item>
            </mat-list>
          </mat-card>

          <mat-card class="demo-card">
            <mat-card-content>
              <p>Overflow actions live behind a menu trigger:</p>
              <button mat-stroked-button [matMenuTriggerFor]="menu">
                <mat-icon>more_vert</mat-icon>
                Actions
              </button>
              <mat-menu #menu="matMenu">
                <button mat-menu-item><mat-icon>edit</mat-icon><span>Edit</span></button>
                <button mat-menu-item><mat-icon>content_copy</mat-icon><span>Duplicate</span></button>
                <mat-divider></mat-divider>
                <button mat-menu-item><mat-icon>delete</mat-icon><span>Delete</span></button>
              </mat-menu>
            </mat-card-content>
          </mat-card>
        </div>
      </section>

      <!-- OVERLAYS -------------------------------------------------------- -->
      <section>
        <h2>Dialogs &amp; notifications</h2>
        <mat-card class="demo-card">
          <mat-card-content>
            <p class="section-note">
              <code>HopConfirmDialogComponent</code> ships with hop-ui — a ready-made
              confirmation dialog. Snackbars come from Angular Material.
            </p>
            <div class="row">
              <button mat-raised-button color="warn" (click)="openConfirm()">
                <mat-icon>delete</mat-icon>
                Open confirm dialog
              </button>
              <button mat-stroked-button (click)="showSnack()">
                <mat-icon>notifications</mat-icon>
                Show snackbar
              </button>
            </div>
            @if (lastConfirm !== null) {
              <p class="text-secondary result">
                Last dialog result: <strong>{{ lastConfirm ? 'Confirmed' : 'Cancelled' }}</strong>
              </p>
            }
          </mat-card-content>
        </mat-card>
      </section>
    </div>
  `,
  styles: [`
    .widgets { max-width: 1100px; margin: 0 auto; padding-bottom: 48px; }
    .page-head { margin-bottom: 32px; }
    h1 { margin-bottom: 8px; }
    .subtitle { color: var(--text-secondary); max-width: 720px; }
    section { margin-bottom: 40px; }
    section > h2 {
      padding-bottom: 8px;
      margin-bottom: 16px;
      border-bottom: 1px solid var(--border-default);
    }
    .section-note { color: var(--text-secondary); margin-bottom: 16px; }

    .demo-card.no-pad .mat-mdc-card { padding: 0; }

    /* Cards */
    .card-stack { display: flex; flex-direction: column; gap: 12px; }
    .card-title { margin-bottom: 4px; }
    .card-body { margin-bottom: 8px; }
    .card-meta { font-size: 0.78rem; color: var(--text-tertiary); }
    .row { display: flex; flex-wrap: wrap; align-items: center; gap: 16px; }
    mat-divider { margin: 20px 0; }

    /* Swatches */
    .swatch-groups { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 24px; }
    .swatch-group h3 { font-size: 0.95rem; margin-bottom: 12px; }
    .swatches { display: flex; flex-direction: column; gap: 10px; }
    .swatch { display: flex; align-items: center; gap: 12px; }
    .swatch .chip {
      width: 40px; height: 40px; border-radius: 8px; flex: none;
      border: 1px solid var(--border-default); box-shadow: var(--shadow-xs);
    }
    .swatch-meta { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
    .swatch-name { font-size: 0.85rem; color: var(--text-primary); }
    .swatch-meta code { font-size: 0.72rem; }

    /* Forms */
    .form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 8px 20px; }
    .form-grid mat-form-field { width: 100%; }
    .toggles { gap: 24px; }
    .slider-wrap { display: flex; flex-direction: column; margin-top: 16px; }
    .slider-wrap label { font-size: 0.85rem; color: var(--text-secondary); }

    .badge-row { gap: 28px; }
    .progress-row { gap: 24px; margin-bottom: 20px; }
    .progress-row mat-progress-bar { flex: 1; }

    /* Callouts */
    .callouts { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }
    .callout {
      display: flex; align-items: center; gap: 12px;
      padding: 12px 16px; border-radius: 8px; border: 1px solid transparent;
      font-size: 0.9rem;
    }
    .callout mat-icon { flex: none; }
    .callout.success { background: var(--color-success-bg); color: var(--color-success-text); border-color: var(--color-success-border); }
    .callout.info    { background: var(--color-info-bg);    color: var(--color-info-text); }
    .callout.warning { background: var(--color-warning-bg); color: var(--color-warning-text); border-color: var(--color-warning-border); }
    .callout.error   { background: var(--color-error-bg);   color: var(--color-error-text); border-color: var(--color-error-border); }

    .tab-body { padding: 20px 4px; color: var(--text-secondary); }

    .full-width { width: 100%; }
    .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; background: var(--text-disabled); }
    .dot.active { background: var(--color-success); }

    .two-col { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 24px; }
    .result { margin-top: 16px; margin-bottom: 0; }
  `]
})
export class WidgetsComponent {
  private dialog = inject(MatDialog);
  private snackBar = inject(MatSnackBar);

  sampleName = '';
  selectedRole = 'Member';
  roles = ['Owner', 'Admin', 'Member', 'Viewer'];
  agree = true;
  notifications = true;
  plan = 'pro';
  seats = 20;

  lastConfirm: boolean | null = null;

  swatchGroups: SwatchGroup[] = [
    {
      title: 'Brand',
      swatches: [
        { name: 'Primary (navy)', token: '--color-primary' },
        { name: 'Accent (teal)', token: '--color-accent' },
        { name: 'Tertiary (magenta)', token: '--color-tertiary' },
      ],
    },
    {
      title: 'Status',
      swatches: [
        { name: 'Success', token: '--color-success' },
        { name: 'Warning', token: '--color-warning' },
        { name: 'Error', token: '--color-error' },
        { name: 'Info', token: '--color-info' },
      ],
    },
    {
      title: 'Surfaces',
      swatches: [
        { name: 'Background', token: '--bg-primary' },
        { name: 'Secondary', token: '--bg-secondary' },
        { name: 'Surface', token: '--surface-default' },
        { name: 'Sunken', token: '--surface-sunken' },
      ],
    },
    {
      title: 'Borders',
      swatches: [
        { name: 'Default', token: '--border-default' },
        { name: 'Strong', token: '--border-strong' },
        { name: 'Focus', token: '--border-focus' },
      ],
    },
  ];

  memberColumns = ['name', 'email', 'role', 'status'];
  members: MemberRow[] = [
    { name: 'Ada Lovelace', email: 'ada@example.com', role: 'Owner', status: 'Active' },
    { name: 'Alan Turing', email: 'alan@example.com', role: 'Admin', status: 'Active' },
    { name: 'Grace Hopper', email: 'grace@example.com', role: 'Member', status: 'Invited' },
  ];

  removeChip(): void {
    this.snackBar.open('Chip removed', 'Dismiss', { duration: 2000 });
  }

  openConfirm(): void {
    const data: HopConfirmDialogData = {
      title: 'Delete organization?',
      message: 'This action cannot be undone. All members will lose access.',
      confirmText: 'Delete',
      cancelText: 'Keep it',
    };
    this.dialog
      .open(HopConfirmDialogComponent, { data })
      .afterClosed()
      .subscribe((result: boolean | undefined) => {
        this.lastConfirm = result ?? false;
      });
  }

  showSnack(): void {
    this.snackBar.open('This is a snackbar notification.', 'Got it', { duration: 3000 });
  }
}
