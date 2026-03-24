import SwiftUI

/// Grid of all approved channels for a child. Shown from the sidebar's "Channels" section.
/// Clicking a channel navigates to its detail view.
struct ChannelsListView: View {
    let child: ChildProfile
    let onChannelSelected: (HomeChannel) -> Void

    @StateObject private var viewModel = ChannelsListViewModel()

    private let columns = [
        GridItem(.adaptive(minimum: 140, maximum: 180), spacing: 30)
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                AppTheme.sectionHeader("Channels")
                    .padding(.horizontal, 60)
                    .padding(.top, 40)

                if viewModel.isLoading {
                    skeletonGrid
                } else if viewModel.channels.isEmpty {
                    emptyState
                } else {
                    LazyVGrid(columns: columns, spacing: 30) {
                        ForEach(viewModel.channels) { channel in
                            ChannelsListItemView(
                                channel: channel,
                                onSelected: { onChannelSelected(channel) }
                            )
                        }
                    }
                    .padding(.horizontal, 60)
                    .padding(.bottom, 40)
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
            await viewModel.loadChannels(childId: child.id)
        }
    }

    private var skeletonGrid: some View {
        LazyVGrid(columns: columns, spacing: 30) {
            ForEach(0..<8, id: \.self) { _ in
                VStack(spacing: 10) {
                    SkeletonLoader(height: 120, cornerRadius: 60)
                        .frame(width: 120)
                    SkeletonLoader(height: 14, cornerRadius: 4)
                        .frame(width: 100)
                }
            }
        }
        .padding(.horizontal, 60)
    }

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "rectangle.stack.person.crop")
                .font(.system(size: 48))
                .foregroundColor(AppTheme.textMuted)
            Text("No channels yet")
                .font(.headline)
                .foregroundColor(AppTheme.textSecondary)
            Text("Search for channels and ask a parent to approve them!")
                .font(.subheadline)
                .foregroundColor(AppTheme.textMuted)
        }
        .frame(maxWidth: .infinity)
        .padding(60)
    }
}

/// A single channel item in the channels grid — circular avatar + name.
struct ChannelsListItemView: View {
    let channel: HomeChannel
    let onSelected: () -> Void

    @FocusState private var isFocused: Bool

    var body: some View {
        Button(action: onSelected) {
            VStack(spacing: 10) {
                avatarImage
                    .frame(width: 120, height: 120)
                    .clipShape(Circle())
                    .overlay(
                        Circle()
                            .stroke(
                                isFocused ? Color.accentColor : AppTheme.border,
                                lineWidth: isFocused ? 3 : 1
                            )
                    )
                    .shadow(
                        color: isFocused ? AppTheme.cardFocusGlowColor : .clear,
                        radius: isFocused ? 8 : 0
                    )

                Text(channel.channelName)
                    .font(.caption)
                    .fontWeight(isFocused ? .semibold : .regular)
                    .foregroundColor(isFocused ? AppTheme.textPrimary : AppTheme.textSecondary)
                    .lineLimit(2)
                    .multilineTextAlignment(.center)
                    .frame(width: 130)

                if let category = channel.category {
                    Text(category.uppercased())
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(AppTheme.categoryColor(category))
                }
            }
        }
        .buttonStyle(.plain)
        .focused($isFocused)
        .scaleEffect(isFocused ? AppTheme.cardFocusScale : 1.0)
        .animation(.easeInOut(duration: 0.15), value: isFocused)
    }

    @ViewBuilder
    private var avatarImage: some View {
        if let urlString = channel.thumbnailUrl, let url = URL(string: urlString) {
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let image):
                    image.resizable().aspectRatio(contentMode: .fill)
                case .failure:
                    avatarPlaceholder
                default:
                    avatarPlaceholder
                        .overlay(ProgressView().scaleEffect(0.6))
                }
            }
        } else {
            avatarPlaceholder
        }
    }

    private var avatarPlaceholder: some View {
        Circle()
            .fill(AppTheme.surface)
            .overlay(
                Text(String(channel.channelName.prefix(1)).uppercased())
                    .font(.title2)
                    .fontWeight(.bold)
                    .foregroundColor(AppTheme.textMuted)
            )
    }
}

// MARK: - ViewModel

@MainActor
final class ChannelsListViewModel: ObservableObject {
    @Published var channels: [HomeChannel] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    private let apiClient: APIClient

    init(apiClient: APIClient = APIClient()) {
        self.apiClient = apiClient
    }

    func loadChannels(childId: Int) async {
        isLoading = true
        errorMessage = nil
        do {
            channels = try await apiClient.getHomeChannels(childId: childId)
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}
