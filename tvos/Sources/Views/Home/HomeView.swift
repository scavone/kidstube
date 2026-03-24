import SwiftUI

// MARK: - Catalog Sort

enum CatalogSort: String, CaseIterable {
    case newest
    case oldest
    case title
    case channel

    var label: String {
        switch self {
        case .newest: return "Newest"
        case .oldest: return "Oldest"
        case .title: return "Title"
        case .channel: return "Channel"
        }
    }
}

enum WatchStatusFilter: String, CaseIterable {
    case all
    case unwatched
    case inProgress = "in_progress"
    case watched

    var label: String {
        switch self {
        case .all: return "All"
        case .unwatched: return "Unwatched"
        case .inProgress: return "In Progress"
        case .watched: return "Watched"
        }
    }
}

/// Main screen after profile selection: featured banner, channel row, search, filters, and catalog grid.
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
    @State private var focusedChannelId: String?

    var body: some View {
        VStack(spacing: 0) {
            // Schedule countdown banner
            if let schedule = viewModel.scheduleStatus,
               schedule.minutesRemaining >= 0,
               schedule.minutesRemaining <= 30 {
                ScheduleBanner(minutesRemaining: schedule.minutesRemaining, endTime: schedule.end)
            }

            // Main scrollable content
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(spacing: 20) {
                        // Featured Banner — shows latest video from focused channel
                        FeaturedBannerView(
                            channel: viewModel.focusedChannel,
                            onPlay: { video in
                                let v = Video(
                                    videoId: video.videoId,
                                    title: video.title,
                                    channelName: viewModel.focusedChannel?.channelName ?? ""
                                )
                                selectVideo(v)
                            }
                        )
                        .animation(.easeInOut(duration: 0.35), value: viewModel.focusedChannel?.id)
                        .padding(.top, 8)

                        // Channel Row — horizontal scroll of approved channels
                        HomeChannelRowView(
                            channels: viewModel.homeChannels,
                            focusedChannelId: focusedChannelId,
                            onFocusChanged: { channelId in
                                focusedChannelId = channelId
                                viewModel.updateFocusedChannel(channelId: channelId)
                            },
                            onChannelSelected: { channel in
                                // Filter catalog by channel_name (backend filters on channel_name)
                                viewModel.selectedChannelFilter = channel.channelName
                                Task { await viewModel.loadCatalog(childId: child.id, reset: true) }
                            }
                        )
                        .padding(.bottom, 4)

                        // Recently Added row
                        if !viewModel.recentlyAdded.isEmpty {
                            recentlyAddedRow
                        }

                        // Divider between hero section and catalog
                        if !viewModel.homeChannels.isEmpty || !viewModel.recentlyAdded.isEmpty {
                            Rectangle()
                                .fill(AppTheme.border)
                                .frame(height: 1)
                                .padding(.horizontal, 60)
                        }

                        // Search field
                        searchField

                        // Category + Sort filter row
                        HStack(alignment: .top, spacing: 0) {
                            CategoryFilterView(
                                selectedCategory: $viewModel.selectedCategory,
                                onChange: { _ in
                                    Task { await viewModel.loadCatalog(childId: child.id, reset: true) }
                                }
                            )

                            SortPickerView(
                                selectedSort: $viewModel.selectedSort,
                                onChange: { _ in
                                    Task { await viewModel.loadCatalog(childId: child.id, reset: true) }
                                }
                            )
                        }

                        // Channel filter pill (shown when a channel is selected)
                        if viewModel.selectedChannelFilter != nil {
                            channelFilterPill
                        }

                        // Watch status filter row
                        WatchStatusFilterView(
                            selectedFilter: $viewModel.selectedWatchFilter,
                            statusCounts: viewModel.statusCounts,
                            onChange: { _ in
                                Task { await viewModel.loadCatalog(childId: child.id, reset: true) }
                            }
                        )

                        // Catalog grid
                        catalogContent(proxy: proxy)
                    }
                }
            }
        }
        .task {
            await viewModel.loadInitialData(childId: child.id)
            // Set initial focus to first channel
            if let first = viewModel.homeChannels.first {
                focusedChannelId = first.id
                viewModel.updateFocusedChannel(channelId: first.id)
            }
            // If outside schedule on initial load, immediately redirect
            if let schedule = viewModel.scheduleStatus, !schedule.allowed {
                onOutsideSchedule(schedule.unlockTime)
            }
        }
        .onChange(of: refreshTrigger) {
            Task {
                await viewModel.loadCatalog(childId: child.id, reset: true)
                await viewModel.loadHomeChannels(childId: child.id)
                await viewModel.refreshScheduleStatus(childId: child.id)
            }
        }
        .sheet(item: $infoItem) { item in
            VideoInfoSheet(
                videoId: item.id,
                childId: item.childId,
                onWatchStatusChanged: { videoId, status in
                    viewModel.updateLocalWatchStatus(videoId: videoId, status: status)
                }
            )
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

    // MARK: - Recently Added Row

    private var recentlyAddedRow: some View {
        VStack(alignment: .leading, spacing: 12) {
            AppTheme.sectionHeader("Recently Added")
                .padding(.horizontal, 60)

            ScrollView(.horizontal, showsIndicators: false) {
                LazyHStack(spacing: 20) {
                    ForEach(viewModel.recentlyAdded) { video in
                        VideoCard(
                            title: video.title,
                            channelName: video.channelName,
                            thumbnailUrl: video.thumbnailUrl,
                            thumbnailUrls: video.thumbnailUrls ?? [],
                            duration: video.formattedDuration,
                            tracksFocus: true,
                            progress: video.watchProgress,
                            isWatched: video.isWatched
                        )
                        .onTapGesture {
                            selectVideo(video)
                        }
                    }
                }
                .padding(.horizontal, 60)
                .padding(.vertical, 8)
            }
            .focusSection()
        }
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
    }

    // MARK: - Channel Filter Pill

    private var channelFilterPill: some View {
        HStack {
            HStack(spacing: 8) {
                Image(systemName: "line.3.horizontal.decrease.circle.fill")
                    .foregroundColor(.accentColor)
                Text("Channel: \(viewModel.selectedChannelFilter ?? "")")
                    .font(.subheadline)
                    .fontWeight(.medium)
                Button {
                    viewModel.selectedChannelFilter = nil
                    Task { await viewModel.loadCatalog(childId: child.id, reset: true) }
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .background(Color.accentColor.opacity(0.15))
            .cornerRadius(8)

            Spacer()
        }
        .padding(.horizontal, 60)
    }

    // MARK: - Catalog Grid

    private var videoRows: [[Video]] {
        let cols = max(1, columnCount)
        guard !viewModel.videos.isEmpty else { return [] }
        return stride(from: 0, to: viewModel.videos.count, by: cols).map { start in
            Array(viewModel.videos[start..<min(start + cols, viewModel.videos.count)])
        }
    }

    @ViewBuilder
    private func catalogContent(proxy: ScrollViewProxy) -> some View {
        if viewModel.selectedSort == .title && !viewModel.videos.isEmpty {
            HStack(spacing: 0) {
                catalogGrid(proxy: proxy)
                AlphabetRailView(
                    videos: viewModel.videos,
                    onLetterSelected: { letter in
                        viewModel.scrollToLetter = letter
                    }
                )
            }
        } else {
            catalogGrid(proxy: proxy)
        }
    }

    private func catalogGrid(proxy: ScrollViewProxy) -> some View {
        Group {
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
                                    thumbnailUrls: video.thumbnailUrls ?? [],
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
                                    Button {
                                        Task { await viewModel.toggleWatchStatus(video: video, childId: child.id) }
                                    } label: {
                                        if video.isWatched {
                                            Label("Mark as Unwatched", systemImage: "arrow.counterclockwise")
                                        } else {
                                            Label("Mark as Watched", systemImage: "checkmark.circle")
                                        }
                                    }
                                }
                                .onTapGesture {
                                    selectVideo(video)
                                }
                                .onAppear {
                                    if video.videoId == viewModel.videos.last?.videoId && viewModel.hasMore {
                                        Task { await viewModel.loadCatalog(childId: child.id, reset: false) }
                                    }
                                }
                            }
                            Spacer(minLength: 0)
                        }
                        .id("row-\(rowIndex)")
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
        .onChange(of: viewModel.scrollToLetter) {
            guard let letter = viewModel.scrollToLetter else { return }
            viewModel.scrollToLetter = nil
            let cols = max(1, columnCount)
            if let videoIndex = viewModel.videos.firstIndex(where: {
                $0.title.folding(options: [.diacriticInsensitive, .caseInsensitive], locale: nil)
                    .first?.uppercased() == letter
            }) {
                let rowIndex = videoIndex / cols
                withAnimation {
                    proxy.scrollTo("row-\(rowIndex)", anchor: .top)
                }
            }
        }
    }

    private var emptyCatalog: some View {
        VStack(spacing: 16) {
            Image(systemName: emptyCatalogIcon)
                .font(.system(size: 48))
                .foregroundColor(.secondary)
            Text(emptyCatalogTitle)
                .font(.headline)
                .foregroundColor(.secondary)
            Text(emptyCatalogSubtitle)
                .font(.callout)
                .foregroundColor(.secondary)
        }
        .padding(60)
    }

    private var emptyCatalogIcon: String {
        viewModel.selectedWatchFilter == .all ? "film.stack" : "checkmark.circle"
    }

    private var emptyCatalogTitle: String {
        switch viewModel.selectedWatchFilter {
        case .all: return "No approved videos yet"
        case .unwatched: return "No unwatched videos"
        case .inProgress: return "No videos in progress"
        case .watched: return "No watched videos"
        }
    }

    private var emptyCatalogSubtitle: String {
        if viewModel.selectedWatchFilter == .all {
            return "Search for videos and ask a parent to approve them!"
        }
        return "Try a different filter to see more videos."
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

// MARK: - Sort Picker

struct SortPickerView: View {
    @Binding var selectedSort: CatalogSort
    let onChange: (CatalogSort) -> Void

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "arrow.up.arrow.down")
                .font(.subheadline)
                .foregroundColor(.secondary)

            ForEach(CatalogSort.allCases, id: \.self) { sort in
                Button {
                    selectedSort = sort
                    onChange(sort)
                } label: {
                    Text(sort.label)
                        .font(.subheadline)
                        .fontWeight(selectedSort == sort ? .bold : .regular)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .background(
                            selectedSort == sort
                                ? Color.accentColor.opacity(0.3)
                                : Color.gray.opacity(0.1)
                        )
                        .cornerRadius(8)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.trailing, 60)
        .padding(.bottom, 12)
    }
}

// MARK: - Watch Status Filter

struct WatchStatusFilterView: View {
    @Binding var selectedFilter: WatchStatusFilter
    let statusCounts: StatusCounts?
    let onChange: (WatchStatusFilter) -> Void

    var body: some View {
        HStack(spacing: 16) {
            ForEach(WatchStatusFilter.allCases, id: \.self) { filter in
                Button {
                    selectedFilter = filter
                    onChange(filter)
                } label: {
                    HStack(spacing: 4) {
                        Text(filter.label)
                        if let counts = statusCounts {
                            Text("(\(countFor(filter, counts: counts)))")
                                .foregroundColor(.secondary)
                        }
                    }
                    .font(.subheadline)
                    .fontWeight(selectedFilter == filter ? .bold : .regular)
                    .padding(.horizontal, 20)
                    .padding(.vertical, 8)
                    .background(
                        selectedFilter == filter
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

    private func countFor(_ filter: WatchStatusFilter, counts: StatusCounts) -> Int {
        switch filter {
        case .all: return counts.all
        case .unwatched: return counts.unwatched
        case .inProgress: return counts.inProgress
        case .watched: return counts.watched
        }
    }
}

// MARK: - Alphabet Rail

struct AlphabetRailView: View {
    let videos: [Video]
    let onLetterSelected: (String) -> Void

    private let letters = (65...90).map { String(UnicodeScalar($0)) } // A-Z

    private var availableLetters: Set<String> {
        Set(videos.compactMap {
            $0.title.folding(options: [.diacriticInsensitive, .caseInsensitive], locale: nil)
                .first?.uppercased()
        }.filter { letters.contains($0) })
    }

    var body: some View {
        ScrollView(.vertical, showsIndicators: false) {
            VStack(spacing: 4) {
                ForEach(letters, id: \.self) { letter in
                    let available = availableLetters.contains(letter)
                    Button {
                        if available { onLetterSelected(letter) }
                    } label: {
                        Text(letter)
                            .font(.caption2)
                            .fontWeight(.medium)
                            .foregroundColor(available ? .primary : .secondary.opacity(0.3))
                            .frame(width: 32, height: 28)
                    }
                    .buttonStyle(.plain)
                    .disabled(!available)
                }
            }
            .padding(.vertical, 8)
        }
        .frame(width: 48)
    }
}

// MARK: - ViewModel

@MainActor
final class HomeViewModel: ObservableObject {
    @Published var videos: [Video] = []
    @Published var recentlyAdded: [Video] = []
    @Published var homeChannels: [HomeChannel] = []
    @Published var focusedChannel: HomeChannel?
    @Published var selectedChannelFilter: String?
    @Published var timeStatus: TimeStatus?
    @Published var scheduleStatus: ScheduleStatus?
    @Published var selectedCategory: String?
    @Published var selectedSort: CatalogSort = .newest
    @Published var selectedWatchFilter: WatchStatusFilter = .all
    @Published var statusCounts: StatusCounts?
    @Published var scrollToLetter: String?
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
        async let channelsTask: () = loadHomeChannels(childId: childId)
        async let recentTask: () = loadRecentlyAdded(childId: childId)
        _ = await (catalogTask, timeTask, scheduleTask, channelsTask, recentTask)
        startScheduleRefresh(childId: childId)
    }

    func loadRecentlyAdded(childId: Int) async {
        do {
            recentlyAdded = try await apiClient.getRecentlyAdded(childId: childId)
        } catch {
            // Non-critical — recently added row just won't show
        }
    }

    func loadHomeChannels(childId: Int) async {
        do {
            homeChannels = try await apiClient.getHomeChannels(childId: childId)
            // Default to first channel if nothing is focused
            if focusedChannel == nil, let first = homeChannels.first {
                focusedChannel = first
            }
        } catch {
            // Non-critical — channel row and banner just won't show
        }
    }

    func updateFocusedChannel(channelId: String) {
        if let channel = homeChannels.first(where: { $0.id == channelId }) {
            withAnimation(.easeInOut(duration: 0.3)) {
                focusedChannel = channel
            }
        }
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
                channel: selectedChannelFilter,
                sortBy: selectedSort.rawValue,
                watchStatus: selectedWatchFilter.rawValue,
                offset: offset
            )
            if reset {
                videos = response.videos
            } else {
                videos.append(contentsOf: response.videos)
            }
            hasMore = response.hasMore
            offset = videos.count
            if let counts = response.statusCounts {
                statusCounts = counts
            }
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

    func toggleWatchStatus(video: Video, childId: Int) async {
        let newStatus = video.isWatched ? "unwatched" : "watched"
        updateLocalWatchStatus(videoId: video.videoId, status: newStatus)
        await apiClient.setWatchStatus(videoId: video.videoId, childId: childId, status: newStatus)
    }

    func updateLocalWatchStatus(videoId: String, status: String) {
        guard let index = videos.firstIndex(where: { $0.videoId == videoId }) else { return }
        if status == "watched" {
            videos[index].watchStatus = "watched"
        } else {
            videos[index].watchStatus = nil
            videos[index].watchPosition = nil
            videos[index].watchDuration = nil
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
