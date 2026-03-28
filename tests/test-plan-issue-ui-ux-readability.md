# Test Plan: UI/UX Readability & Navigation Improvements

**Issue**: UI/UX overhaul — text contrast, timer badge visibility, overlay backgrounds, channel navigation
**Phase**: 1 (pre-change baseline + test plan) | Date: 2026-03-28
**QA**: qa-analyst

---

## Baseline: Current State (pre-changes)

Code review findings before frontend-dev makes changes:

### 1. Text Contrast — Current Issues
- **`textMuted` (white: 0.4)** on **background (white: 0.08)**: delta of 0.32, borderline for small text (WCAG AA needs ~4.5:1 for small text)
- **`CATEGORIES` label** in SidebarView uses `textMuted` at `.caption2` — very small, low contrast
- **Category subtitle** (time remaining) uses `textMuted` — small caption2, may be unreadable
- **Disabled items**: `textMuted` at 40% opacity → effective value ~0.16 on 0.08 bg, extremely low (intentional dim, but verify)
- **Unselected items**: `textSecondary` (white: 0.65) — adequate for callout/body size

### 2. Timer Badge — Current Issues
- **Normal state**: `Color.black.opacity(0.6)` background with white text — on dark sidebar (`sidebarBackground = white: 0.06`), badge blends in with minimal visual differentiation
- **Warning (≤10 min)**: `Color.orange.opacity(0.85)` — good contrast ✓
- **Exceeded**: `Color.red.opacity(0.85)` — good contrast ✓
- **Free day**: `Color.green.opacity(0.85)` — good contrast ✓

### 3. Overlay Backgrounds — Current Issues
Overlays **missing** explicit `AppTheme.background` coverage:
- `TimesUpView` — no background set
- `CategoryTimesUpView` — no background set
- `OutsideScheduleView` — no background set
- `DeniedView` — no background set
- `PendingView` — no background set

`CooldownView` ✓ correctly uses `AppTheme.background.ignoresSafeArea()`

### 4. Channel Navigation — Current Issues
- `HomeChannelItemView` (home screen row): focus shows scale×1.1 + accent ring only — **no "View Channel" label**
- `ChannelsListItemView` (channels grid): focus shows scale+glow+ring only — **no "View Channel" label**
- `ChannelCard` (search results): focus shows scale×1.05 only — **no "View Channel" label**
- None of the channel components navigate to `ChannelDetailView` from the home row
- `ChannelDetailView` exists and works; it is reachable from search results only currently

---

## Test Cases

### Area 1: Text Contrast — Filter States

| ID | Test | Expected | How to Verify |
|----|------|----------|---------------|
| TC-1.1 | Unselected sidebar item (e.g., "Home" not active) | Text at `textSecondary` (white: 0.65) is readable | Visual inspection; label clearly visible |
| TC-1.2 | Selected sidebar item | Text at `textPrimary` (white), icon at `accentColor` | Bold weight + white text + colored icon visible |
| TC-1.3 | Focused but unselected sidebar item | Background `sidebarSelectedBackground` fills row | Highlight background is visible without obscuring text |
| TC-1.4 | `CATEGORIES` section label | Readable `textMuted` at caption2 | Not required to meet full WCAG AA (muted intentional), but must be discernible against sidebar |
| TC-1.5 | Category subtitle (time remaining) | Readable `textMuted` at caption2 | E.g. "45 min left" must be legible against sidebar |
| TC-1.6 | Disabled category (time exhausted) | Dims to 40% opacity — clearly greyed out | Visually distinct from enabled, intentionally unreadable as affordance |
| TC-1.7 | AppTheme filter-state colors are sourced from AppTheme tokens | No hardcoded hex/RGBA values for selected/unselected states | Grep for hardcoded colors in SidebarView.swift |

### Area 2: Timer Badge — All States in Sidebar

| ID | Test | Expected | How to Verify |
|----|------|----------|---------------|
| TC-2.1 | Normal state (>10 min remaining) | Badge renders; text white; background distinguishable from sidebar | Check badge bg against `sidebarBackground` |
| TC-2.2 | Warning state (≤10 min) | Orange background (0.85 opacity), white text | Clearly visible |
| TC-2.3 | Exceeded state | Red background (0.85 opacity), "Time's up" text, `exclamationmark.circle` icon | High visibility |
| TC-2.4 | Free day state | Green background (0.85 opacity), `gift` icon | High visibility |
| TC-2.5 | Badge nil (no time limit) | Badge hidden — no empty placeholder renders | `timeStatus = nil` → `TimeBadge` renders nothing |
| TC-2.6 | Badge appears at sidebar bottom | Positioned below nav items with correct padding | Visual check: not clipped, not overlapping nav items |

### Area 3: Overlay Views — Opaque Backgrounds

| ID | Test | Expected | How to Verify |
|----|------|----------|---------------|
| TC-3.1 | `TimesUpView` presented | Solid opaque background (AppTheme.background or card) — content behind not visible | Navigate to time-exhausted state |
| TC-3.2 | `CategoryTimesUpView` presented | Solid background; all text/buttons readable | Navigate to category-exhausted state |
| TC-3.3 | `OutsideScheduleView` presented | Solid background; lock message readable | Simulate outside-schedule state |
| TC-3.4 | `DeniedView` presented | Solid opaque card/background; red icon, text readable | Deny a video request |
| TC-3.5 | `PendingView` presented | Solid background; polling animation visible; text readable | Request a non-pre-approved video |
| TC-3.6 | `CooldownView` presented | `AppTheme.background.ignoresSafeArea()` ✓ already correct | Verify unchanged (regression) |
| TC-3.7 | Overlay text colors use theme tokens (not hardcoded) | No `.secondary` / `.primary` / raw `Color(...)` bypassing theme | Code review of changed overlay files |

