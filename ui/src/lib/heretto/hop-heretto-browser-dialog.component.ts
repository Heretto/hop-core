import {
  ChangeDetectionStrategy, ChangeDetectorRef, Component, DestroyRef, ElementRef, OnInit, ViewChild, inject,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MAT_DIALOG_DATA, MatDialog, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { Observable, Subscription, catchError, of, debounceTime, distinctUntilChanged, switchMap, tap, throwError } from 'rxjs';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { HerettoConnection } from '../agents/hop-agent.service';
import {
  HerettoFailure, HerettoFile, HerettoFileKind, HerettoFolderListing, HerettoFolderRef, HerettoRepository,
  HerettoSearchResult, HopHerettoService, herettoFailure,
} from './hop-heretto.service';
import { HerettoBrowserRow, HopHerettoEntryListComponent } from './hop-heretto-entry-list.component';
import { HopHerettoFileDetailsComponent } from './hop-heretto-file-details.component';

export interface HopHerettoBrowserDialogData {
  /** Defaults to "Select a Heretto file". */
  title?: string;
  /** One line under the title saying what the file is for, e.g. "Choose the map to publish". */
  purpose?: string;
  /** The kinds that can be chosen; others show but are greyed out. Omit for any file. */
  accept?: HerettoFileKind[] | null;
  /** Browse through this connection only. Otherwise every connection is offered. */
  credentialId?: string | null;
  /** Open at this file's folder, with the file selected. */
  fileId?: string | null;
  /** Open at this folder. */
  folderId?: string | null;
  /** The choose button's label. Defaults to "Select file". */
  selectLabel?: string;
  /** Where the app's Credentials page is, linked when Heretto rejects a connection. `null` hides the link. */
  credentialsLink?: string | null;
}

/** Opens the Heretto file browser; emits the chosen file, or undefined if none was. */
export function openHerettoFileBrowser(
  dialog: MatDialog, data: HopHerettoBrowserDialogData = {},
): Observable<HerettoFile | undefined> {
  return dialog.open<HopHerettoBrowserDialogComponent, HopHerettoBrowserDialogData, HerettoFile>(
    HopHerettoBrowserDialogComponent,
    { data, width: '1040px', maxWidth: 'calc(100vw - 32px)', autoFocus: '.find-input' },
  ).afterClosed();
}

const PLURAL_KINDS: Record<HerettoFileKind, string> = {
  map: 'DITA maps', topic: 'DITA topics', image: 'images', other: 'other files',
};
const STORAGE_KEY = 'hop-heretto-browser';
const MIN_DEEP_QUERY = 2;

/** Browse and search a Heretto repository by folder and file name, and choose a file. */
@Component({
  changeDetection: ChangeDetectionStrategy.Eager,
  selector: 'hop-heretto-browser-dialog',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, RouterLink, MatDialogModule, MatButtonModule, MatCheckboxModule,
    MatFormFieldModule, MatIconModule, MatInputModule, MatSelectModule,
    HopHerettoEntryListComponent, HopHerettoFileDetailsComponent,
  ],
  template: `
    <div class="head">
      <div>
        <h2 id="hop-heretto-browser-title">{{ data.title || 'Select a Heretto file' }}</h2>
        <p *ngIf="data.purpose">{{ data.purpose }}</p>
      </div>
      <button mat-icon-button type="button" aria-label="Close" (click)="ref.close()"><mat-icon>close</mat-icon></button>
    </div>

    <p class="notice" *ngIf="noConnections">
      <mat-icon>info</mat-icon>
      <span>No Heretto connection is set up.
        <a *ngIf="credentialsLink" [routerLink]="credentialsLink" (click)="ref.close()">Add one under Credentials</a>
        <ng-container *ngIf="!credentialsLink">Add one under Credentials</ng-container>
        to browse Heretto.</span>
    </p>

    <div class="bar" *ngIf="!noConnections">
      <mat-form-field class="conn" *ngIf="connections.length > 1 && !data.credentialId" subscriptSizing="dynamic">
        <mat-label>Connection</mat-label>
        <mat-select [value]="credentialId" (selectionChange)="useConnection($event.value)">
          <mat-option *ngFor="let c of connections" [value]="c.id">{{ c.name }} · {{ host(c) }}</mat-option>
        </mat-select>
      </mat-form-field>
      <mat-form-field class="repo" *ngIf="repositories.length > 1" subscriptSizing="dynamic">
        <mat-label>Repository</mat-label>
        <mat-select [value]="repoKey" (selectionChange)="useRepository($event.value)">
          <mat-option *ngFor="let r of repositories" [value]="key(r)">{{ r.repository }} · {{ r.branch }}</mat-option>
        </mat-select>
      </mat-form-field>
      <mat-form-field class="find" subscriptSizing="dynamic">
        <mat-label>Find by name</mat-label>
        <mat-icon matPrefix>search</mat-icon>
        <input matInput class="find-input" [formControl]="findControl"
               [placeholder]="deep ? 'Search this folder and subfolders' : 'Filter this folder'">
        <button matSuffix mat-icon-button type="button" *ngIf="findControl.value" aria-label="Clear"
                (click)="findControl.setValue('')"><mat-icon>close</mat-icon></button>
      </mat-form-field>
      <mat-checkbox [checked]="deep" (change)="setDeep($event.checked)">Include subfolders</mat-checkbox>
    </div>

    <div class="path" *ngIf="!noConnections">
      <button mat-stroked-button type="button" class="up" aria-label="Up one folder"
              [disabled]="crumbs.length < 2 || loading" (click)="openCrumb(crumbs.length - 2)">
        <mat-icon>arrow_upward</mat-icon>
      </button>
      <ng-container *ngIf="!editing">
        <nav aria-label="Folder path">
          <ng-container *ngFor="let c of crumbs; let i = index; let last = last">
            <span class="sep" *ngIf="i > 0" aria-hidden="true">/</span>
            <span *ngIf="last" class="here" aria-current="location">{{ crumbLabel(c, i) }}</span>
            <button *ngIf="!last" type="button" class="crumb" (click)="openCrumb(i)">{{ crumbLabel(c, i) }}</button>
          </ng-container>
        </nav>
        <button mat-icon-button type="button" aria-label="Type or paste a folder path" title="Type or paste a folder path"
                [disabled]="!repoKey" (click)="startEdit()"><mat-icon>edit</mat-icon></button>
      </ng-container>
      <div class="edit" *ngIf="editing">
        <mat-form-field subscriptSizing="dynamic">
          <input matInput #pathInput aria-label="Folder path" [formControl]="pathControl" spellcheck="false"
                 (keydown.enter)="goPath(); $event.preventDefault()"
                 (keydown.escape)="cancelEdit(); $event.stopPropagation()">
          <mat-hint *ngIf="!pathControl.errors">
            Paste a folder path, like /guides/install or {{ repoPath }}/documents/guides/install. Press Enter to go.
          </mat-hint>
          <mat-error>{{ pathControl.errors?.['heretto'] }}</mat-error>
        </mat-form-field>
        <button mat-flat-button color="primary" type="button" [disabled]="resolvingPath" (click)="goPath()">Go</button>
        <button mat-stroked-button type="button" (click)="cancelEdit()">Cancel</button>
      </div>
      <span class="accept" *ngIf="acceptNote && !editing">{{ acceptNote }}</span>
    </div>

    <div class="body" *ngIf="!noConnections">
      <hop-heretto-entry-list class="list"
          [rows]="rows" [loading]="loading || searching" [loadingLabel]="searching ? 'Searching' : 'Loading folder'"
          [error]="error || searchError" [errorTitle]="error ? 'Couldn\\'t open this folder.' : 'Couldn\\'t search this folder.'"
          [credentialsLink]="credentialsLink" [selectedId]="selected?.id ?? null"
          [emptyIcon]="query ? 'search_off' : 'folder_open'" [emptyTitle]="emptyTitle" [emptyHint]="emptyHint"
          (open)="openRow($event)" (pick)="pick($event)" (choose)="pick($event, true)"
          (retry)="retry()" (leave)="ref.close()"></hop-heretto-entry-list>
      <hop-heretto-file-details class="details" [file]="details" [loading]="detailsLoading"
          [error]="detailsError"></hop-heretto-file-details>
    </div>

    <div class="foot">
      <span class="status" [class.warn]="searchResult?.truncated">{{ footerLabel }}</span>
      <button mat-stroked-button type="button" (click)="ref.close()">Cancel</button>
      <button mat-flat-button color="primary" type="button" [disabled]="!canChoose" (click)="chooseSelected()">
        {{ data.selectLabel || 'Select file' }}
      </button>
    </div>
  `,
  styles: [`
    :host { display: flex; flex-direction: column; height: min(680px, calc(100vh - 48px)); overflow: hidden; }
    .head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 20px 16px 0 24px; }
    .head h2 { margin: 0; font-size: 20px; }
    .head p { margin: 4px 0 0; }
    .notice { display: flex; gap: 8px; margin: 24px; color: var(--text-secondary); }
    .bar { display: flex; flex-wrap: wrap; align-items: center; gap: 0 12px; padding: 4px 24px 12px; }
    .conn { flex: 0 1 260px; }
    .repo { flex: 0 1 200px; }
    .find { flex: 1 1 260px; }
    .find mat-icon[matPrefix] { margin: 0 4px 0 10px; color: var(--text-tertiary); }
    mat-checkbox { margin-top: 12px; }
    .path { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; min-height: 40px; padding: 0 24px 12px; }
    .up { min-width: 36px; width: 36px; padding: 0; margin-right: 6px; }
    .up mat-icon { margin: 0; }
    nav { display: flex; align-items: center; flex-wrap: wrap; gap: 2px; min-width: 0; }
    .sep { color: var(--text-disabled); padding: 0 2px; }
    .here { padding: 6px 8px; font-weight: 600; }
    .crumb { padding: 6px 8px; border: 0; border-radius: 6px; background: transparent; font: inherit; color: var(--text-link); cursor: pointer; }
    .crumb:hover { background: var(--hover-overlay); color: var(--text-link-hover); }
    .edit { flex: 1 1 420px; display: flex; align-items: flex-start; gap: 8px; min-width: 0; }
    .edit mat-form-field { flex: 1; min-width: 0; margin-top: 0; }
    .edit input { font-family: var(--font-mono); font-size: 13px; }
    .edit button { margin-top: 4px; }
    .accept {
      margin-left: auto; padding: 3px 10px; border-radius: 9999px; font-size: 12px; font-weight: 500;
      background: var(--color-primary-bg); color: var(--color-primary-text);
    }
    .body { flex: 1; min-height: 0; display: flex; border-top: 1px solid var(--border-default); }
    .list { flex: 1 1 auto; min-width: 0; overflow-y: auto; }
    .details { flex: 0 0 300px; }
    .foot { display: flex; align-items: center; gap: 12px; padding: 14px 24px; border-top: 1px solid var(--border-default); }
    .status { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-secondary); }
    .status.warn { color: var(--color-warning-text); }
    @media (max-width: 768px) {
      .head, .bar, .path, .foot { padding-left: 16px; padding-right: 16px; }
      .body { flex-direction: column; }
      .details { flex: 0 0 auto; max-height: 40%; border-left: 0; border-top: 1px solid var(--border-default); }
      .status { display: none; }
    }
  `],
})
export class HopHerettoBrowserDialogComponent implements OnInit {
  readonly data: HopHerettoBrowserDialogData = inject(MAT_DIALOG_DATA, { optional: true }) ?? {};
  readonly ref = inject(MatDialogRef<HopHerettoBrowserDialogComponent, HerettoFile>);
  private heretto = inject(HopHerettoService);
  private cdr = inject(ChangeDetectorRef);
  private destroyRef = inject(DestroyRef);

