import SwiftUI

/// Identifiable wrapper for presenting a VideoInfoSheet via `.sheet(item:)`.
struct VideoInfoItem: Identifiable {
    let id: String   // videoId
    let childId: Int
}

/// A sheet that shows full video metadata including description.
/// Presented from a context menu on a video card.
struct VideoInfoSheet: View {
    let videoId: String
    let childId: Int
    var onWatchStatusChanged: ((String, String) -> Void)?

    @StateObject private var viewModel = VideoInfoSheetViewModel()
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Group {
                if viewModel.isLoading {
                    ProgressView()
                        .scaleEffect(1.5)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if let video = viewModel.video {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 20) {
                            // Thumbnail
                            thumbnailView(video)

                            // Title
                            Text(video.title)
                                .font(.title3)
                                .fontWeight(.bold)

                            // Channel + Duration
                            HStack(spacing: 16) {
                                Label(video.channelName, systemImage: "person.circle")
                                    .font(.subheadline)
                                    .foregroundColor(.secondary)

                                if !video.formattedDuration.isEmpty {
                                    Label(video.formattedDuration, systemImage: "clock")
                                        .font(.subheadline)
                                        .foregroundColor(.secondary)
                                }
                            }

                            // Description
                            if let description = video.description, !description.isEmpty {
                                Divider()
                                Text(description)
                                    .font(.body)
                                    .foregroundColor(.secondary)
                            } else if !viewModel.isLoading {
                                Text("No description available.")
                                    .font(.body)
                                    .foregroundColor(.secondary)
                                    .italic()
                            }

                            // Watch status toggle
                            if onWatchStatusChanged != nil {
                                Divider()
                                Button {
                                    viewModel.toggleWatchStatus(childId: childId)
                                    let newStatus = video.isWatched ? "unwatched" : "watched"
                                    onWatchStatusChanged?(video.videoId, newStatus)
                                } label: {
                                    if video.isWatched {
                                        Label("Mark as Unwatched", systemImage: "arrow.counterclockwise")
                                    } else {
                                        Label("Mark as Watched", systemImage: "checkmark.circle")
                                    }
                                }
                                .buttonStyle(.bordered)
                            }
                        }
                        .padding(40)
                    }
                } else if let error = viewModel.errorMessage {
                    VStack(spacing: 12) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.system(size: 48))
                            .foregroundColor(.secondary)
                        Text(error)
                            .foregroundColor(.secondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .task {
            await viewModel.loadDetail(videoId: videoId, childId: childId)
        }
    }

    @ViewBuilder
    private func thumbnailView(_ video: Video) -> some View {
        if let urlString = video.thumbnailUrl, let url = URL(string: urlString) {
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let image):
                    image
                        .resizable()
                        .aspectRatio(16/9, contentMode: .fill)
                        .frame(maxWidth: .infinity)
                        .frame(height: 300)
                        .clipped()
                        .cornerRadius(12)
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
            .frame(maxWidth: .infinity)
            .frame(height: 300)
            .cornerRadius(12)
            .overlay(
                Image(systemName: "play.rectangle")
                    .font(.largeTitle)
                    .foregroundColor(.gray)
            )
    }
}

// MARK: - ViewModel

@MainActor
final class VideoInfoSheetViewModel: ObservableObject {
    @Published var video: Video?
    @Published var isLoading = false
    @Published var errorMessage: String?

    private let apiClient: APIClient

    init(apiClient: APIClient = APIClient()) {
        self.apiClient = apiClient
    }

    func loadDetail(videoId: String, childId: Int) async {
        isLoading = true
        errorMessage = nil
        do {
            video = try await apiClient.getVideoDetail(videoId: videoId, childId: childId)
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    func toggleWatchStatus(childId: Int) {
        guard var video = video else { return }
        let newStatus = video.isWatched ? "unwatched" : "watched"
        if newStatus == "watched" {
            video.watchStatus = "watched"
        } else {
            video.watchStatus = nil
            video.watchPosition = nil
            video.watchDuration = nil
        }
        self.video = video
        Task {
            await apiClient.setWatchStatus(videoId: video.videoId, childId: childId, status: newStatus)
        }
    }
}
