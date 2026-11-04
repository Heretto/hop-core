import { InjectionToken } from '@angular/core';

export interface HopLoginConfig {
  /** App name displayed beside the logo in the login card header. */
  appName?: string;
  /**
   * Short tagline shown below "Sign in", e.g. "Review discoveries and manage
   * the pipeline."  Hidden on the registration step.
   */
  subtitle?: string;
}

/**
 * Optional token for configuring the login card's brand header and subtitle.
 * Provide it in app.config.ts (or a route's providers) so lazy-loaded apps
 * don't need a wrapper component:
 *
 *   { provide: HOP_LOGIN_CONFIG, useValue: { appName: 'My App', subtitle: 'Tagline' } }
 *
 * Direct `[appName]` / `[subtitle]` inputs on `<hop-login>` take precedence.
 */
export const HOP_LOGIN_CONFIG = new InjectionToken<HopLoginConfig>('HOP_LOGIN_CONFIG');
