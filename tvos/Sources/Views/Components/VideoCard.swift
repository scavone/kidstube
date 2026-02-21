import SwiftUI

/// A thumbnail card displaying a video's poster, title, channel, and duration.
/// Used in both catalog grids and search results.
struct VideoCard: View {
    let title: String
    let channelName: String
    let thumbnailUrl: String?
    let duration: String
    let badge: String?

    @FocusState private var isFocused: Bool

    init(
        title: String,
        channelName: String,
        thumbnailUrl: String?,
        duration: String,
        badge: String? = nil
    ) {
        self.title = title
        self.channelName = channelName
        self.thumbnailUrl = thumbnailUrl
        self.duration = duration
        self.badge = badge
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Thumbnail
            ZStack(alignment: .bottomTrailing) {
                thumbnailImage
                    .frame(height: 180)
                    .clipped()
                    .cornerRadius(8)

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
        .scaleEffect(isFocused ? 1.05 : 1.0)
        .animation(.easeInOut(duration: 0.15), value: isFocused)
        .focused($isFocused)
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
