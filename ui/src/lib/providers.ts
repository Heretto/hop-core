import { EnvironmentProviders, makeEnvironmentProviders } from '@angular/core';
import { MAT_FORM_FIELD_DEFAULT_OPTIONS } from '@angular/material/form-field';

/**
 * Providers every hop-ui app should include in its app.config.ts.
 *
 * Sets MAT_FORM_FIELD_DEFAULT_OPTIONS so every <mat-form-field> defaults to
 * appearance="outline" without a per-field attribute. The hop-ui theme styles
 * the outlined variant only; a bare <mat-form-field> otherwise renders with
 * Angular Material's default filled appearance (grey background).
 */
export function provideHopUi(): EnvironmentProviders {
  return makeEnvironmentProviders([
    { provide: MAT_FORM_FIELD_DEFAULT_OPTIONS, useValue: { appearance: 'outline' } },
  ]);
}
