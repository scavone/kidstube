import SwiftUI
import AVKit

/// Full-screen video player wrapping AVPlayerViewController.
/// - Fetches a fresh stream URL from the server
/// - Uses native tvOS playback controls (play/pause/scrub via Siri Remote)
/// - Runs heartbeat timer for watch time tracking
/// - Monitors time limits and schedule windows
struct PlayerView: View {
    let videoId: String
    let videoTitle: String
    let child: ChildProfile
    let onTimesUp: () -> Void
    let onOutsideSchedule: () -> Void
    let onDismiss: () -> Void

    @StateObject private var viewModel = PlayerViewModel()

    var body: some View {
        ZStack {
            if viewModel.isLoading {
                loadingState
            } else if let errorMessage = viewModel.errorMessage {
                errorState(errorMessage)
            } else if let player = viewModel.player {
                playerContent(player)
            }
        }
        .task {
            await viewModel.loadAndPlay(
                videoId: videoId,
                childId: child.id
            )
        }
        .onDisappear {
            viewModel.cleanup()
        }
        .onChange(of: viewModel.heartbeat.isTimeExceeded) { _, exceeded in
            if exceeded {
                viewModel.pause()
                onTimesUp()
            }
        }
        .onChange(of: viewModel.heartbeat.isOutsideSchedule) { _, outside in
            if outside {
                viewModel.pause()
                onOutsideSchedule()
            }
        }
    }

    // MARK: - Loading

    private var loadingState: some View {
        VStack(spacing: 20) {
            ProgressView()
                .scaleEffect(1.5)
            Text("Loading video...")
                .font(.headline)
                .foregroundColor(.secondary)
        }
    }

    // MARK: - Error

    private func errorState(_ message: String) -> some View {
        VStack(spacing: 20) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 48))
                .foregroundColor(.orange)
            Text("Couldn't play video")
                .font(.headline)
            Text(message)
                .font(.callout)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 80)

            HStack(spacing: 30) {
                Button("Retry") {
                    Task {
                        await viewModel.loadAndPlay(videoId: videoId, childId: child.id)
                    }
                }
                .buttonStyle(.borderedProminent)

                Button("Go Back", action: onDismiss)
                    .buttonStyle(.bordered)
            }
        }
    }

    // MARK: - Player

    private func playerContent(_ player: AVPlayer) -> some View {
        ZStack(alignment: .topTrailing) {
            AVPlayerViewControllerRepresentable(player: player)
                .ignoresSafeArea()

            // Time remaining overlay
            PlayerOverlayView(heartbeat: viewModel.heartbeat)
                .padding(30)
        }
    }
}

// MARK: - AVPlayerViewController SwiftUI Wrapper

struct AVPlayerViewControllerRepresentable: UIViewControllerRepresentable {
    let player: AVPlayer

    func makeUIViewController(context: Context) -> AVPlayerViewController {
        let controller = AVPlayerViewController()
        controller.player = player
        controller.allowsPictureInPicturePlayback = false
        return controller
    }

    func updateUIViewController(_ controller: AVPlayerViewController, context: Context) {
        controller.player = player
    }
}

// MARK: - ViewModel

@MainActor
final class PlayerViewModel: ObservableObject {
    @Published var player: AVPlayer?
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var heartbeat = HeartbeatService()

    private let apiClient: APIClient

    init(apiClient: APIClient = APIClient()) {
        self.apiClient = apiClient
    }

    func loadAndPlay(videoId: String, childId: Int) async {
        isLoading = true
        errorMessage = nil

        do {
            let streamUrl = try await apiClient.getStreamURL(videoId: videoId, childId: childId)
            guard let url = URL(string: streamUrl) else {
                errorMessage = "Invalid stream URL"
                isLoading = false
                return
            }

            let avPlayer = AVPlayer(url: url)
            self.player = avPlayer
            avPlayer.play()

            // Start heartbeat tracking
            heartbeat.start(videoId: videoId, childId: childId)
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    func pause() {
        player?.pause()
        heartbeat.stop()
    }

    func cleanup() {
        player?.pause()
        player = nil
        heartbeat.stop()
    }

    deinit {
        player?.pause()
        heartbeat.stop()
    }
}