  @ViewChild('pathInput') pathInput?: ElementRef<HTMLInputElement>;

  readonly credentialsLink = this.data.credentialsLink === undefined ? '/credentials' : this.data.credentialsLink;
  readonly findControl = new FormControl('', { nonNullable: true });
  readonly pathControl = new FormControl('', { nonNullable: true });

  connections: HerettoConnection[] = [];
  noConnections = false;
  credentialId: string | null = null;
  repositories: HerettoRepository[] = [];
  repoKey: string | null = null;

  folder: HerettoFolderListing | null = null;
  crumbs: HerettoFolderRef[] = [];
  loading = true;
  error: HerettoFailure | null = null;

  deep = false;
  query = '';
  searching = false;
  searchResult: HerettoSearchResult | null = null;
  searchError: HerettoFailure | null = null;

  editing = false;
  resolvingPath = false;

  rows: HerettoBrowserRow[] = [];
  selected: { id: string; name: string } | null = null;
  details: HerettoFile | null = null;
  detailsLoading = false;
  detailsError = '';

  private navigation?: Subscription;
  private searchSub?: Subscription;
  private detailsSub?: Subscription;
  private retryAction: () => void = () => undefined;
  private chooseWhenLoaded = false;

  ngOnInit(): void {
    this.findControl.valueChanges.pipe(
      debounceTime(300), distinctUntilChanged(), takeUntilDestroyed(this.destroyRef),
    ).subscribe(value => this.setQuery(value));

    this.heretto.connections().subscribe({
      next: connections => {
        this.connections = connections;
        const wanted = this.data.credentialId ?? this.remembered().credentialId;
        const id = connections.find(c => c.id === wanted)?.id ?? this.data.credentialId ?? connections[0]?.id;
        if (!id) {
          this.noConnections = true;
          this.cdr.markForCheck();
          return;
        }
        this.useConnection(id, { fileId: this.data.fileId, folderId: this.data.folderId });
      },
      error: error => this.fail(error, () => this.ngOnInit()),
    });
  }

