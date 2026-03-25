import SwiftUI

/// Sidebar sections for the main navigation.
enum SidebarSection: Hashable {
    case home
    case channels
    case category(String)
    case search
    case profile
}

/// Plex-style sidebar navigation rail for the main app layout.
struct SidebarView: View {
    @Binding var selection: SidebarSection
    let child: ChildProfile
    let timeStatus: TimeStatus?
    let categoryTimeStatus: CategoryTimeStatusResponse?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Child header
            childHeader
                .padding(.bottom, 24)

            // Navigation items
            VStack(alignment: .leading, spacing: 4) {
                sidebarItem(
                    icon: "house.fill",
                    label: "Home",
                    section: .home
                )

                sidebarItem(
                    icon: "rectangle.stack.person.crop",
                    label: "Channels",
                    section: .channels
                )

                Divider()
                    .background(AppTheme.border)
                    .padding(.vertical, 8)

                // Category items
                Text("CATEGORIES")
                    .font(.caption2)
                    .fontWeight(.semibold)
                    .foregroundColor(AppTheme.textMuted)
                    .padding(.horizontal, 20)
                    .padding(.bottom, 4)

                categorySidebarItem(
                    icon: "graduationcap.fill",
                    label: "Educational",
                    category: "edu"
                )

                categorySidebarItem(
                    icon: "gamecontroller.fill",
                    label: "Entertainment",
                    category: "fun"
                )

                Divider()
                    .background(AppTheme.border)
                    .padding(.vertical, 8)

                sidebarItem(
                    icon: "magnifyingglass",
                    label: "Search",
                    section: .search
                )

                sidebarItem(
                    icon: "person.circle",
                    label: "Profile",
                    section: .profile
                )
            }

            Spacer()

            // Time remaining at bottom
            if let time = timeStatus {
                TimeBadge(timeStatus: time, style: .compact)
                    .padding(.horizontal, 20)
                    .padding(.bottom, 16)
            }
        }
        .padding(.top, 40)
        .frame(maxHeight: .infinity)
        .background(AppTheme.sidebarBackground)
        .focusSection()
    }

    // MARK: - Child Header

    private var childHeader: some View {
        HStack(spacing: 12) {
            childAvatar
                .frame(width: 44, height: 44)
                .clipShape(Circle())

            VStack(alignment: .leading, spacing: 2) {
                Text(child.name)
                    .font(.headline)
                    .foregroundColor(AppTheme.textPrimary)
                    .lineLimit(1)
                Text(Config.appName)
                    .font(.caption2)
                    .foregroundColor(AppTheme.textMuted)
            }

            Spacer()
        }
        .padding(.horizontal, 20)
    }

    @ViewBuilder
    private var childAvatar: some View {
        if let url = child.avatarURL {
            AsyncImage(url: url) { phase in
                if case .success(let image) = phase {
                    image.resizable().scaledToFill()
                } else {
                    Text(child.avatar).font(.title3)
                }
            }
        } else {
            Text(child.avatar).font(.title3)
        }
    }

    // MARK: - Sidebar Item

    private func sidebarItem(
        icon: String,
        label: String,
        section: SidebarSection,
        accentColor: Color = .accentColor
    ) -> some View {
        SidebarItemView(
            icon: icon,
            label: label,
            subtitle: nil,
            isSelected: selection == section,
            isDisabled: false,
            accentColor: accentColor,
            action: { selection = section }
        )
    }

    // MARK: - Category Sidebar Item

    /// Builds a category item with optional time-remaining subtitle and exhaustion dimming.
    private func categorySidebarItem(icon: String, label: String, category: String) -> some View {
        let isUncapped = categoryTimeStatus?.uncappedCategories.contains(category) ?? true
        let timeInfo = categoryTimeStatus?.categories[category]
        let isExhausted = !isUncapped && (timeInfo?.exhausted == true)
        let subtitle = categorySubtitle(timeInfo: timeInfo, isUncapped: isUncapped)

        return SidebarItemView(
            icon: icon,
            label: label,
            subtitle: subtitle,
            isSelected: selection == .category(category),
            isDisabled: isExhausted,
            accentColor: AppTheme.categoryColor(category),
            action: { if !isExhausted { selection = .category(category) } }
        )
    }

    private func categorySubtitle(timeInfo: CategoryTimeInfo?, isUncapped: Bool) -> String? {
        guard !isUncapped, let info = timeInfo else { return nil }
        if info.exhausted {
            return "0 min left"
        }
        if info.bonusMinutes > 0 {
            return "\(info.formattedRemaining)  +\(info.bonusMinutes) bonus"
        }
        return info.formattedRemaining
    }
}

/// A single focusable row in the sidebar.
struct SidebarItemView: View {
    let icon: String
    let label: String
    let subtitle: String?
    let isSelected: Bool
    let isDisabled: Bool
    let accentColor: Color
    let action: () -> Void

    @FocusState private var isFocused: Bool

    var body: some View {
        Button(action: action) {
            HStack(spacing: 14) {
                Image(systemName: icon)
                    .font(.body)
                    .foregroundColor(iconColor)
                    .frame(width: 24)

                VStack(alignment: .leading, spacing: 2) {
                    Text(label)
                        .font(.callout)
                        .fontWeight(isSelected ? .semibold : .regular)
                        .foregroundColor(labelColor)
                        .lineLimit(1)

                    if let sub = subtitle {
                        Text(sub)
                            .font(.caption2)
                            .foregroundColor(subtitleColor)
                            .lineLimit(1)
                    }
                }

                Spacer()
            }
            .padding(.horizontal, 20)
            .frame(minHeight: 52)
            .padding(.vertical, subtitle != nil ? 6 : 0)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(isFocused || isSelected ? AppTheme.sidebarSelectedBackground : Color.clear)
                    .padding(.horizontal, 8)
            )
            .clipShape(Rectangle())
        }
        .buttonStyle(.plain)
        .focused($isFocused)
        .opacity(isDisabled ? 0.4 : 1.0)
        .allowsHitTesting(!isDisabled)
    }

    private var iconColor: Color {
        if isDisabled { return AppTheme.textMuted }
        return isSelected ? accentColor : AppTheme.textSecondary
    }

    private var labelColor: Color {
        if isDisabled { return AppTheme.textMuted }
        return isSelected ? AppTheme.textPrimary : AppTheme.textSecondary
    }

    private var subtitleColor: Color {
        if isDisabled { return AppTheme.textMuted }
        return AppTheme.textMuted
    }
}
