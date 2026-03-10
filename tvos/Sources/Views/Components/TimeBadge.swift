import SwiftUI

/// Displays the remaining watch time as a badge.
/// Used in the top-right corner of the home screen and as a player overlay.
struct TimeBadge: View {
    let timeStatus: TimeStatus?
    var style: BadgeStyle = .compact

    enum BadgeStyle {
        case compact   // Small badge for home screen corner
        case overlay   // Larger, semi-transparent overlay for player
    }

    var body: some View {
        if let status = timeStatus {
            HStack(spacing: 6) {
                Image(systemName: iconName(status))
                    .font(style == .compact ? .caption : .body)

                Text(status.exceeded ? "Time's up" : status.formattedRemaining)
                    .font(style == .compact ? .caption : .body)
                    .fontWeight(.semibold)
            }
            .padding(.horizontal, style == .compact ? 10 : 16)
            .padding(.vertical, style == .compact ? 6 : 10)
            .background(backgroundColor(status))
            .cornerRadius(style == .compact ? 8 : 12)
        }
    }

    private func iconName(_ status: TimeStatus) -> String {
        if status.exceeded { return "exclamationmark.circle" }
        if status.isFreeDay { return "gift" }
        return "clock"
    }

    private func backgroundColor(_ status: TimeStatus) -> Color {
        if status.exceeded {
            return Color.red.opacity(0.85)
        } else if status.isFreeDay {
            return Color.green.opacity(0.85)
        } else if status.remainingMin <= 10 {
            return Color.orange.opacity(0.85)
        } else {
            return Color.black.opacity(0.6)
        }
    }
}
