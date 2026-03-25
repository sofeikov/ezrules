import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';
import { AuthService } from '../services/auth.service';
import { PermissionRequirement, hasPermissionRequirement } from './permissions';

export const permissionGuard: CanActivateFn = (route, state) => {
  const authService = inject(AuthService);
  const router = inject(Router);

  if (!authService.getAccessToken()) {
    return router.createUrlTree(['/login']);
  }

  const requirement = route.data?.['permissionRequirement'] as PermissionRequirement | undefined;
  if (!requirement) {
    return true;
  }

  const cachedUser = authService.getCurrentUserSnapshot();
  if (cachedUser) {
    if (hasPermissionRequirement(cachedUser.permissions, requirement)) {
      return true;
    }

    return router.createUrlTree(['/access-denied'], {
      queryParams: {
        from: state.url,
        all: requirement.allOf?.join(',') || null,
        any: requirement.anyOf?.join(',') || null,
      },
    });
  }

  return authService.getCurrentUser().pipe(
    map((user) => {
      if (hasPermissionRequirement(user.permissions, requirement)) {
        return true;
      }

      return router.createUrlTree(['/access-denied'], {
        queryParams: {
          from: state.url,
          all: requirement.allOf?.join(',') || null,
          any: requirement.anyOf?.join(',') || null,
        },
      });
    }),
    catchError(() => of(router.createUrlTree(['/login'])))
  );
};
