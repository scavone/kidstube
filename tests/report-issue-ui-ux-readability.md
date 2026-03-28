# QA Report: UI/UX Readability & Navigation

**Date**: 2026-03-28
**QA**: qa-analyst
**Test plan**: `tests/test-plan-issue-ui-ux-readability.md`
**Files reviewed**: 9 changed Swift files (initial) + 2 follow-up files
**Tests run**: `swift test` — 133/133 passed ✅

---

## Overall Verdict: PASS with minor observations

All primary requirements are met. No blocking issues. Three minor maintenance concerns and one cleanup item from follow-up noted below.

---

## Test Results by Area

### Area 1: AppTheme Token Changes

| TC | Test | Result | Notes |
|----|------|--------|-------|
| TC-1.1 | Unselected filter text (`textSecondary`) | ✅ PASS | 0.78 (was 0.65) — 0.70 delta above background |
| TC-1.2 | Selected filter text (`.white` + accentColor) | ✅ PASS | Explicit `.foregroundColor(.white)` + `accentColor.opacity(0.5)` bg |
| TC-1.3 | `textMuted` for captions | ✅ PASS | 0.55 (was 0.40) — improved legibility for category subtitles |
| TC-1.4 | Disabled items | ✅ PASS | Still 0.4 opacity on `textMuted` — intentional affordance, acceptable |
| TC-1.7 | No hardcoded colors for selected/unselected states in SidebarView | ✅ PASS | SidebarView correctly uses `AppTheme.textPrimary`, `textSecondary`, `textMuted` |

**AppTheme.swift delta**: `textSecondary` 0.65 → 0.78, `textMuted` 0.40 → 0.55. All other tokens unchanged.

---

### Area 2: Filter Buttons (CategoryFilter, SortPicker, WatchStatusFilter)

| TC | Test | Result | Notes |
|----|------|--------|-------|
| TC-2.1 | Selected state: white text, tinted background | ✅ PASS | `.white` + `accentColor.opacity(0.5)` |
| TC-2.2 | Unselected state: secondary text, surface background | ✅ PASS | `AppTheme.textSecondary` + `Color(white: 0.18)` |
| TC-2.3 | Count labels on WatchStatusFilter | ✅ PASS | Selected: `Color.white.opacity(0.75)`, unselected: `AppTheme.textMuted` |
| TC-2.4 | Channel filter pill | ✅ PASS | `accentColor.opacity(0.3)` bg, clear affordance with x button |

⚠️ **Minor observation**: `Color(white: 0.18)` used directly in all three filter views instead of `AppTheme.surfaceHighlight` (same value). No visual impact now, but if `surfaceHighlight` changes in the future, filters won't track it. Not a bug.

---

### Area 3: Timer Badge — All States

| TC | Test | Result | Notes |
|----|------|--------|-------|
| TC-3.1 | Normal state (>10 min) | ✅ PASS | `Color(white: 0.20)` bg + `Color(white: 0.3)` border + shadow. Clearly distinct from `sidebarBackground (0.06)` |
| TC-3.2 | Warning state (≤10 min) | ✅ PASS | `Color.orange.opacity(0.85)` — unchanged, good |
| TC-3.3 | Exceeded state | ✅ PASS | `Color.red.opacity(0.85)` — unchanged, good |
| TC-3.4 | Free day state | ✅ PASS | `Color.green.opacity(0.85)` — unchanged, good |
| TC-3.5 | Explicit foreground color | ✅ PASS | Both icon and text now have explicit `.foregroundColor(.white)` |
| TC-3.6 | Font size upgrade | ✅ PASS | `.callout` (was `.caption`) — more legible |
| TC-3.7 | Digit stability | ✅ PASS | `.monospacedDigit()` prevents layout jitter as time counts down |
| TC-3.8 | Shadow | ✅ PASS | `shadow(color: .black.opacity(0.5), radius: 4, y: 2)` |
| TC-3.9 | Border only on normal state | ✅ PASS | `borderColor()` returns `.clear` for colored states (red/orange/green) — correct |

---

### Area 4: Overlay Backgrounds

| TC | Test | Result | Notes |
|----|------|--------|-------|
| TC-4.1 | ContentView blur layer | ✅ PASS | `blur(radius: 12)` (was 5) — strong blur when overlay is active |
| TC-4.2 | ContentView dim layer | ✅ PASS | `Color.black.opacity(0.85)` between blurred content and overlay card |
| TC-4.3 | `TimesUpView` card | ✅ PASS | `Color(white: 0.12).opacity(0.95)`, cornerRadius 24, maxWidth 800, shadow |
| TC-4.4 | `CategoryTimesUpView` card | ✅ PASS | Same card treatment |
| TC-4.5 | `OutsideScheduleView` card | ✅ PASS | Same card treatment |
| TC-4.6 | `DeniedView` card | ✅ PASS | Same card treatment |
| TC-4.7 | `PendingView` card | ✅ PASS | Same card treatment |
| TC-4.8 | `CooldownView` card | ✅ PASS | Card treatment. Removed old `AppTheme.background.ignoresSafeArea()`. Correctly relies on ContentView dim layer |
| TC-4.9 | Overlay text colors | ✅ PASS | Titles: `.foregroundColor(.white)`. Secondary: `.foregroundColor(Color(white: 0.78))` |

**Architecture note on CooldownView**: Old version used `ZStack { AppTheme.background.ignoresSafeArea() ... }` — a full-screen view. New version is a floating card, consistent with all other overlays. `ContentView` provides the dim + blur context. ✅

