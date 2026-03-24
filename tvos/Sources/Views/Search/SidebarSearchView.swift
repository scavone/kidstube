import SwiftUI

/// Search screen shown from the sidebar. Contains its own search field and results.
struct SidebarSearchView: View {
    let child: ChildProfile
    let onWatch: (String) -> Void
    let onRequest: (SearchResult) -> Void
    let onBrowseChannel: (ChannelSearchResult) -> Void
    let onRequestChannel: (ChannelSearchResult) -> Void

    @StateObject private var viewModel = SearchResultsViewModel()
    @State private var searchText = ""
    @State private var columnCount = 4
    @State private var infoItem: VideoInfoItem?

    private var resultRows: [[SearchItem]] {
        let cols = max(1, columnCount)
        guard !viewModel.items.isEmpty else { return [] }
        return stride(from: 0, to: viewModel.items.count, by: cols).map { start in
            Array(viewModel.items[start..<min(start + cols, viewModel.items.count)])
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Search header
            VStack(alignment: .leading, spacing: 16) {
                AppTheme.sectionHeader("Search")
                    .padding(.top, 40)

                HStack {
                    Image(systemName: "magnifyingglass")
                        .foregroundColor(AppTheme.textMuted)
                    TextField("Search videos and channels...", text: $searchText)
                        .onSubmit {
                            let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
                            guard !query.isEmpty else { return }
                            Task { await viewModel.search(query: query, childId: child.id) }
                        }
                }
                .padding(12)
                .background(AppTheme.surface)
                .cornerRadius(10)
            }
            .padding(.horizontal, 60)
            .padding(.bottom, 20)

            // Results
            ScrollView {
                if viewModel.isLoading {
                    skeletonResults
                } else if viewModel.items.isEmpty && !searchText.isEmpty {
                    noResults
                } else if viewModel.items.isEmpty {
                    searchPrompt
                } else {
                    LazyVStack(spacing: 30) {
                        ForEach(0..<resultRows.count, id: \.self) { rowIndex in
                            let row = resultRows[rowIndex]
                            HStack(spacing: 30) {
                                ForEach(row) { item in
                                    searchItemCard(item)
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
                }

                if let error = viewModel.errorMessage {
                    Text(error)
                        .foregroundColor(.red)
                        .font(.caption)
                        .padding()
                }
            }
        }
        .sheet(item: $infoItem) { item in
            VideoInfoSheet(videoId: item.id, childId: item.childId)
        }
    }

    @ViewBuilder
    private func searchItemCard(_ item: SearchItem) -> some View {
        switch item {
        case .video(let result):
            videoResultCard(result)
        case .channel(let channel):
            channelResultCard(channel)
        }
    }

    @ViewBuilder
    private func videoResultCard(_ result: SearchResult) -> some View {
        VStack(spacing: 8) {
            VideoCard(
                title: result.title,
                channelName: result.channelName,
                thumbnailUrl: result.thumbnailUrl,
                thumbnailUrls: result.thumbnailUrls ?? [],
                duration: result.formattedDuration,
                badge: statusBadge(result)
            )
            .contextMenu {
                Button {
                    infoItem = VideoInfoItem(id: result.videoId, childId: child.id)
                } label: {
                    Label("Video Info", systemImage: "info.circle")
                }
            }

            actionButton(result)
        }
    }

    @ViewBuilder
    private func actionButton(_ result: SearchResult) -> some View {
        if result.isApproved {
            Button {
                onWatch(result.videoId)
            } label: {
                Label("Watch", systemImage: "play.fill")
                    .font(.caption)
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .tint(.green)
        } else if result.isPending {
            Button {} label: {
                Label("Pending...", systemImage: "clock")
                    .font(.caption)
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .disabled(true)
        } else {
            Button {
                viewModel.markAsPending(videoId: result.videoId)
                onRequest(result)
            } label: {
                Label("Request", systemImage: "hand.raised")
                    .font(.caption)
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
        }
    }

    private func statusBadge(_ result: SearchResult) -> String? {
        switch result.accessStatus {
        case "approved": return "Approved"
        case "pending": return "Pending"
        case "denied": return "Denied"
        default: return nil
        }
    }

    @ViewBuilder
    private func channelResultCard(_ channel: ChannelSearchResult) -> some View {
        VStack(spacing: 8) {
            ChannelCard(
                name: channel.name,
                thumbnailUrl: channel.thumbnailUrl,
                subscriberCount: channel.formattedSubscriberCount
            )

            Button {
                onBrowseChannel(channel)
            } label: {
                Label("Browse", systemImage: "rectangle.grid.2x2")
                    .font(.caption)
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .tint(.blue)

            channelActionButton(channel)
        }
    }

    @ViewBuilder
    private func channelActionButton(_ channel: ChannelSearchResult) -> some View {
        if channel.isAllowed {
            Label("Allowed", systemImage: "checkmark.circle.fill")
                .font(.caption)
                .foregroundColor(.green)
        } else if channel.isPending {
            Button {} label: {
                Label("Pending...", systemImage: "clock")
                    .font(.caption)
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .disabled(true)
        } else {
            Button {
                viewModel.markChannelAsPending(channelId: channel.channelId)
                onRequestChannel(channel)
            } label: {
                Label("Request Channel", systemImage: "plus.circle")
                    .font(.caption)
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
        }
    }

    private var skeletonResults: some View {
        HStack(spacing: 30) {
            ForEach(0..<4, id: \.self) { _ in
                VideoCardSkeleton()
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 60)
        .padding(.top, 20)
    }

    private var searchPrompt: some View {
        VStack(spacing: 16) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 48))
                .foregroundColor(AppTheme.textMuted)
            Text("Search for videos and channels")
                .font(.headline)
                .foregroundColor(AppTheme.textSecondary)
            Text("Type a query and press Enter")
                .font(.subheadline)
                .foregroundColor(AppTheme.textMuted)
        }
        .frame(maxWidth: .infinity)
        .padding(60)
    }

    private var noResults: some View {
        VStack(spacing: 16) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 48))
                .foregroundColor(AppTheme.textMuted)
            Text("No results found")
                .font(.headline)
                .foregroundColor(AppTheme.textSecondary)
            Text("Try a different search term")
                .font(.subheadline)
                .foregroundColor(AppTheme.textMuted)
        }
        .frame(maxWidth: .infinity)
        .padding(60)
    }
}
