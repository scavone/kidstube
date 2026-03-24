import SwiftUI

/// Shows approved videos filtered by a specific category.
/// Used as the detail view when a category is selected from the sidebar.
struct CategoryContentView: View {
    let child: ChildProfile
    let category: String
    let onVideoSelected: (Video) -> Void

    @StateObject private var viewModel = CategoryContentViewModel()
    @State private var columnCount = 4
    @State private var infoItem: VideoInfoItem?

    private var categoryLabel: String {
        switch category {
        case "edu": return "Educational"
        case "fun": return "Entertainment"
        case "music": return "Music"
        default: return category.capitalized
        }
    }

    private var videoRows: [[Video]] {
        let cols = max(1, columnCount)
        guard !viewModel.videos.isEmpty else { return [] }
        return stride(from: 0, to: viewModel.videos.count, by: cols).map { start in
            Array(viewModel.videos[start..<min(start + cols, viewModel.videos.count)])
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Header
                HStack(spacing: 12) {
                    Circle()
                        .fill(AppTheme.categoryColor(category))
                        .frame(width: 10, height: 10)
                    AppTheme.sectionHeader(categoryLabel)
                    Spacer()
                }
                .padding(.horizontal, 60)
                .padding(.top, 40)

                // Sort controls
                HStack(spacing: 12) {
                    ForEach(CatalogSort.allCases, id: \.self) { sort in
                        Button {
                            viewModel.selectedSort = sort
                            Task { await viewModel.loadVideos(childId: child.id, category: category, reset: true) }
                        } label: {
                            Text(sort.label)
                                .font(.subheadline)
                                .fontWeight(viewModel.selectedSort == sort ? .bold : .regular)
                                .padding(.horizontal, 16)
                                .padding(.vertical, 8)
                                .background(
                                    viewModel.selectedSort == sort
                                        ? AppTheme.categoryColor(category).opacity(0.3)
                                        : AppTheme.surface
                                )
                                .cornerRadius(8)
                        }
                        .buttonStyle(.plain)
                    }
                    Spacer()
                }
                .padding(.horizontal, 60)

                // Video grid
                if viewModel.isLoading && viewModel.videos.isEmpty {
                    skeletonGrid
                } else if viewModel.videos.isEmpty {
                    emptyState
                } else {
                    LazyVStack(spacing: 30) {
                        ForEach(0..<videoRows.count, id: \.self) { rowIndex in
                            let row = videoRows[rowIndex]
                            HStack(spacing: 30) {
                                ForEach(row) { video in
                                    VideoCard(
                                        title: video.title,
                                        channelName: video.channelName,
                                        thumbnailUrl: video.thumbnailUrl,
                                        duration: video.formattedDuration,
                                        tracksFocus: true,
                                        progress: video.watchProgress,
                                        isWatched: video.isWatched
                                    )
                                    .contextMenu {
                                        Button {
                                            infoItem = VideoInfoItem(id: video.videoId, childId: child.id)
                                        } label: {
                                            Label("Video Info", systemImage: "info.circle")
                                        }
                                    }
                                    .onTapGesture {
                                        onVideoSelected(video)
                                    }
                                    .onAppear {
                                        if video.videoId == viewModel.videos.last?.videoId && viewModel.hasMore {
                                            Task { await viewModel.loadVideos(childId: child.id, category: category, reset: false) }
                                        }
                                    }
                                }
                                Spacer(minLength: 0)
                            }
                            .focusSection()
                        }
                    }
                    .padding(.horizontal, 60)
                    .padding(.bottom, 40)
                    .background(
                        GeometryReader { geo in
                            Color.clear.onAppear {
                                let cols = max(1, Int((geo.size.width + 30) / (280 + 30)))
                                if cols != columnCount { columnCount = cols }
                            }
                        }
                    )

                    if viewModel.isLoading {
                        ProgressView().padding()
                    }
                }

                if let error = viewModel.errorMessage {
                    Text(error)
                        .foregroundColor(.red)
                        .font(.caption)
                        .padding(.horizontal, 60)
                }
            }
        }
        .task {
            await viewModel.loadVideos(childId: child.id, category: category, reset: true)
        }
        .onChange(of: category) {
            Task { await viewModel.loadVideos(childId: child.id, category: category, reset: true) }
        }
        .sheet(item: $infoItem) { item in
            VideoInfoSheet(videoId: item.id, childId: item.childId)
        }
    }

    private var skeletonGrid: some View {
        HStack(spacing: 30) {
            ForEach(0..<4, id: \.self) { _ in
                VideoCardSkeleton()
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 60)
    }

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "film.stack")
                .font(.system(size: 48))
                .foregroundColor(AppTheme.textMuted)
            Text("No \(categoryLabel.lowercased()) videos yet")
                .font(.headline)
                .foregroundColor(AppTheme.textSecondary)
        }
        .frame(maxWidth: .infinity)
        .padding(60)
    }
}

// MARK: - ViewModel

@MainActor
final class CategoryContentViewModel: ObservableObject {
    @Published var videos: [Video] = []
    @Published var selectedSort: CatalogSort = .newest
    @Published var isLoading = false
    @Published var hasMore = false
    @Published var errorMessage: String?

    private let apiClient: APIClient
    private var offset = 0

    init(apiClient: APIClient = APIClient()) {
        self.apiClient = apiClient
    }

    func loadVideos(childId: Int, category: String, reset: Bool) async {
        if reset {
            offset = 0
            videos = []
        }
        isLoading = true
        errorMessage = nil
        do {
            let response = try await apiClient.getCatalog(
                childId: childId,
                category: category,
                sortBy: selectedSort.rawValue,
                offset: offset
            )
            if reset {
                videos = response.videos
            } else {
                videos.append(contentsOf: response.videos)
            }
            hasMore = response.hasMore
            offset = videos.count
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}
