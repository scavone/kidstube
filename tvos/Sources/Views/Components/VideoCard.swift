import SwiftUI

/// A thumbnail card displaying a video's poster, title, channel, and duration.
/// Used in both catalog grids and search results.
struct VideoCard: View {
    let title: String
    let channelName: String
    let thumbnailUrl: String?
    let duration: String
    let badge: String?
    /// When true, the card tracks focus itself (for standalone use).
    /// Set to false when the card is inside a Button to avoid stealing focus.
    let tracksFocus: Bool
    let progress: Double?
    let isWatched: Bool

    init(
        title: String,
        channelName: String,
        thumbnailUrl: String?,
        duration: String,
        badge: String? = nil,
        tracksFocus: Bool = true,
        progress: Double? = nil,
        isWatched: Bool = false
    ) {
        self.title = title
        self.channelName = channelName
        self.thumbnailUrl = thumbnailUrl
        self.duration = duration
        self.badge = badge
        self.tracksFocus = tracksFocus
        self.progress = progress
        self.isWatched = isWatched
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Thumbnail
            ZStack(alignment: .bottomTrailing) {
                thumbnailImage
                    .frame(height: 180)
                    .clipped()
                    .opacity(isWatched ? 0.7 : 1.0)

                // Progress bar at bottom
                if let progress, progress > 0 {
                    VStack {
                        Spacer()
                        GeometryReader { geo in
                            ZStack(alignment: .leading) {
                                Rectangle().fill(Color.gray.opacity(0.3)).frame(height: 3)
                                Rectangle()
                                    .fill(isWatched ? Color.green : Color.accentColor)
                                    .frame(width: geo.size.width * progress, height: 3)
                            }
                        }
                        .frame(height: 3)
                    }
                }

                // Watched checkmark badge
                if isWatched {
                    VStack {
                        HStack {
                            Spacer()
                            Image(systemName: "checkmark.circle.fill")
                                .font(.caption)
                                .foregroundColor(.white)
                                .shadow(radius: 2)
                                .padding(6)
                        }
                        Spacer()
                    }
                }

                if !duration.isEmpty {
                    Text(duration)
                        .font(.caption2)
                        .fontWeight(.semibold)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.black.opacity(0.75))
                        .cornerRadius(4)
                        .padding(6)
                }

                if let badge {
                    HStack {
                        Text(badge)
                            .font(.caption2)
                            .fontWeight(.bold)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(badgeColor(badge))
                            .cornerRadius(4)
                            .padding(6)
                        Spacer()
                    }
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 8))

            // Title
            Text(title)
                .font(.caption)
                .fontWeight(.medium)
                .lineLimit(2)
                .foregroundColor(.primary)

            // Channel
            Text(channelName)
                .font(.caption2)
                .foregroundColor(.secondary)
                .lineLimit(1)
        }
        .frame(width: 300)
        .modifier(FocusScaleModifier(tracksFocus: tracksFocus))
    }

    @ViewBuilder
    private var thumbnailImage: some View {
        if let urlString = thumbnailUrl, let url = URL(string: urlString) {
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let image):
                    image
                        .resizable()
                        .aspectRatio(16/9, contentMode: .fill)
                case .failure:
                    placeholderImage
                default:
                    placeholderImage
                        .overlay(ProgressView())
                }
            }
        } else {
            placeholderImage
        }
    }

    private var placeholderImage: some View {
        Rectangle()
            .fill(Color.gray.opacity(0.3))
            .aspectRatio(16/9, contentMode: .fill)
            .overlay(
                Image(systemName: "play.rectangle")
                    .font(.largeTitle)
                    .foregroundColor(.gray)
            )
    }

    private func badgeColor(_ text: String) -> Color {
        switch text.lowercased() {
        case "approved": return .green.opacity(0.85)
        case "pending": return .orange.opacity(0.85)
        case "denied": return .red.opacity(0.85)
        default: return .blue.opacity(0.85)
        }
    }
}

/// Conditionally applies focus tracking and scale effect.
/// When `tracksFocus` is false, the view is not focusable (avoids stealing
/// focus from a parent Button on tvOS).
/// When true, uses `.focusable()` so the card can receive tap and long-press
/// gestures directly on tvOS without a wrapping Button.
private struct FocusScaleModifier: ViewModifier {
    let tracksFocus: Bool
    @FocusState private var isFocused: Bool

    func body(content: Content) -> some View {
        if tracksFocus {
            content
                .focusable()
                .scaleEffect(isFocused ? 1.05 : 1.0)
                .animation(.easeInOut(duration: 0.15), value: isFocused)
                .focused($isFocused)
        } else {
            content
        }
    }
}
