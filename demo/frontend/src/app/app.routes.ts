import { Routes } from '@angular/router';
import { hopAuthGuard, hopAdminGuard } from '@heretto/hop-ui';

export const routes: Routes = [
  // Unauthenticated routes — rendered without the main layout shell
  {
    path: 'login',
    loadComponent: () => import('@heretto/hop-ui').then(m => m.HopLoginComponent),
  },
  {
    path: 'forgot-password',
    loadComponent: () => import('@heretto/hop-ui').then(m => m.HopForgotPasswordComponent),
  },
  {
    path: 'reset-password',
    loadComponent: () => import('@heretto/hop-ui').then(m => m.HopResetPasswordComponent),
  },
  {
    path: 'auth/sso/complete',
    loadComponent: () => import('@heretto/hop-ui').then(m => m.HopSSOCallbackComponent),
  },
  {
    path: 'invite/:token',
    loadComponent: () => import('@heretto/hop-ui').then(m => m.HopAcceptInvitationComponent),
  },
  // Authenticated routes — rendered inside the HopMainLayoutComponent shell
  {
    path: '',
    canActivate: [hopAuthGuard],
    loadComponent: () => import('./shell/shell.component').then(m => m.ShellComponent),
    children: [
      {
        path: 'dashboard',
        loadComponent: () =>
          import('./dashboard/dashboard.component').then(m => m.DashboardComponent),
      },
      {
        path: 'docs/dita',
        loadComponent: () =>
          import('./dita-docs/dita-docs.component').then(m => m.DitaDocsComponent),
      },
      {
        path: 'widgets',
        loadComponent: () =>
          import('./widgets/widgets.component').then(m => m.WidgetsComponent),
      },
      {
        path: 'account',
        loadComponent: () => import('@heretto/hop-ui').then(m => m.HopAccountComponent),
      },
      {
        path: 'admin',
        canActivate: [hopAdminGuard],
        loadComponent: () => import('@heretto/hop-ui').then(m => m.HopAdminComponent),
      },
      { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
    ],
  },
  { path: '**', redirectTo: '' },
];