  // ── where we are ────────────────────────────────────────────────────────

  useConnection(id: string, start: { fileId?: string | null; folderId?: string | null } = {}): void {
    this.credentialId = id;
    this.repositories = [];
    this.repoKey = null;
    this.crumbs = [];
    this.clearSelection();
    const listing$ = this.heretto.repositories(id).pipe(
      tap(repositories => this.repositories = repositories),
      switchMap(repositories => this.startListing(id, repositories, start)),
    );
    this.show(listing$, undefined, true);
  }

  useRepository(key: string): void {
    const repo = this.repositories.find(r => this.key(r) === key);
    if (!repo || !this.credentialId) return;
    this.clearSelection();
    this.show(this.heretto.openRepository(this.credentialId, repo.branch, repo.repository));
  }

  private startListing(
    id: string, repositories: HerettoRepository[], start: { fileId?: string | null; folderId?: string | null },
  ): Observable<HerettoFolderListing> {
    if (start.fileId) {
      return this.heretto.file(id, start.fileId).pipe(
        tap(file => this.showDetails(file)),
        switchMap(file => file.folder_id
          ? this.heretto.openFolder(id, file.folder_id, true)
          : this.defaultRepository(id, repositories)),
        catchError(() => this.defaultRepository(id, repositories)),
      );
    }
    if (start.folderId) return this.heretto.openFolder(id, start.folderId, true);
    const saved = this.remembered().folders?.[id];
    if (saved) {
      return this.heretto.openFolder(id, saved, true).pipe(
        catchError(() => this.defaultRepository(id, repositories)),
      );
    }
    return this.defaultRepository(id, repositories);
  }

