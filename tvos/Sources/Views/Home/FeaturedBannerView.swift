import SwiftUI

/// Large hero banner at the top of the home screen showing the latest video
/// from the currently focused channel. Tapping the banner plays the video.
/// Uses the channel's `banner_url` as background, falling back to the video thumbnail.
struct FeaturedBannerView: View {
    let channel: HomeChannel?
    let onPlay: (HomeChannelVideo) -> Void

    @FocusState private var isFocused: Bool

    var body: some View {
        if let channel, let video = channel.latestVideo {
            Button {
                onPlay(video)
            } label: {
                bannerContent(channel: channel, video: video)
            }
            .buttonStyle(.plain)
            .focused($isFocused)
            .scaleEffect(isFocused ? 1.02 : 1.0)
            .animation(.easeInOut(duration: 0.2), value: isFocused)
        } else {
            bannerPlaceholder
        }
    }

    private func bannerContent(channel: HomeChannel, video: HomeChannelVideo) -> some View {
        ZStack(alignment: .bottomLeading) {
            // Background: prefer video thumbnail for relevance, fall back to channel banner
            asyncImage(url: video.thumbnailUrl ?? channel.bannerUrl)
                .frame(maxWidth: .infinity)
                .frame(height: 400)
                .clipped()

            // Gradient overlay for text readability
            LinearGradient(
                colors: [.clear, .clear, .black.opacity(0.85)],
                startPoint: .top,
                endPoint: .bottom
            )

            // Text overlay
            VStack(alignment: .leading, spacing: 8) {
                Spacer()

                Text(video.title)
                    .font(.title2)
                    .fontWeight(.bold)
                    .foregroundColor(.white)
                    .lineLimit(2)
                    .shadow(radius: 4)

                HStack(spacing: 12) {
                    // Channel avatar + name
                    HStack(spacing: 8) {
                        channelAvatar(url: channel.thumbnailUrl, size: 28)
                        Text(channel.channelName)
                            .font(.subheadline)
                            .foregroundColor(.white.opacity(0.9))
                    }

                    if !video.formattedDuration.isEmpty {
                        Text(video.formattedDuration)
                            .font(.caption)
                            .fontWeight(.medium)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(Color.white.opacity(0.2))
                            .cornerRadius(4)
                            .foregroundColor(.white.opacity(0.9))
                    }

                    Spacer()

                    HStack(spacing: 6) {
                        Image(systemName: "play.fill")
                        Text("Watch Now")
                    }
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .foregroundColor(.white)
                    .padding(.horizontal, 20)
                    .padding(.vertical, 8)
                    .background(Color.accentColor.opacity(isFocused ? 1.0 : 0.7))
                    .cornerRadius(8)
                }
            }
            .padding(40)
        }
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .shadow(color: .black.opacity(0.3), radius: 10, y: 5)
        .padding(.horizontal, 60)
    }

    @ViewBuilder
    private func asyncImage(url: String?) -> some View {
        if let urlString = url, let url = URL(string: urlString) {
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let image):
                    image
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                case .failure:
                    bannerPlaceholderBackground
                default:
                    bannerPlaceholderBackground
                        .overlay(ProgressView())
                }
            }
        } else {
            bannerPlaceholderBackground
        }
    }

    @ViewBuilder
    private func channelAvatar(url: String?, size: CGFloat) -> some View {
        if let urlString = url, let url = URL(string: urlString) {
            AsyncImage(url: url) { phase in
                if case .success(let image) = phase {
                    image
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                        .frame(width: size, height: size)
                        .clipShape(Circle())
                } else {
                    Circle()
                        .fill(Color.white.opacity(0.3))
                        .frame(width: size, height: size)
                }
            }
        } else {
            Circle()
                .fill(Color.white.opacity(0.3))
                .frame(width: size, height: size)
        }
    }

    private var bannerPlaceholder: some View {
        RoundedRectangle(cornerRadius: 16)
            .fill(Color.gray.opacity(0.15))
            .frame(height: 400)
            .overlay(
                VStack(spacing: 12) {
                    Image(systemName: "tv")
                        .font(.system(size: 48))
                        .foregroundColor(.secondary)
                    Text("No channels yet")
                        .font(.headline)
                        .foregroundColor(.secondary)
                    Text("Search for videos and ask a parent to approve channels!")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
            )
            .padding(.horizontal, 60)
    }

    private var bannerPlaceholderBackground: some View {
        Rectangle()
            .fill(
                LinearGradient(
                    colors: [Color.gray.opacity(0.3), Color.gray.opacity(0.15)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .overlay(
                Image(systemName: "play.rectangle.fill")
                    .font(.system(size: 60))
                    .foregroundColor(.gray.opacity(0.4))
            )
    }
}
