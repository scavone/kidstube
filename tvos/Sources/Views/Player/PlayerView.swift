import SwiftUI
import AVKit

/// Full-screen video player wrapping AVPlayerViewController.
/// - Fetches a fresh stream URL from the server
/// - Uses native tvOS playback controls (play/pause/scrub via Siri Remote)
/// - Runs heartbeat timer for watch time tracking
/// - Saves playback position periodically and on exit for resume support
/// - Monitors time limits and schedule windows
/// - Sets a precise cutoff timer based on the schedule end time
struct PlayerView: View {
    let video: Video
    let child: ChildProfile
    let onTimesUp: () -> Void
    let onOutsideSchedule: () -> Void
    let onDismiss: () -> Void

    @StateObject private var viewModel = PlayerViewModel()
    @State private var showResumePrompt: Bool = false
    @State private var resumeSeconds: Int = 0

    var body: some View {
        ZStack {
            if showResumePrompt {
                resumePrompt
            } else if viewModel.isLoading {
                loadingState
            } else if let errorMessage = viewModel.errorMessage {
                errorState(errorMessage)
            } else if let player = viewModel.player {
                playerContent(player)
            }
        }
        .task {
            // Always fetch latest position from server (catalog data may be stale)
            if let pos = await viewModel.fetchResumePosition(
                videoId: video.videoId, childId: child.id
            ) {
                resumeSeconds = pos
                showResumePrompt = true
            } else {
                await viewModel.loadAndPlay(
                    videoId: video.videoId,
                    childId: child.id,
                    resumePosition: nil
                )
            }
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
        .onChange(of: viewModel.scheduleCutoffReached) { _, reached in
            if reached {
                viewModel.pause()
                onOutsideSchedule()
            }
        }
    }

    // MARK: - Resume Prompt

    private var resumePrompt: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            VStack(spacing: 30) {
                Text(video.title)
                    .font(.title3)
                    .foregroundColor(.white)
                    .lineLimit(2)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 80)

                Text("You were watching this video")
                    .font(.headline)
                    .foregroundColor(.gray)

                HStack(spacing: 40) {
                    Button {
                        showResumePrompt = false
                        Task {
                            await viewModel.loadAndPlay(
                                videoId: video.videoId,
                                childId: child.id,
                                resumePosition: resumeSeconds
                            )
                        }
                    } label: {
                        VStack(spacing: 8) {
                            Image(systemName: "play.circle.fill")
                                .font(.system(size: 48))
                            Text("Resume from \(formatSeconds(resumeSeconds))")
                                .font(.callout)
                        }
                        .frame(width: 260, height: 120)
                    }
                    .buttonStyle(.borderedProminent)

                    Button {
                        showResumePrompt = false
                        Task {
                            await viewModel.loadAndPlay(
                                videoId: video.videoId,
                                childId: child.id,
                                resumePosition: nil
                            )
                        }
                    } label: {
                        VStack(spacing: 8) {
                            Image(systemName: "arrow.counterclockwise.circle.fill")
                                .font(.system(size: 48))
                            Text("Start Over")
                                .font(.callout)
                        }
                        .frame(width: 260, height: 120)
                    }
                    .buttonStyle(.bordered)
                }
            }
        }
    }

    // MARK: - Loading

    private var loadingState: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            VStack(spacing: 24) {
                ProgressView()
                    .scaleEffect(2.0)
                    .tint(.white)
                Text(video.title)
                    .font(.title3)
                    .foregroundColor(.white)
                    .lineLimit(2)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 80)
                Text("Loading video...")
                    .font(.callout)
                    .foregroundColor(.gray)
            }
        }
    }

    // MARK: - Error

    private func errorState(_ message: String) -> some View {
        ZStack {
            Color.black.ignoresSafeArea()

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
                            await viewModel.loadAndPlay(
                                videoId: video.videoId,
                                childId: child.id,
                                resumePosition: nil
                            )
                        }
                    }
                    .buttonStyle(.borderedProminent)

                    Button("Go Back", action: onDismiss)
                        .buttonStyle(.bordered)
                }
            }
        }
    }

    private func formatSeconds(_ total: Int) -> String {
        let hours = total / 3600
        let minutes = (total % 3600) / 60
        let seconds = total % 60
        if hours > 0 {
            return String(format: "%d:%02d:%02d", hours, minutes, seconds)
        }
        return String(format: "%d:%02d", minutes, seconds)
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
    @Published var isLoading = true
    @Published var errorMessage: String?
    @Published var heartbeat = HeartbeatService()
    @Published var scheduleCutoffReached = false

    private let apiClient: APIClient
    private var hlsSessionId: String?
    private var positionSaveTask: Task<Void, Never>?
    private var cutoffTask: Task<Void, Never>?
    private var videoId: String = ""
    private var childId: Int = 0

    init(apiClient: APIClient = APIClient()) {
        self.apiClient = apiClient
    }

    /// Fetch the latest watch position from the server.
    /// Returns the position in seconds if resumable, or nil.
    func fetchResumePosition(videoId: String, childId: Int) async -> Int? {
        do {
            let response = try await apiClient.getWatchPosition(videoId: videoId, childId: childId)
            let pos = response.watchPosition
            let dur = response.watchDuration
            guard pos >= 5, dur > 0, pos < dur - 5 else { return nil }
            return pos
        } catch {
            return nil
        }
    }

    func loadAndPlay(videoId: String, childId: Int, resumePosition: Int?) async {
        isLoading = true
        errorMessage = nil
        self.videoId = videoId
        self.childId = childId

        do {
            let (streamUrl, sessionId) = try await apiClient.getStreamURL(videoId: videoId, childId: childId)
            self.hlsSessionId = sessionId
            guard let url = URL(string: streamUrl) else {
                errorMessage = "Invalid stream URL"
                isLoading = false
                return
            }

            let avPlayer = AVPlayer(url: url)
            self.player = avPlayer

            // Seek to resume position if provided
            if let pos = resumePosition, pos > 0 {
                let targetTime = CMTime(seconds: Double(pos), preferredTimescale: 1)
                await avPlayer.seek(to: targetTime, toleranceBefore: .zero, toleranceAfter: CMTime(seconds: 2, preferredTimescale: 1))
            }

            avPlayer.play()

            // Start heartbeat tracking
            heartbeat.start(videoId: videoId, childId: childId)

            // Start periodic position saving (every 15 seconds)
            startPositionSaving()

            // Start schedule cutoff timer
            startScheduleCutoffTimer(childId: childId)
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    func pause() {
        player?.pause()
        heartbeat.stop()
        cutoffTask?.cancel()
        saveCurrentPosition()
    }

    func cleanup() {
        // Save position before tearing down
        saveCurrentPosition()
        positionSaveTask?.cancel()
        positionSaveTask = nil
        cutoffTask?.cancel()
        cutoffTask = nil
        player?.pause()
        player = nil
        heartbeat.stop()
        // Kill server-side ffmpeg immediately
        if let sessionId = hlsSessionId {
            let client = apiClient
            Task { await client.deleteHLSSession(sessionId: sessionId) }
            hlsSessionId = nil
        }
    }

    // MARK: - Schedule Cutoff Timer

    /// Fetch the schedule and set a precise timer to stop playback at the cutoff time.
    private func startScheduleCutoffTimer(childId: Int) {
        cutoffTask?.cancel()
        cutoffTask = Task { [weak self] in
            guard let self else { return }
            do {
                let schedule = try await self.apiClient.getScheduleStatus(childId: childId)
                guard !Task.isCancelled else { return }
                // Only set timer if currently allowed and there's a known end time
                guard schedule.allowed, schedule.minutesRemaining >= 0 else { return }
                let sleepNanos = UInt64(schedule.minutesRemaining) * 60 * 1_000_000_000
                if sleepNanos > 0 {
                    try await Task.sleep(nanoseconds: sleepNanos)
                }
                guard !Task.isCancelled else { return }
                self.scheduleCutoffReached = true
            } catch {
                // Non-critical — heartbeat will still catch outside-schedule
            }
        }
    }

    // MARK: - Position Saving

    private func startPositionSaving() {
        positionSaveTask?.cancel()
        positionSaveTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 15 * 1_000_000_000) // 15 seconds
                guard !Task.isCancelled else { break }
                self?.saveCurrentPosition()
            }
        }
    }

    private func saveCurrentPosition() {
        guard let player, !videoId.isEmpty, childId > 0 else { return }
        let currentTime = player.currentTime()
        let position = Int(currentTime.seconds)
        guard position > 0, currentTime.seconds.isFinite else { return }

        let totalDuration: Int
        if let dur = player.currentItem?.duration, dur.seconds.isFinite, dur.seconds > 0 {
            totalDuration = Int(dur.seconds)
        } else {
            totalDuration = 0
        }

        let vid = videoId
        let cid = childId
        let client = apiClient
        Task {
            await client.saveWatchPosition(
                videoId: vid, childId: cid,
                position: position, duration: totalDuration
            )
        }
    }
}
