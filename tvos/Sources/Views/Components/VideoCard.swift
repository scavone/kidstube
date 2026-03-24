import SwiftUI

/// A thumbnail card displaying a video's poster, title, channel, and duration.
/// When focused and `thumbnailUrls` is non-empty, cycles through thumbnails every 1.5 s
/// with a crossfade animation. Falls back to single `thumbnailUrl` when no extras are provided.
struct VideoCard: View {
    let title: String
    let channelName: String
    let thumbnailUrl: String?
    let thumbnailUrls: [String]
    let duration: String
    let badge: String?
    let tracksFocus: Bool
    let progress: Double?
    let isWatched: Bool

    @State private var currentThumbIndex: Int = 0

    init(
        title: String,
        channelName: String,
        thumbnailUrl: String?,
        thumbnailUrls: [String] = [],
        duration: String,
        badge: String? = nil,
        tracksFocus: Bool = true,
        progress: Double? = nil,
        isWatched: Bool = false
    ) {
        self.title = title
        self.channelName = channelName
        self.thumbnailUrl = thumbnailUrl
        self.thumbnailUrls = thumbnailUrls
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
                thumbnailImageView
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
        .modifier(FocusCycleModifier(
            tracksFocus: tracksFocus,
            thumbnailUrls: thumbnailUrls,
            currentThumbIndex: $currentThumbIndex
        ))
    }

    /// Shows the cycling thumbnail when extras are available, otherwise the primary thumbnail.
    @ViewBuilder
    private var thumbnailImageView: some View {
        if !thumbnailUrls.isEmpty {
            let idx = min(currentThumbIndex, thumbnailUrls.count - 1)
            let urlString = thumbnailUrls[idx]
            if let url = URL(string: urlString) {
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
                    }
                }
                .id(urlString)
                .transition(.opacity)
            } else {
                placeholderImage
            }
        } else {
            thumbnailImage
        }
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

/// Handles focus tracking, scale animation, and thumbnail cycling for VideoCard.
/// Cycles every 1.5 s with a crossfade while focused; stops on focus loss.
/// Preloads all cycle images via URLSession when the card first receives focus.
private struct FocusCycleModifier: ViewModifier {
    let tracksFocus: Bool
    let thumbnailUrls: [String]
    @Binding var currentThumbIndex: Int

    @FocusState private var isFocused: Bool
    @State private var cycleTask: Task<Void, Never>?

    func body(content: Content) -> some View {
        if tracksFocus {
            content
                .focusable()
                .focused($isFocused)
                .scaleEffect(isFocused ? 1.05 : 1.0)
                .animation(.easeInOut(duration: 0.15), value: isFocused)
                .onChange(of: isFocused) {
                    if isFocused && !thumbnailUrls.isEmpty {
                        currentThumbIndex = 0
                        preloadImages()
                        startCycling()
                    } else {
                        cycleTask?.cancel()
                        cycleTask = nil
                    }
                }
                .onDisappear {
                    cycleTask?.cancel()
                    cycleTask = nil
                }
        } else {
            content
        }
    }

    private func startCycling() {
        cycleTask?.cancel()
        cycleTask = Task { @MainActor in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 1_500_000_000)
                guard !Task.isCancelled else { break }
                withAnimation(.easeInOut(duration: 0.4)) {
                    currentThumbIndex = (currentThumbIndex + 1) % thumbnailUrls.count
                }
            }
        }
    }

    private func preloadImages() {
        for urlString in thumbnailUrls {
            guard let url = URL(string: urlString) else { continue }
            URLSession.shared.dataTask(with: url) { _, _, _ in }.resume()
        }
    }
}
