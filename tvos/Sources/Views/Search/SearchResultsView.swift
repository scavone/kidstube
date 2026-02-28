import SwiftUI

/// Displays search results with contextual action buttons:
/// - "Watch" if the video is already approved
/// - "Pending..." if awaiting parent approval
/// - "Request" if not yet requested
struct SearchResultsView: View {
    let query: String
    let child: ChildProfile
    let onWatch: (String) -> Void
    let onRequest: (SearchResult) -> Void
    let onBack: () -> Void

    @StateObject private var viewModel = SearchResultsViewModel()
    @State private var columnCount = 4

    private var resultRows: [[SearchResult]] {
        let cols = max(1, columnCount)
        guard !viewModel.results.isEmpty else { return [] }
        return stride(from: 0, to: viewModel.results.count, by: cols).map { start in
            Array(viewModel.results[start..<min(start + cols, viewModel.results.count)])
        }
    }

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

                Text("Results for \"\(query)\"")
                    .font(.headline)

                Spacer()
            }
            .padding(.horizontal, 60)
            .padding(.vertical, 16)

            // Results
            ScrollView {
                if viewModel.isLoading {
                    ProgressView()
                        .scaleEffect(1.5)
                        .padding(60)
                } else if viewModel.results.isEmpty {
                    noResults
                } else {
                    LazyVStack(spacing: 30) {
                        ForEach(0..<resultRows.count, id: \.self) { rowIndex in
                            let row = resultRows[rowIndex]
                            HStack(spacing: 30) {
                                ForEach(row) { result in
                                    searchResultCard(result)
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
        .task {
            await viewModel.search(query: query, childId: child.id)
        }
    }

    @ViewBuilder
    private func searchResultCard(_ result: SearchResult) -> some View {
        VStack(spacing: 8) {
            VideoCard(
                title: result.title,
                channelName: result.channelName,
                thumbnailUrl: result.thumbnailUrl,
                duration: result.formattedDuration,
                badge: statusBadge(result)
            )

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

    private var noResults: some View {
        VStack(spacing: 16) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 48))
                .foregroundColor(.secondary)
            Text("No results found")
                .font(.headline)
                .foregroundColor(.secondary)
            Text("Try a different search term")
                .font(.callout)
                .foregroundColor(.secondary)
        }
        .padding(60)
    }
}

// MARK: - ViewModel

@MainActor
final class SearchResultsViewModel: ObservableObject {
    @Published var results: [SearchResult] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    private let apiClient: APIClient

    init(apiClient: APIClient = APIClient()) {
        self.apiClient = apiClient
    }

    func search(query: String, childId: Int) async {
        isLoading = true
        errorMessage = nil
        do {
            let response = try await apiClient.search(query: query, childId: childId)
            results = response.results
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}
