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

                sidebarItem(
                    icon: "graduationcap.fill",
                    label: "Educational",
                    section: .category("edu"),
                    accentColor: AppTheme.categoryColor("edu")
                )

                sidebarItem(
                    icon: "gamecontroller.fill",
                    label: "Entertainment",
                    section: .category("fun"),
                    accentColor: AppTheme.categoryColor("fun")
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
            isSelected: selection == section,
            accentColor: accentColor,
            action: { selection = section }
        )
    }
}

/// A single focusable row in the sidebar.
struct SidebarItemView: View {
    let icon: String
    let label: String
    let isSelected: Bool
    let accentColor: Color
    let action: () -> Void

    @FocusState private var isFocused: Bool

    var body: some View {
        Button(action: action) {
            HStack(spacing: 14) {
                Image(systemName: icon)
                    .font(.body)
                    .foregroundColor(isSelected ? accentColor : AppTheme.textSecondary)
                    .frame(width: 24)

                Text(label)
                    .font(.callout)
                    .fontWeight(isSelected ? .semibold : .regular)
                    .foregroundColor(isSelected ? AppTheme.textPrimary : AppTheme.textSecondary)
                    .lineLimit(1)

                Spacer()
            }
            .padding(.horizontal, 20)
            .frame(height: 52)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(isFocused || isSelected ? AppTheme.sidebarSelectedBackground : Color.clear)
                    .padding(.horizontal, 8)
            )
            .clipShape(Rectangle())
        }
        .buttonStyle(.plain)
        .focused($isFocused)
    }
}
