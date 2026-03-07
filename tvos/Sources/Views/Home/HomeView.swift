import SwiftUI

/// Main screen after profile selection: search bar + category filters + approved video catalog.
struct HomeView: View {
    let child: ChildProfile
    let refreshTrigger: Int
    let onVideoSelected: (Video) -> Void
    let onSearchSubmitted: (String) -> Void
    let onSwitchProfile: () -> Void
    let onOutsideSchedule: (String) -> Void

    @StateObject private var viewModel = HomeViewModel()
    @State private var searchText = ""
    @State private var columnCount = 4
    @State private var infoItem: VideoInfoItem?
    @State private var durationWarningVideo: Video?

    var body: some View {
        VStack(spacing: 0) {
            // Top bar: child name + time badge + switch profile
            topBar

            // Schedule countdown banner
            if let schedule = viewModel.scheduleStatus,
               schedule.minutesRemaining >= 0,
               schedule.minutesRemaining <= 30 {
                ScheduleBanner(minutesRemaining: schedule.minutesRemaining, endTime: schedule.end)
            }

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
            // If outside schedule on initial load, immediately redirect
            if let schedule = viewModel.scheduleStatus, !schedule.allowed {
                onOutsideSchedule(schedule.unlockTime)
            }
        }
        .onChange(of: refreshTrigger) {
            Task {
                await viewModel.loadCatalog(childId: child.id, reset: true)
                await viewModel.refreshScheduleStatus(childId: child.id)
            }
        }
        .sheet(item: $infoItem) { item in
            VideoInfoSheet(videoId: item.id, childId: item.childId)
        }
        .alert("Video May Be Cut Short", isPresented: Binding(
            get: { durationWarningVideo != nil },
            set: { if !$0 { durationWarningVideo = nil } }
        )) {
            Button("Watch Anyway") {
                if let video = durationWarningVideo {
                    durationWarningVideo = nil
                    onVideoSelected(video)
                }
            }
            Button("Pick Another", role: .cancel) {
                durationWarningVideo = nil
            }
        } message: {
            if let video = durationWarningVideo,
               let schedule = viewModel.scheduleStatus {
                let videoDuration = (video.duration ?? 0) / 60
                Text("This video is \(videoDuration) min but bedtime is in \(schedule.minutesRemaining) min. It will be cut short.")
            }
        }
    }

    /// Check if a video's duration exceeds the remaining schedule time.
    /// If so, show a warning; otherwise, proceed to play.
    private func selectVideo(_ video: Video) {
        if let schedule = viewModel.scheduleStatus,
           schedule.minutesRemaining >= 0,
           let duration = video.duration,
           duration > 0 {
            let videoMinutes = duration / 60
            if videoMinutes > schedule.minutesRemaining {
                durationWarningVideo = video
                return
            }
        }
        onVideoSelected(video)
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
                                VideoCard(
                                    title: video.title,
                                    channelName: video.channelName,
                                    thumbnailUrl: video.thumbnailUrl,
                                    duration: video.formattedDuration,
                                    tracksFocus: true
                                )
                                .onLongPressGesture(minimumDuration: 0.5) {
                                    infoItem = VideoInfoItem(id: video.videoId, childId: child.id)
                                }
                                .onTapGesture {
                                    selectVideo(video)
                                }
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

// MARK: - Schedule Countdown Banner

/// Persistent banner warning the child that the viewing window is closing soon.
struct ScheduleBanner: View {
    let minutesRemaining: Int
    let endTime: String

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "moon.fill")
                .foregroundColor(.white)
            Text(bannerText)
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundColor(.white)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 10)
        .background(minutesRemaining <= 5 ? Color.red.opacity(0.9) : Color.orange.opacity(0.9))
    }

    private var bannerText: String {
        if minutesRemaining <= 0 {
            return "Bedtime! Viewing window has ended."
        } else if minutesRemaining == 1 {
            return "Bedtime in 1 minute!"
        } else {
            return "Bedtime in \(minutesRemaining) minutes"
        }
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
    @Published var scheduleStatus: ScheduleStatus?
    @Published var selectedCategory: String?
    @Published var isLoading = false
    @Published var hasMore = false
    @Published var errorMessage: String?

    private let apiClient: APIClient
    private var offset = 0
    private var scheduleRefreshTask: Task<Void, Never>?

    init(apiClient: APIClient = APIClient()) {
        self.apiClient = apiClient
    }

    func loadInitialData(childId: Int) async {
        async let catalogTask: () = loadCatalog(childId: childId, reset: true)
        async let timeTask: () = refreshTimeStatus(childId: childId)
        async let scheduleTask: () = refreshScheduleStatus(childId: childId)
        _ = await (catalogTask, timeTask, scheduleTask)
        startScheduleRefresh(childId: childId)
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

    func refreshScheduleStatus(childId: Int) async {
        do {
            scheduleStatus = try await apiClient.getScheduleStatus(childId: childId)
        } catch {
            // Non-critical — schedule banner just won't show
        }
    }

    /// Periodically refresh schedule status so the countdown banner updates.
    private func startScheduleRefresh(childId: Int) {
        scheduleRefreshTask?.cancel()
        scheduleRefreshTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 60 * 1_000_000_000) // every minute
                guard !Task.isCancelled else { break }
                await self?.refreshScheduleStatus(childId: childId)
            }
        }
    }
}
