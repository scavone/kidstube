import SwiftUI

/// "Waiting for channel approval" screen that polls the server for status changes.
struct ChannelPendingView: View {
    let channelId: String
    let channelName: String
    let child: ChildProfile
    let onApproved: () -> Void
    let onDenied: () -> Void
    let onCancel: () -> Void

    @StateObject private var viewModel = ChannelPendingViewModel()

    var body: some View {
        VStack(spacing: 30) {
            Spacer()

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

                Image(systemName: "tv.badge.ellipsis")
                    .font(.system(size: 36))
                    .foregroundColor(.accentColor)
            }

            Text("Waiting for Channel Approval")
                .font(.title2)
                .fontWeight(.bold)

            Text("\"\(channelName)\"")
                .font(.headline)
                .foregroundColor(.secondary)
                .lineLimit(2)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 80)

            Text("A parent has been notified.\nPlease wait for approval.")
                .font(.callout)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)

            Spacer()

            Button("Cancel", action: onCancel)
                .buttonStyle(.bordered)

            Spacer()
        }
        .padding(60)
        .task {
            viewModel.startPolling(channelId: channelId, childId: child.id)
        }
        .onDisappear {
            viewModel.stopPolling()
        }
        .onChange(of: viewModel.currentStatus) { _, newStatus in
            switch newStatus {
            case "approved":
                viewModel.stopPolling()
                onApproved()
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
final class ChannelPendingViewModel: ObservableObject {
    @Published var currentStatus: String = "pending"
    @Published var isPolling = false
    @Published var rotationAngle: Double = 0

    private let apiClient: APIClient
    private var pollTask: Task<Void, Never>?

    init(apiClient: APIClient = APIClient()) {
        self.apiClient = apiClient
    }

    func startPolling(channelId: String, childId: Int) {
        stopPolling()
        isPolling = true
        rotationAngle = 360

        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: UInt64(Config.pollInterval * 1_000_000_000))
                guard !Task.isCancelled else { break }

                do {
                    let status = try await self?.apiClient.getChannelRequestStatus(
                        channelId: channelId,
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
