import { InjectionToken } from '@angular/core';

/** URL for the brand logo displayed in the top bar (e.g. 'assets/logo.svg').
 *  Provide this token in your app config so all hop-ui layout components
 *  pick it up automatically without needing a [logoSrc] input binding. */
export const HOP_LOGO_SRC = new InjectionToken<string>('HOP_LOGO_SRC');
