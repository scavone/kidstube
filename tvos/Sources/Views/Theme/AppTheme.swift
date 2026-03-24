import SwiftUI

/// Centralized design tokens for the KidsTube tvOS app.
/// Dark theme with category accent colors and consistent typography.
enum AppTheme {

    // MARK: - Category Colors

    /// Accent color for a content category. Falls back to teal for unknown categories.
    static func categoryColor(_ category: String?) -> Color {
        switch category?.lowercased() {
        case "edu", "educational": return .blue
        case "fun", "entertainment": return .green
        case "music":               return .purple
        case "science":             return .orange
        case "art", "creative":     return .pink
        default:                    return .teal
        }
    }

    // MARK: - Surface Colors

    /// Main background — near-black.
    static let background = Color(white: 0.08)

    /// Elevated surface (cards, sidebar).
    static let surface = Color(white: 0.12)

    /// Slightly brighter surface for hover/focus states.
    static let surfaceHighlight = Color(white: 0.18)

    /// Divider / border.
    static let border = Color(white: 0.2)

    // MARK: - Text Colors

    static let textPrimary = Color.white
    static let textSecondary = Color(white: 0.65)
    static let textMuted = Color(white: 0.4)

    // MARK: - Sidebar

    static let sidebarWidth: CGFloat = 340
    static let sidebarBackground = Color(white: 0.06)
    static let sidebarSelectedBackground = Color.white.opacity(0.12)

    // MARK: - Cards

    static let cardCornerRadius: CGFloat = 12
    static let cardShadowRadius: CGFloat = 8
    static let cardFocusScale: CGFloat = 1.05
    static let cardFocusGlowColor = Color.white.opacity(0.25)

    // MARK: - Typography Helpers

    /// Section header style (e.g. "Recently Added", "Channels").
    static func sectionHeader(_ text: String) -> some View {
        Text(text)
            .font(.title3)
            .fontWeight(.bold)
            .foregroundColor(textPrimary)
    }

    /// Subtle section subheader.
    static func sectionSubheader(_ text: String) -> some View {
        Text(text)
            .font(.subheadline)
            .foregroundColor(textSecondary)
    }

    // MARK: - Skeleton Loading

    /// Shimmering placeholder color for skeleton loaders.
    static let skeletonBase = Color(white: 0.15)
    static let skeletonHighlight = Color(white: 0.22)
}

// MARK: - Skeleton Loader

/// Animated placeholder view that shimmers while content loads.
/// Use in place of ProgressView for a polished loading state.
struct SkeletonLoader: View {
    var width: CGFloat? = nil
    var height: CGFloat = 180
    var cornerRadius: CGFloat = AppTheme.cardCornerRadius

    @State private var shimmerOffset: CGFloat = -1.0

    var body: some View {
        RoundedRectangle(cornerRadius: cornerRadius)
            .fill(AppTheme.skeletonBase)
            .overlay(
                GeometryReader { geo in
                    LinearGradient(
                        colors: [.clear, AppTheme.skeletonHighlight, .clear],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                    .frame(width: geo.size.width * 0.4)
                    .offset(x: shimmerOffset * geo.size.width)
                }
                .mask(RoundedRectangle(cornerRadius: cornerRadius))
            )
            .frame(width: width, height: height)
            .onAppear {
                withAnimation(
                    .linear(duration: 1.5)
                    .repeatForever(autoreverses: false)
                ) {
                    shimmerOffset = 1.5
                }
            }
    }
}

/// A skeleton placeholder shaped like a video card.
struct VideoCardSkeleton: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            SkeletonLoader(height: 180)
            SkeletonLoader(height: 14, cornerRadius: 4)
                .frame(width: 200)
            SkeletonLoader(height: 12, cornerRadius: 4)
                .frame(width: 120)
        }
        .frame(width: 300)
    }
}
