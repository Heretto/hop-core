import { Component } from '@angular/core';
import { HopMainLayoutComponent, NavItem } from '@heretto/hop-ui';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [HopMainLayoutComponent],
  template: `<hop-main-layout appTitle="Hop Demo" [navItems]="navItems"></hop-main-layout>`,
})
export class ShellComponent {
  navItems: NavItem[] = [
    { label: 'Dashboard', route: '/dashboard', icon: 'dashboard' },
  ];
}
