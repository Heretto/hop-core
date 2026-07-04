import { Component } from '@angular/core';
import { HopMainLayoutComponent, NavItem } from '@heretto/hop-ui';

@Component({
    selector: 'app-shell',
    imports: [HopMainLayoutComponent],
    template: `<hop-main-layout appTitle="Hop Demo" logoSrc="assets/heretto_open_projects.png" [navItems]="navItems"></hop-main-layout>`
})
export class ShellComponent {
  navItems: NavItem[] = [
    { label: 'Dashboard', route: '/dashboard', icon: 'dashboard' },
    { label: 'Widget Library', route: '/widgets', icon: 'widgets' },
  ];
}