### Area 4: Channel Navigation — "View Channel" Label & Navigation

| ID | Test | Expected | How to Verify |
|----|------|----------|---------------|
| TC-4.1 | Focus a channel icon in home screen row | "View Channel" label appears (fade-in or overlay) | Navigate to Home, focus channel row |
| TC-4.2 | Focus a channel icon in channels grid | "View Channel" label appears on icon | Navigate to Channels section, focus an icon |
| TC-4.3 | Focus a `ChannelCard` in search results | "View Channel" label appears on focus | Search for a channel query, focus result |
| TC-4.4 | Select (click) a channel icon in home row | Navigates to `ChannelDetailView` for that channel | Verify channel name in detail view header matches |
| TC-4.5 | Select (click) a channel in channels grid | Navigates to `ChannelDetailView` | Same check |
| TC-4.6 | `ChannelDetailView` back button | Returns to previous screen (home/channels/search) | Press Back |
| TC-4.7 | `ChannelDetailView` loads channel videos | Videos grid populates; video count > 0 for active channel | Confirm `getChannelVideos` API call fires |
| TC-4.8 | Label only shows on focus (not always visible) | When unfocused, no "View Channel" text crowding the grid | Check unfocused state |

### Area 5: Regression — Existing Views

| ID | Test | Expected | How to Verify |
|----|------|----------|---------------|
| TC-5.1 | `VideoCard` renders correctly | Title/channel text visible, thumbnail loads, duration badge visible | Check in home/category/search views |
| TC-5.2 | `VideoCard` approved/pending/denied badges | Badge colors (green/orange/red) unchanged | Visual or code check |
| TC-5.3 | `FeaturedBannerView` — text over image | White title + channel name + "Watch Now" button visible over gradient | Home screen banner loads with an active channel |
| TC-5.4 | `FeaturedBannerView` — placeholder | Correct placeholder shown when no channel | Simulate no channels |
| TC-5.5 | `SidebarView` focus behavior | Items focus correctly; `.focusSection()` works; no dead zones | Navigate all sidebar items |
| TC-5.6 | `SidebarSearchView` renders correctly | Search input, results grid, channel cards all visible | Navigate to Search section |
| TC-5.7 | `AppTheme` tokens unchanged for unmodified views | Existing surface/card/border colors unchanged | Verify constants in AppTheme.swift |

### Area 6: Hardcoded Colors Audit

| ID | Test | Expected | How to Verify |
|----|------|----------|---------------|
| TC-6.1 | Grep for raw `Color(white:` outside AppTheme.swift | Only AppTheme.swift should define white-channel colors for backgrounds | `grep -r "Color(white:" tvos/Sources/Views/` |
| TC-6.2 | Grep for `.foregroundColor(.secondary)` in changed overlay files | Overlay views should use AppTheme tokens; `.secondary` is system-adaptive and may not have sufficient contrast | Check changed files |
| TC-6.3 | Grep for `.foregroundColor(.primary)` in changed files | Same as above | Check changed files |
| TC-6.4 | `VideoCard` color usage | `.primary`/`.secondary` acceptable in VideoCard (component-level adaptive — intentional) | Confirm no regressions |

---

## Automated Tests

### swift test (133 tests must pass)

```
cd tvos && swift test
```

Test coverage for this feature area:
- `UIOverhaulTests.swift` — existing AppTheme/SidebarSection/RecentlyAdded coverage
- New tests to add (Phase 2, if needed): `TimeBadge` state logic, `AppTheme` color token consistency

### AppTheme Token Verification (add to UIOverhaulTests.swift if needed)

```swift
// Verify contrast delta between text and background tokens
// textSecondary(0.65) - background(0.08) = 0.57 delta — acceptable
// textMuted(0.4) - background(0.08) = 0.32 delta — borderline, verify in context
```

---

## Phase 2 Checklist (after frontend-dev confirms done)

- [ ] Read all changed files listed by frontend-dev
- [ ] Confirm overlay views have opaque backgrounds
- [ ] Confirm "View Channel" label added with correct focus behavior
- [ ] Confirm AppTheme tokens not bypassed in changed files
- [ ] Run `cd tvos && swift test` — all 133 must pass
- [ ] Check for accessibility: focus states visible (no invisible focus rings)
- [ ] Check for regressions: VideoCard, FeaturedBanner, SidebarView unchanged
- [ ] Write final report to `tests/report-issue-ui-ux-readability.md`

---

## Risk Areas

1. **Overlay backgrounds**: `TimesUpView`/`DeniedView`/`PendingView` currently lack opaque backgrounds — fix must not break the views' internal layout
2. **"View Channel" focus overlay**: if implemented via `.overlay()`, verify it doesn't clip or extend outside the card bounds on tvOS focus ring
3. **Normal TimeBadge on dark sidebar**: `Color.black.opacity(0.6)` on `Color(white: 0.06)` sidebar is near-identical — if not fixed, badge is invisible
4. **`textMuted` at caption2**: borderline contrast; verify the fix raises this or uses a lighter token for captions