⚠️ **Minor observation**: All overlay views use `Color(white: 0.78)` hardcoded for secondary text instead of `AppTheme.textSecondary`. Values match now (0.78 = updated `textSecondary`), but these files won't track future token changes. Affects: `TimesUpView`, `CategoryTimesUpView`, `OutsideScheduleView`, `DeniedView`, `PendingView`, `CooldownView`.

⚠️ **Minor observation**: `CooldownView` countdown number `Text(formatCountdown(secondsRemaining))` has no explicit foreground color. All other text in the file has explicit colors; this one relies on system default (should be white on dark background, but inconsistent).

---

### Area 5: Channel Navigation (initial + follow-up)

| TC | Test | Result | Notes |
|----|------|--------|-------|
| TC-5.1 | "View Channel ›" label on `HomeChannelItemView` focus | ✅ PASS | Fades in/out with `.easeInOut(0.15)` animation on `isFocused` |
| TC-5.2 | White focus ring on `HomeChannelItemView` | ✅ PASS | `Color.white` stroke (was `Color.accentColor`) |
| TC-5.3 | Scale on focus | ✅ PASS | 1.15 (was 1.1) — more pronounced feedback |
| TC-5.4 | "View Channel ›" uses AppTheme token | ✅ PASS | `AppTheme.textSecondary` (not hardcoded) |
| TC-5.5 | Clicking channel in home row → navigates to `ChannelDetailView` | ✅ PASS | `onChannelBrowse` → `browsingChannel = ChannelSearchResult(...)` → `ChannelDetailView` renders |
| TC-5.6 | Conversion `HomeChannel` → `ChannelSearchResult` matches ChannelsListView pattern | ✅ PASS | `channelId: homeChannel.channelId ?? homeChannel.channelName` — identical to existing ChannelsListView handler |
| TC-5.7 | Focus/banner behavior decoupled from click | ✅ PASS | `onFocusChanged` still updates featured banner; click is independent |
| TC-5.8 | Back button from ChannelDetailView | ✅ PASS | `browsingChannel = nil` returns to HomeView with state intact |
| TC-5.9 | `ChannelsListItemView` navigation unchanged | ✅ PASS | Still navigates to `ChannelDetailView` via same pattern |

⚠️ **Cleanup observation**: `HomeViewModel.selectedChannelFilter`, `channelFilterPill` view, and `getCatalog(channel:)` parameter are now unreachable dead code. Previously the only way to set `selectedChannelFilter` was the home channel row click; that path now calls `onChannelBrowse` instead. No functional impact — the filter pill simply never appears. Safe to remove in a future cleanup.

---

### Area 6: Regressions

| TC | Test | Result | Notes |
|----|------|--------|-------|
| TC-6.1 | `VideoCard` unchanged | ✅ PASS | Not modified |
| TC-6.2 | `FeaturedBannerView` unchanged | ✅ PASS | Not modified |
| TC-6.3 | `SidebarView` unchanged | ✅ PASS | Benefits from textSecondary/textMuted token bumps |
| TC-6.4 | `ChannelsListView` / `ChannelDetailView` unchanged | ✅ PASS | Channel navigation still works |
| TC-6.5 | `SidebarSearchView` unchanged | ✅ PASS | Not modified |
| TC-6.6 | AppTheme structural tokens unchanged | ✅ PASS | `surface`, `surfaceHighlight`, `border`, `background`, card constants unchanged |

---

### Automated Tests

```
swift test → 133/133 PASSED ✅  (verified twice — initial review and follow-up)
```

---

## Summary of Findings

| Severity | Count | Items |
|----------|-------|-------|
| Blocking | 0 | — |
| Minor (maintenance) | 2 | `Color(white: 0.18)` in filters; `Color(white: 0.78)` in overlays — bypass theme tokens |
| Minor (code consistency) | 1 | Cooldown countdown number missing explicit foreground color |
| Cleanup (non-blocking) | 1 | `selectedChannelFilter` / `channelFilterPill` is now dead code in `HomeViewModel` |

---

## Recommendations

1. **Low priority**: Replace `Color(white: 0.18)` in filter buttons with `AppTheme.surfaceHighlight`. Replace `Color(white: 0.78)` in overlay views with `AppTheme.textSecondary`. Both are one-line changes per occurrence and reduce future maintenance risk.

2. **Low priority**: Add explicit `.foregroundColor(AppTheme.textPrimary)` to the countdown number in `CooldownView` for consistency.

3. **Low priority**: Remove `selectedChannelFilter`, `channelFilterPill`, and the `channel:` parameter in `loadCatalog` from `HomeViewModel` — all unreachable after the navigation fix.

---

## Acceptance

All 5 tasks addressed in this change are complete and correct:
- ✅ **Task 1** (Text contrast): AppTheme tokens raised; filter views use correct contrast ratios
- ✅ **Task 2** (Timer badge): Normal state now visually distinct; all states readable
- ✅ **Task 3** (Overlay backgrounds): All 6 overlay views have card treatment; ContentView adds dim + blur
- ✅ **Task 4** (Channel navigation): "View Channel ›" label with focus animation; clicking navigates to `ChannelDetailView`
- ✅ **Follow-up** (Navigation fix): Home row channel click now navigates to `ChannelDetailView`, not catalog filter
- ✅ **Tests**: 133/133 passing
