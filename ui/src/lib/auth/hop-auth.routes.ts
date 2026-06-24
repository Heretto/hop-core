import { Routes } from '@angular/router';
import { hopAuthGuard } from './hop-auth.guard';
import { hopAdminGuard } from './hop-admin.guard';

export const HOP_ROUTES: Routes = [
  {
    path: 'login',
    loadComponent: () => import('./hop-login.component').then(m => m.HopLoginComponent),
  },
  {
    path: 'forgot-password',
    loadComponent: () => import('./hop-forgot-password.component').then(m => m.HopForgotPasswordComponent),
  },
  {
    path: 'reset-password',
    loadComponent: () => import('./hop-reset-password.component').then(m => m.HopResetPasswordComponent),
  },
  {
    path: 'auth/sso/complete',
    loadComponent: () => import('./hop-sso-callback.component').then(m => m.HopSSOCallbackComponent),
  },
  {
    path: 'invite/:token',
    loadComponent: () => import('./hop-accept-invitation.component').then(m => m.HopAcceptInvitationComponent),
  },
  {
    path: 'account',
    canActivate: [hopAuthGuard],
    loadComponent: () => import('../account/hop-account.component').then(m => m.HopAccountComponent),
  },
  {
    path: 'admin',
    canActivate: [hopAuthGuard, hopAdminGuard],
    loadComponent: () => import('../admin/hop-admin.component').then(m => m.HopAdminComponent),
  },
];
