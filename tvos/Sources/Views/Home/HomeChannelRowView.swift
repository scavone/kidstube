import SwiftUI

/// Horizontal scrollable row of approved channels with circular avatars.
/// Focusing a channel updates the featured banner above.
struct HomeChannelRowView: View {
    let channels: [HomeChannel]
    let focusedChannelId: String?
    let onFocusChanged: (String) -> Void
    let onChannelSelected: (HomeChannel) -> Void

    var body: some View {
        if channels.isEmpty {
            EmptyView()
        } else {
            VStack(alignment: .leading, spacing: 12) {
                Text("Channels")
                    .font(.headline)
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 60)

                ScrollView(.horizontal, showsIndicators: false) {
                    LazyHStack(spacing: 24) {
                        ForEach(channels) { channel in
                            HomeChannelItemView(
                                channel: channel,
                                isHighlighted: channel.id == focusedChannelId,
                                onFocused: {
                                    onFocusChanged(channel.id)
                                },
                                onSelected: {
                                    onChannelSelected(channel)
                                }
                            )
                        }
                    }
                    .padding(.horizontal, 60)
                    .padding(.vertical, 8)
                }
            }
            .focusSection()
        }
    }
}

/// A single channel item in the channel row — circular avatar + name.
struct HomeChannelItemView: View {
    let channel: HomeChannel
    let isHighlighted: Bool
    let onFocused: () -> Void
    let onSelected: () -> Void

    @FocusState private var isFocused: Bool

    var body: some View {
        Button(action: onSelected) {
            VStack(spacing: 10) {
                channelAvatar
                    .frame(width: 100, height: 100)
                    .clipShape(Circle())
                    .overlay(
                        Circle()
                            .stroke(
                                isFocused ? Color.white : Color.clear,
                                lineWidth: 3
                            )
                    )

                VStack(spacing: 2) {
                    Text(channel.channelName)
                        .font(.caption)
                        .fontWeight(.semibold)
                        .foregroundColor(.white)
                        .lineLimit(2)
                        .multilineTextAlignment(.center)
                        .frame(width: 110)

                    Text("View Channel ›")
                        .font(.caption2)
                        .foregroundColor(AppTheme.textSecondary)
                        .opacity(isFocused ? 1.0 : 0.0)
                        .animation(.easeInOut(duration: 0.15), value: isFocused)
                }
            }
        }
        .buttonStyle(.plain)
        .focused($isFocused)
        .scaleEffect(isFocused ? 1.15 : 1.0)
        .animation(.easeInOut(duration: 0.15), value: isFocused)
        .onChange(of: isFocused) {
            if isFocused {
                onFocused()
            }
        }
    }

    @ViewBuilder
    private var channelAvatar: some View {
        if let urlString = channel.thumbnailUrl, let url = URL(string: urlString) {
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
                        .overlay(ProgressView().scaleEffect(0.6))
                }
            }
        } else {
            avatarPlaceholder
        }
    }

    private var avatarPlaceholder: some View {
        Circle()
            .fill(Color.gray.opacity(0.25))
            .overlay(
                Text(String(channel.channelName.prefix(1)).uppercased())
                    .font(.title2)
                    .fontWeight(.bold)
                    .foregroundColor(.secondary)
            )
    }
}
