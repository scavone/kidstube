import Foundation

/// Status of a time request from the child to the parent.
enum TimeRequestStatus: Equatable {
    case idle
    case requesting
    case pending
    case granted(bonusMinutes: Int)
    case denied
}

/// Manages the "request more time" flow — POST + polling.
@MainActor
final class TimeRequestService: ObservableObject {
    @Published var status: TimeRequestStatus = .idle

    private let apiClient: APIClient
    private var pollTask: Task<Void, Never>?

    init(apiClient: APIClient = APIClient()) {
        self.apiClient = apiClient
    }

    /// Request more time and start polling for a response.
    func requestMoreTime(childId: Int, videoId: String? = nil) {
        guard status == .idle || status == .denied else { return }
        status = .requesting

        pollTask?.cancel()
        pollTask = Task { [weak self] in
            guard let self else { return }
            do {
                let response = try await self.apiClient.requestMoreTime(childId: childId, videoId: videoId)
                guard !Task.isCancelled else { return }
                if response.status == "granted" {
                    self.status = .granted(bonusMinutes: response.bonusMinutes)
                    return
                }
                self.status = .pending
                self.startPolling(childId: childId)
            } catch {
                self.status = .idle
            }
        }
    }

    /// Start polling for status updates (called after POST succeeds).
    func startPolling(childId: Int) {
        pollTask?.cancel()
        pollTask = Task { [weak self] in
            guard let self else { return }
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 3 * 1_000_000_000)
                guard !Task.isCancelled else { break }
                do {
                    let response = try await self.apiClient.getTimeRequestStatus(childId: childId)
                    guard !Task.isCancelled else { break }
                    switch response.status {
                    case "granted":
                        self.status = .granted(bonusMinutes: response.bonusMinutes)
                        return
                    case "denied":
                        self.status = .denied
                        return
                    case "pending":
                        continue
                    default:
                        self.status = .idle
                        return
                    }
                } catch {
                    // Network errors during polling are non-fatal; keep trying.
                }
            }
        }
    }

    /// Check current status once (e.g. on screen appear to catch approval during transition).
    func checkStatus(childId: Int) {
        Task { [weak self] in
            guard let self else { return }
            do {
                let response = try await self.apiClient.getTimeRequestStatus(childId: childId)
                switch response.status {
                case "granted":
                    self.status = .granted(bonusMinutes: response.bonusMinutes)
                case "denied":
                    self.status = .denied
                case "pending":
                    self.status = .pending
                    self.startPolling(childId: childId)
                default:
                    break
                }
            } catch {
                // Non-critical
            }
        }
    }

    func reset() {
        pollTask?.cancel()
        pollTask = nil
        status = .idle
    }

    deinit {
        pollTask?.cancel()
    }
}
