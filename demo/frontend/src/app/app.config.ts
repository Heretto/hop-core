import { ApplicationConfig } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptors, withXhr } from '@angular/common/http';
import { provideAnimations } from '@angular/platform-browser/animations';

import { hopAuthInterceptor, HOP_LOGIN_CONFIG, provideHopUi } from '@heretto/hop-ui';
import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideRouter(routes),
    provideHttpClient(withXhr(), withInterceptors([hopAuthInterceptor])),
    provideAnimations(),
    provideHopUi(),
    {
      provide: HOP_LOGIN_CONFIG,
      useValue: {
        appName: 'HOP Core Demo',
        subtitle: 'Platform library for multi-tenant AI-powered apps.',
      },
    },
  ],
};
