import SwiftUI

/// Displays a channel's videos with the same action buttons as search results.
/// Users can watch approved videos, request access, or go back to search.
struct ChannelDetailView: View {
    let channel: ChannelSearchResult
    let child: ChildProfile
    let onWatch: (String) -> Void
    let onRequest: (SearchResult) -> Void
    let onBack: () -> Void

    @StateObject private var viewModel = ChannelDetailViewModel()
    @State private var infoItem: VideoInfoItem?

    // Adaptive grid lets the focus engine route up/down/left/right between
    // items without the per-row .focusSection() barriers that prevented the
    // sidebar from being reachable from the videos area.
    private let columns = [
        GridItem(.adaptive(minimum: 280, maximum: 320), spacing: 30)
    ]

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Button(action: onBack) {
                    Label("Back", systemImage: "chevron.left")
                        .font(.caption)
                }
                .buttonStyle(.plain)

                Spacer()

                channelHeader

                Spacer()
            }
            .padding(.horizontal, 60)
            .padding(.vertical, 16)

            // Videos
            ScrollView {
                if viewModel.isLoading {
                    ProgressView()
                        .scaleEffect(1.5)
                        .padding(60)
                } else if viewModel.videos.isEmpty {
                    noVideos
                } else {
                    LazyVGrid(columns: columns, spacing: 30) {
                        ForEach(viewModel.videos) { video in
                            videoCard(video)
                        }
                    }
                    .padding(.horizontal, 60)
                    .padding(.bottom, 40)
                }

                if let error = viewModel.errorMessage {
                    Text(error)
                        .foregroundColor(.red)
                        .font(.caption)
                        .padding()
                }
            }
        }
        .task {
            await viewModel.loadVideos(channelId: channel.channelId, childId: child.id)
        }
        .sheet(item: $infoItem) { item in
            VideoInfoSheet(videoId: item.id, childId: item.childId)
        }
    }

    private var channelHeader: some View {
        HStack(spacing: 12) {
            if let urlString = channel.thumbnailUrl, let url = URL(string: urlString) {
                AsyncImage(url: url) { phase in
                    if case .success(let image) = phase {
                        image
                            .resizable()
                            .aspectRatio(contentMode: .fill)
                            .frame(width: 40, height: 40)
                            .clipShape(Circle())
                    } else {
                        Circle()
                            .fill(Color.gray.opacity(0.3))
                            .frame(width: 40, height: 40)
                    }
                }
            }

            VStack(alignment: .leading, spacing: 2) {
                Text(channel.name)
                    .font(.headline)
                if !channel.formattedSubscriberCount.isEmpty {
                    Text(channel.formattedSubscriberCount)
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }
        }
    }

    @ViewBuilder
    private func videoCard(_ video: SearchResult) -> some View {
        VStack(spacing: 8) {
            VideoCard(
                title: video.title,
                channelName: video.channelName,
                thumbnailUrl: video.thumbnailUrl,
                thumbnailUrls: video.thumbnailUrls ?? [],
                duration: video.formattedDuration,
                badge: statusBadge(video)
            )
            .contextMenu {
                Button {
                    infoItem = VideoInfoItem(id: video.videoId, childId: child.id)
                } label: {
                    Label("Video Info", systemImage: "info.circle")
                }
            }

            actionButton(video)
        }
    }

    @ViewBuilder
    private func actionButton(_ video: SearchResult) -> some View {
        if video.isApproved {
            Button {
                onWatch(video.videoId)
            } label: {
                Label("Watch", systemImage: "play.fill")
                    .font(.caption)
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .tint(.green)
        } else if video.isPending {
            Button {} label: {
                Label("Pending...", systemImage: "clock")
                    .font(.caption)
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .disabled(true)
        } else {
            Button {
                viewModel.markAsPending(videoId: video.videoId)
                onRequest(video)
            } label: {
                Label("Request", systemImage: "hand.raised")
                    .font(.caption)
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
        }
    }

    private func statusBadge(_ video: SearchResult) -> String? {
        switch video.accessStatus {
        case "approved": return "Approved"
        case "pending": return "Pending"
        case "denied": return "Denied"
        default: return nil
        }
    }

    private var noVideos: some View {
        VStack(spacing: 16) {
            Image(systemName: "play.rectangle")
                .font(.system(size: 48))
                .foregroundColor(.secondary)
            Text("No videos found")
                .font(.headline)
                .foregroundColor(.secondary)
            Text("This channel doesn't have any videos yet")
                .font(.callout)
                .foregroundColor(.secondary)
        }
        .padding(60)
    }
}

// MARK: - ViewModel

@MainActor
final class ChannelDetailViewModel: ObservableObject {
    @Published var videos: [SearchResult] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    private let apiClient: APIClient

    init(apiClient: APIClient = APIClient()) {
        self.apiClient = apiClient
    }

    func loadVideos(channelId: String, childId: Int) async {
        isLoading = true
        errorMessage = nil
        do {
            videos = try await apiClient.getChannelVideos(channelId: channelId, childId: childId)
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    func markAsPending(videoId: String) {
        guard let index = videos.firstIndex(where: { $0.videoId == videoId }) else { return }
        videos[index].accessStatus = "pending"
    }
}