  private defaultRepository(id: string, repositories: HerettoRepository[]): Observable<HerettoFolderListing> {
    const repo = repositories.find(r => r.branch === 'master') ?? repositories[0];
    if (!repo) {
      return throwError(() => ({
        error: { detail: { message: "This connection's account can't see any repositories.", reason: 'error' } },
      }));
    }
    return this.heretto.openRepository(id, repo.branch, repo.repository);
  }

  openRow(row: HerettoBrowserRow): void {
    if (!this.credentialId) return;
    this.clearSelection();
    if (row.pathLabel !== undefined) {
      // A search result: its trail isn't known yet, so fetch it.
      this.show(this.heretto.openFolder(this.credentialId, row.entry.id, true));
    } else {
      this.show(this.heretto.openFolder(this.credentialId, row.entry.id),
        [...this.crumbs, { id: row.entry.id, name: row.entry.name }]);
    }
  }

  openCrumb(index: number): void {
    const crumb = this.crumbs[index];
    if (!crumb || !this.credentialId) return;
    this.clearSelection();
    this.show(this.heretto.openFolder(this.credentialId, crumb.id), this.crumbs.slice(0, index + 1));
  }

  retry(): void {
    this.retryAction();
  }

  /** Loads a folder; `crumbs` is its trail when we stepped there, else the listing's ancestors are used. */
  private show(listing$: Observable<HerettoFolderListing>, crumbs?: HerettoFolderRef[], keepSelection = false): void {
    this.navigation?.unsubscribe();
    this.searchSub?.unsubscribe();
    this.loading = true;
    this.error = null;
    this.searchResult = null;
    this.searchError = null;
    this.searching = false;
    this.retryAction = () => this.show(listing$, crumbs, keepSelection);
    this.refreshRows();
    this.navigation = listing$.subscribe({
      next: listing => {
        this.folder = listing;
        this.loading = false;
        const here = { id: listing.id, name: listing.name };
        this.crumbs = listing.ancestors ? [...listing.ancestors, here] : crumbs ?? [here];
        if (listing.branch && listing.repository) {
          const repo = { branch: listing.branch, repository: listing.repository };
          if (!this.repositories.some(r => this.key(r) === this.key(repo))) this.repositories = [...this.repositories, repo];
          this.repoKey = this.key(repo);
        }
        this.remember(listing.id);
        if (this.findControl.value) this.findControl.setValue('', { emitEvent: false });
        this.query = '';
        if (!keepSelection) this.clearSelection();
        this.refreshRows();
        this.cdr.markForCheck();
      },
      error: error => this.fail(error, () => this.show(listing$, crumbs, keepSelection)),
    });
  }

