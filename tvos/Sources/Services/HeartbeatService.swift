import Foundation

/// Manages periodic heartbeat reporting during video playback.
/// Reports watch seconds to the server and monitors time limits.
@MainActor
final class HeartbeatService: ObservableObject {
    @Published var remainingSeconds: Int = -1
    @Published var isOutsideSchedule: Bool = false
    @Published var isTimeExceeded: Bool = false

    private let apiClient: APIClient
    private var task: Task<Void, Never>?
    private var videoId: String = ""
    private var childId: Int = 0

    init(apiClient: APIClient = APIClient()) {
        self.apiClient = apiClient
    }

    /// Start sending heartbeats for a video.
    func start(videoId: String, childId: Int) {
        stop()
        self.videoId = videoId
        self.childId = childId
        self.isTimeExceeded = false
        self.isOutsideSchedule = false

        task = Task { [weak self] in
            guard let self else { return }
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: UInt64(Config.heartbeatInterval * 1_000_000_000))
                guard !Task.isCancelled else { break }
                await self.sendHeartbeat()
            }
        }
    }

    /// Stop sending heartbeats.
    func stop() {
        task?.cancel()
        task = nil
    }

    /// Send a single heartbeat and update state based on response.
    private func sendHeartbeat() async {
        do {
            let remaining = try await apiClient.sendHeartbeat(
                videoId: videoId,
                childId: childId,
                seconds: Config.heartbeatSeconds
            )
            self.remainingSeconds = remaining

            if remaining == -2 {
                self.isOutsideSchedule = true
            } else if remaining == 0 {
                self.isTimeExceeded = true
            }
        } catch {
            // Network errors during heartbeat are non-fatal; playback continues.
            // The next heartbeat will retry.
        }
    }

}
