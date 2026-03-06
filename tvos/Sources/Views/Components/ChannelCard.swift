import SwiftUI

/// A card displaying a channel's avatar, name, and subscriber count.
/// Used in search results to distinguish channels from videos.
struct ChannelCard: View {
    let name: String
    let thumbnailUrl: String?
    let subscriberCount: String

    @FocusState private var isFocused: Bool

    var body: some View {
        VStack(spacing: 12) {
            // Channel avatar (circular)
            channelAvatar
                .frame(width: 120, height: 120)
                .clipShape(Circle())

            // Channel name
            Text(name)
                .font(.caption)
                .fontWeight(.semibold)
                .lineLimit(2)
                .multilineTextAlignment(.center)
                .foregroundColor(.primary)

            // Subscriber count
            if !subscriberCount.isEmpty {
                Text(subscriberCount)
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
        }
        .frame(width: 300, height: 230)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color.gray.opacity(0.15))
        )
        .scaleEffect(isFocused ? 1.05 : 1.0)
        .animation(.easeInOut(duration: 0.15), value: isFocused)
        .focused($isFocused)
    }

    @ViewBuilder
    private var channelAvatar: some View {
        if let urlString = thumbnailUrl, let url = URL(string: urlString) {
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let image):
                    image
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                case .failure:
                    avatarPlaceholder
                default:
                    avatarPlaceholder
                        .overlay(ProgressView())
                }
            }
        } else {
            avatarPlaceholder
        }
    }

    private var avatarPlaceholder: some View {
        Circle()
            .fill(Color.gray.opacity(0.3))
            .overlay(
                Image(systemName: "person.circle")
                    .font(.system(size: 40))
                    .foregroundColor(.gray)
            )
    }
}