  private fail(error: unknown, retry: () => void): void {
    this.loading = false;
    this.error = herettoFailure(error);
    this.retryAction = retry;
    this.refreshRows();
    this.cdr.markForCheck();
  }

  // ── typed paths ─────────────────────────────────────────────────────────

  startEdit(): void {
    this.editing = true;
    this.pathControl.setValue('/' + this.crumbs.slice(1).map(c => c.name).join('/'));
    this.cdr.markForCheck();
    setTimeout(() => this.pathInput?.nativeElement.select());
  }

  cancelEdit(): void {
    this.editing = false;
    this.pathControl.setErrors(null);
    this.cdr.markForCheck();
  }

  goPath(): void {
    const repo = this.repositories.find(r => this.key(r) === this.repoKey);
    if (!repo || !this.credentialId || this.resolvingPath) return;
    this.resolvingPath = true;
    this.heretto.resolveFolder(this.credentialId, repo, this.pathControl.value).subscribe({
      next: listing => {
        this.resolvingPath = false;
        this.editing = false;
        this.clearSelection();
        this.show(of(listing));
      },
      error: error => {
        this.resolvingPath = false;
        this.pathControl.setErrors({ heretto: herettoFailure(error).message });
        this.pathControl.markAsTouched();
        this.cdr.markForCheck();
      },
    });
  }

  // ── finding ─────────────────────────────────────────────────────────────

  setDeep(deep: boolean): void {
    this.deep = deep;
    this.setQuery(this.findControl.value, true);
  }

  private setQuery(value: string, force = false): void {
    const query = value.trim();
    if (query === this.query && !force) return;
    this.query = query;
    this.searchSub?.unsubscribe();
    this.searchResult = null;
    this.searchError = null;
    this.searching = false;
    if (query && this.deep && query.length >= MIN_DEEP_QUERY && this.folder && this.credentialId) {
      this.searching = true;
      this.searchSub = this.heretto.search(this.credentialId, this.folder.id, query).subscribe({
        next: result => {
          this.searching = false;
          this.searchResult = result;
          this.refreshRows();
          this.cdr.markForCheck();
        },
        error: error => {
          this.searching = false;
          this.searchError = herettoFailure(error);
          this.retryAction = () => this.setQuery(this.findControl.value, true);
          this.refreshRows();
          this.cdr.markForCheck();
        },
      });
    }
    this.refreshRows();
    this.cdr.markForCheck();
  }

  private refreshRows(): void {
    const accept = this.data.accept;
    const blocked = (kind: string) => kind !== 'folder' && !!accept?.length && !accept.includes(kind as HerettoFileKind);
    if (this.searchResult) {
      const base = this.currentPath();
      this.rows = this.searchResult.matches.map(match => ({
        entry: match,
        pathLabel: match.folder_path === '/' ? base : (base === '/' ? '' : base) + match.folder_path,
        disabled: blocked(match.kind),
      }));
    } else if (this.deep && this.query) {
      this.rows = [];
    } else {
      const needle = this.query.toLowerCase();
      this.rows = (this.folder?.entries ?? [])
        .filter(e => !needle || e.name.toLowerCase().includes(needle))
        .map(entry => ({ entry, disabled: blocked(entry.kind) }));
    }
  }

  // ── choosing ────────────────────────────────────────────────────────────

