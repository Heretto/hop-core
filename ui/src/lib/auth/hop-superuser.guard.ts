import { inject } from '@angular/core';
import { Router, CanActivateFn } from '@angular/router';
import { HopAccountService } from '../shared/hop-account.service';
import { map, take, switchMap, of } from 'rxjs';

export const hopSuperuserGuard: CanActivateFn = () => {
  const accountService = inject(HopAccountService);
  const router = inject(Router);

  return accountService.accountInfo$.pipe(
    take(1),
    switchMap(info => info ? of(info) : accountService.getAccountInfo()),
    map(info => {
      if (info?.is_superuser) return true;
      router.navigate(['/dashboard']);
      return false;
    })
  );
};
