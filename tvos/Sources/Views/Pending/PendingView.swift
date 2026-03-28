import SwiftUI

/// "Waiting for approval" screen that polls the server for status changes.
/// Navigates to player on approval, or shows denied message on denial.
struct PendingView: View {
    let videoId: String
    let videoTitle: String
    let child: ChildProfile
    let onApproved: (String) -> Void
    let onDenied: () -> Void
    let onCancel: () -> Void

    @StateObject private var viewModel = PendingViewModel()

    var body: some View {
        VStack(spacing: 30) {
            // Animated waiting indicator
            ZStack {
                Circle()
                    .stroke(Color.accentColor.opacity(0.2), lineWidth: 4)
                    .frame(width: 100, height: 100)

                if viewModel.isPolling {
                    Circle()
                        .trim(from: 0, to: 0.3)
                        .stroke(Color.accentColor, style: StrokeStyle(lineWidth: 4, lineCap: .round))
                        .frame(width: 100, height: 100)
                        .rotationEffect(.degrees(viewModel.rotationAngle))
                        .animation(
                            .linear(duration: 1.0).repeatForever(autoreverses: false),
                            value: viewModel.rotationAngle
                        )
                }

                Image(systemName: "clock.badge.questionmark")
                    .font(.system(size: 36))
                    .foregroundColor(.accentColor)
            }

            Text("Waiting for Approval")
                .font(.title2)
                .fontWeight(.bold)
                .foregroundColor(.white)

            Text("\"\(videoTitle)\"")
                .font(.headline)
                .foregroundColor(AppTheme.textSecondary)
                .lineLimit(2)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 80)

            Text("A parent has been notified.\nPlease wait for approval.")
                .font(.callout)
                .foregroundColor(AppTheme.textSecondary)
                .multilineTextAlignment(.center)

            Button("Cancel", action: onCancel)
                .buttonStyle(.bordered)
        }
        .padding(60)
        .background(Color(white: 0.12).opacity(0.95))
        .cornerRadius(24)
        .shadow(color: .black.opacity(0.5), radius: 20)
        .frame(maxWidth: 800)
        .task {
            viewModel.startPolling(videoId: videoId, childId: child.id)
        }
        .onDisappear {
            viewModel.stopPolling()
        }
        .onChange(of: viewModel.currentStatus) { _, newStatus in
            switch newStatus {
            case "approved":
                viewModel.stopPolling()
                onApproved(videoId)
            case "denied":
                viewModel.stopPolling()
                onDenied()
            default:
                break
            }
        }
    }
}

// MARK: - ViewModel

@MainActor
final class PendingViewModel: ObservableObject {
    @Published var currentStatus: String = "pending"
    @Published var isPolling = false
    @Published var rotationAngle: Double = 0

    private let apiClient: APIClient
    private var pollTask: Task<Void, Never>?

    init(apiClient: APIClient = APIClient()) {
        self.apiClient = apiClient
    }

    func startPolling(videoId: String, childId: Int) {
        stopPolling()
        isPolling = true
        rotationAngle = 360 // Trigger animation

        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: UInt64(Config.pollInterval * 1_000_000_000))
                guard !Task.isCancelled else { break }

                do {
                    let status = try await self?.apiClient.getVideoStatus(
                        videoId: videoId,
                        childId: childId
                    )
                    if let status {
                        self?.currentStatus = status
                        if status != "pending" { break }
                    }
                } catch {
                    // Network errors during polling are non-fatal; keep polling.
                }
            }
        }
    }

    func stopPolling() {
        pollTask?.cancel()
        pollTask = nil
        isPolling = false
    }

    deinit {
        pollTask?.cancel()
    }
}