  pick(row: HerettoBrowserRow, choose = false): void {
    if (row.disabled || !this.credentialId) return;
    if (this.selected?.id === row.entry.id && (this.detailsLoading || this.details?.id === row.entry.id)) {
      // Already selected (a double-click's first click): choose once the details are in.
      if (choose && this.details) this.chooseSelected();
      else this.chooseWhenLoaded = this.chooseWhenLoaded || choose;
      return;
    }
    this.chooseWhenLoaded = choose;
    this.selected = { id: row.entry.id, name: row.entry.name };
    this.details = null;
    this.detailsError = '';
    this.detailsLoading = true;
    this.detailsSub?.unsubscribe();
    this.detailsSub = this.heretto.file(this.credentialId, row.entry.id).subscribe({
      next: file => {
        this.showDetails(file);
        if (this.chooseWhenLoaded) this.chooseSelected();
      },
      error: error => {
        this.detailsLoading = false;
        this.detailsError = herettoFailure(error).message;
        this.cdr.markForCheck();
      },
    });
    this.cdr.markForCheck();
  }

  private showDetails(file: HerettoFile): void {
    this.selected = { id: file.id, name: file.name };
    this.details = file;
    this.detailsLoading = false;
    this.detailsError = '';
    this.cdr.markForCheck();
  }

  private clearSelection(): void {
    this.detailsSub?.unsubscribe();
    this.selected = null;
    this.details = null;
    this.detailsLoading = false;
    this.detailsError = '';
  }

  get canChoose(): boolean {
    const file = this.details;
    return !!file && file.id === this.selected?.id && this.accepts(file.kind);
  }

  chooseSelected(): void {
    if (this.canChoose) this.ref.close(this.details!);
  }

  private accepts(kind: HerettoFileKind): boolean {
    const accept = this.data.accept;
    return !accept?.length || accept.includes(kind);
  }

  // ── labels ──────────────────────────────────────────────────────────────

  get acceptNote(): string {
    const accept = this.data.accept;
    if (!accept?.length) return '';
    const names = accept.map(kind => PLURAL_KINDS[kind]);
    const list = names.length === 1 ? names[0] : names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1];
    return `Only ${list} can be chosen`;
  }

  get emptyTitle(): string {
    if (this.deep && this.query && this.query.length < MIN_DEEP_QUERY) return 'Keep typing';
    return this.query ? `No names contain “${this.query}”` : 'This folder is empty';
  }

  get emptyHint(): string {
    if (this.deep && this.query && this.query.length < MIN_DEEP_QUERY) {
      return `Enter at least ${MIN_DEEP_QUERY} characters to search subfolders.`;
    }
    if (!this.query) return this.crumbs.length > 1 ? 'Go up a level to keep browsing.' : '';
    if (!this.deep) return 'Try Include subfolders to look deeper.';
    return this.searchResult?.truncated
      ? 'The search stopped before covering every subfolder. Open a subfolder to search deeper.'
      : 'Nothing in this folder or its subfolders matches.';
  }

  get footerLabel(): string {
    const chosen = this.selected ? `Selected: ${this.selected.name}` : 'Nothing selected';
    const result = this.searchResult;
    if (!result) return chosen;
    const matches = `${result.matches.length} ${result.matches.length === 1 ? 'match' : 'matches'}`;
    const folders = `${result.folders_searched} ${result.folders_searched === 1 ? 'folder' : 'folders'}`;
    const stopped = result.truncated ? ' (stopped early; open a subfolder to search deeper)' : '';
    return `${matches} for “${result.query}” in ${folders}${stopped} · ${chosen}`;
  }

  crumbLabel(crumb: HerettoFolderRef, index: number): string {
    if (index === 0 && crumb.name === 'documents' && this.folder?.repository) return this.folder.repository;
    return crumb.name;
  }

  get repoPath(): string {
    return this.repoKey ?? 'master/product';
  }

  host(connection: HerettoConnection): string {
    try {
      return new URL(connection.server_url).host;
    } catch {
      return connection.server_url;
    }
  }

  key(repo: HerettoRepository): string {
    return `${repo.branch}/${repo.repository}`;
  }

  private currentPath(): string {
    return '/' + this.crumbs.slice(1).map(c => c.name).join('/');
  }

  // ── remembering the last folder, per connection ─────────────────────────

  private remembered(): { credentialId?: string; folders?: Record<string, string> } {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') ?? {};
    } catch {
      return {};
    }
  }

  private remember(folderId: string): void {
    if (!this.credentialId) return;
    try {
      const saved = this.remembered();
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        credentialId: this.credentialId,
        folders: { ...(saved.folders ?? {}), [this.credentialId]: folderId },
      }));
    } catch {
      // Storage unavailable: the browser just starts at the repository next time.
    }
  }
}
