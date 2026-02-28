import SwiftUI

/// Main screen after profile selection: search bar + category filters + approved video catalog.
struct HomeView: View {
    let child: ChildProfile
    let onVideoSelected: (Video) -> Void
    let onSearchSubmitted: (String) -> Void
    let onSwitchProfile: () -> Void

    @StateObject private var viewModel = HomeViewModel()
    @State private var searchText = ""
    @State private var columnCount = 4

    var body: some View {
        VStack(spacing: 0) {
            // Top bar: child name + time badge + switch profile
            topBar

            // Search field
            searchField

            // Category filter tabs
            CategoryFilterView(
                selectedCategory: $viewModel.selectedCategory,
                onChange: { _ in
                    Task { await viewModel.loadCatalog(childId: child.id, reset: true) }
                }
            )

            // Catalog grid
            catalogGrid
        }
        .task {
            await viewModel.loadInitialData(childId: child.id)
        }
    }

    // MARK: - Top Bar

    private var topBar: some View {
        HStack {
            HStack(spacing: 10) {
                Text(child.avatar)
                    .font(.title3)
                Text(child.name)
                    .font(.headline)
            }

            Spacer()

            TimeBadge(timeStatus: viewModel.timeStatus, style: .compact)

            Button(action: onSwitchProfile) {
                Label("Switch", systemImage: "person.2")
                    .font(.caption)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 60)
        .padding(.top, 20)
        .padding(.bottom, 10)
    }

    // MARK: - Search

    private var searchField: some View {
        HStack {
            Image(systemName: "magnifyingglass")
                .foregroundColor(.secondary)
            TextField("Search videos...", text: $searchText)
                .onSubmit {
                    let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !query.isEmpty else { return }
                    onSearchSubmitted(query)
                }
        }
        .padding(12)
        .background(Color.gray.opacity(0.15))
        .cornerRadius(10)
        .padding(.horizontal, 60)
        .padding(.bottom, 16)
    }

    // MARK: - Catalog Grid

    private var videoRows: [[Video]] {
        let cols = max(1, columnCount)
        guard !viewModel.videos.isEmpty else { return [] }
        return stride(from: 0, to: viewModel.videos.count, by: cols).map { start in
            Array(viewModel.videos[start..<min(start + cols, viewModel.videos.count)])
        }
    }

    private var catalogGrid: some View {
        ScrollView {
            if viewModel.isLoading && viewModel.videos.isEmpty {
                ProgressView()
                    .scaleEffect(1.5)
                    .padding(60)
            } else if viewModel.videos.isEmpty {
                emptyCatalog
            } else {
                LazyVStack(spacing: 30) {
                    ForEach(0..<videoRows.count, id: \.self) { rowIndex in
                        let row = videoRows[rowIndex]
                        HStack(spacing: 30) {
                            ForEach(row) { video in
                                Button {
                                    onVideoSelected(video)
                                } label: {
                                    VideoCard(
                                        title: video.title,
                                        channelName: video.channelName,
                                        thumbnailUrl: video.thumbnailUrl,
                                        duration: video.formattedDuration,
                                        tracksFocus: false
                                    )
                                }
                                .buttonStyle(.plain)
                                .onAppear {
                                    // Infinite scroll: load more when near the end
                                    if video.videoId == viewModel.videos.last?.videoId && viewModel.hasMore {
                                        Task { await viewModel.loadCatalog(childId: child.id, reset: false) }
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
                    ProgressView()
                        .padding()
                }
            }

            if let error = viewModel.errorMessage {
                Text(error)
                    .foregroundColor(.red)
                    .font(.caption)
                    .padding()
            }
        }
    }

    private var emptyCatalog: some View {
        VStack(spacing: 16) {
            Image(systemName: "film.stack")
                .font(.system(size: 48))
                .foregroundColor(.secondary)
            Text("No approved videos yet")
                .font(.headline)
                .foregroundColor(.secondary)
            Text("Search for videos and ask a parent to approve them!")
                .font(.callout)
                .foregroundColor(.secondary)
        }
        .padding(60)
    }
}

// MARK: - Category Filter

struct CategoryFilterView: View {
    @Binding var selectedCategory: String?
    let onChange: (String?) -> Void

    private let categories: [(label: String, value: String?)] = [
        ("All", nil),
        ("Educational", "edu"),
        ("Entertainment", "fun")
    ]

    var body: some View {
        HStack(spacing: 16) {
            ForEach(categories, id: \.label) { cat in
                Button {
                    selectedCategory = cat.value
                    onChange(cat.value)
                } label: {
                    Text(cat.label)
                        .font(.subheadline)
                        .fontWeight(selectedCategory == cat.value ? .bold : .regular)
                        .padding(.horizontal, 20)
                        .padding(.vertical, 8)
                        .background(
                            selectedCategory == cat.value
                                ? Color.accentColor.opacity(0.3)
                                : Color.gray.opacity(0.1)
                        )
                        .cornerRadius(8)
                }
                .buttonStyle(.plain)
            }
            Spacer()
        }
        .padding(.horizontal, 60)
        .padding(.bottom, 12)
    }
}

// MARK: - ViewModel

@MainActor
final class HomeViewModel: ObservableObject {
    @Published var videos: [Video] = []
    @Published var timeStatus: TimeStatus?
    @Published var selectedCategory: String?
    @Published var isLoading = false
    @Published var hasMore = false
    @Published var errorMessage: String?

    private let apiClient: APIClient
    private var offset = 0

    init(apiClient: APIClient = APIClient()) {
        self.apiClient = apiClient
    }

    func loadInitialData(childId: Int) async {
        async let catalogTask: () = loadCatalog(childId: childId, reset: true)
        async let timeTask: () = refreshTimeStatus(childId: childId)
        _ = await (catalogTask, timeTask)
    }

    func loadCatalog(childId: Int, reset: Bool) async {
        if reset {
            offset = 0
            videos = []
        }
        isLoading = true
        errorMessage = nil
        do {
            let response = try await apiClient.getCatalog(
                childId: childId,
                category: selectedCategory,
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

    func refreshTimeStatus(childId: Int) async {
        do {
            timeStatus = try await apiClient.getTimeStatus(childId: childId)
        } catch {
            // Non-critical — time badge just won't show
        }
    }
}
