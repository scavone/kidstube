import SwiftUI

/// "Who's watching?" profile selection screen shown at launch.
/// Auto-selects when only one child profile exists.
struct ProfilePickerView: View {
    @StateObject private var viewModel = ProfilePickerViewModel()
    var suppressAutoSelect: Bool = false
    let onProfileSelected: (ChildProfile) -> Void

    private let columns = [
        GridItem(.adaptive(minimum: 200, maximum: 250), spacing: 40)
    ]

    var body: some View {
        VStack(spacing: 40) {
            Text("Who's watching?")
                .font(.title)
                .fontWeight(.bold)

            if viewModel.isLoading {
                ProgressView()
                    .scaleEffect(1.5)
            } else if viewModel.profiles.isEmpty {
                emptyState
            } else {
                LazyVGrid(columns: columns, spacing: 40) {
                    ForEach(viewModel.profiles) { profile in
                        ProfileCardView(
                            profile: profile,
                            subtitle: profile.subtitle
                        ) {
                            onProfileSelected(profile)
                        }
                    }
                }
                .padding(.horizontal, 80)
            }

            if let error = viewModel.errorMessage {
                Text(error)
                    .foregroundColor(.red)
                    .font(.caption)
                    .multilineTextAlignment(.center)
                    .padding()

                Button("Retry") {
                    Task { await viewModel.loadProfiles() }
                }
            }
        }
        .padding(60)
        .task {
            await viewModel.loadProfiles()
            // Auto-skip when only one child exists (unless suppressed after PIN cancel)
            if viewModel.profiles.count == 1 && !suppressAutoSelect {
                onProfileSelected(viewModel.profiles[0])
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 20) {
            Text("No profiles yet")
                .font(.headline)
                .foregroundColor(.secondary)
            Text("Ask a parent to add a profile\nusing the Telegram bot with /addkid")
                .font(.callout)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)

            Button("Refresh") {
                Task { await viewModel.loadProfiles() }
            }
        }
    }
}

/// Individual profile card with avatar and name.
struct ProfileCardView: View {
    let profile: ChildProfile
    let subtitle: String?
    let onSelect: () -> Void

    @FocusState private var isFocused: Bool

    var body: some View {
        Button(action: onSelect) {
            VStack(spacing: 16) {
                avatarView
                    .frame(width: 120, height: 120)
                    .clipShape(Circle())
                    .background(
                        Circle()
                            .fill(Color.accentColor.opacity(isFocused ? 0.4 : 0.2))
                    )

                VStack(spacing: 6) {
                    Text(profile.name)
                        .font(.headline)
                        .foregroundColor(.primary)
                        .lineLimit(1)

                    if let subtitle {
                        Text(subtitle)
                            .font(.caption)
                            .foregroundColor(AppTheme.textSecondary)
                            .lineLimit(1)
                    }
                }
            }
            .padding(20)
            .scaleEffect(isFocused ? 1.1 : 1.0)
            .animation(.easeInOut(duration: 0.15), value: isFocused)
        }
        .buttonStyle(.plain)
        .focused($isFocused)
    }

    @ViewBuilder
    private var avatarView: some View {
        if let url = profile.avatarURL {
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let image):
                    image
                        .resizable()
                        .scaledToFill()
                case .failure:
                    Text(fallbackEmoji)
                        .font(.system(size: 64))
                default:
                    ProgressView()
                }
            }
        } else {
            Text(profile.avatar)
                .font(.system(size: 64))
        }
    }

    private var fallbackEmoji: String {
        "👤"
    }
}

// MARK: - ViewModel

@MainActor
final class ProfilePickerViewModel: ObservableObject {
    @Published var profiles: [ChildProfile] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    private let apiClient: APIClient

    init(apiClient: APIClient = APIClient()) {
        self.apiClient = apiClient
    }

    func loadProfiles() async {
        isLoading = true
        errorMessage = nil
        do {
            profiles = try await apiClient.getProfiles()
        } catch {
            errorMessage = "Could not load profiles.\n\(error.localizedDescription)"
        }
        isLoading = false
    }
}
