import SwiftUI

/// Root view that manages navigation between all screens.
/// Uses a state-machine approach for clear, predictable screen flow.
struct ContentView: View {
    @State private var screen: AppScreen = .profilePicker
    @State private var selectedChild: ChildProfile?
    @State private var pendingVideoId: String?
    @State private var pendingVideoTitle: String?
    @State private var scheduleUnlockTime: String = ""

    var body: some View {
        Group {
            switch screen {
            case .profilePicker:
                ProfilePickerView { profile in
                    selectedChild = profile
                    screen = .home
                }

            case .home:
                if let child = selectedChild {
                    HomeView(
                        child: child,
                        onVideoSelected: { video in
                            playApprovedVideo(videoId: video.videoId, title: video.title)
                        },
                        onSearchSubmitted: { query in
                            screen = .search(query: query)
                        },
                        onSwitchProfile: {
                            selectedChild = nil
                            screen = .profilePicker
                        }
                    )
                }

            case .search(let query):
                if let child = selectedChild {
                    SearchResultsView(
                        query: query,
                        child: child,
                        onWatch: { videoId in
                            playApprovedVideo(videoId: videoId, title: query)
                        },
                        onRequest: { result in
                            requestVideo(result)
                        },
                        onBack: { screen = .home }
                    )
                }

            case .pending:
                if let child = selectedChild,
                   let videoId = pendingVideoId,
                   let title = pendingVideoTitle {
                    PendingView(
                        videoId: videoId,
                        videoTitle: title,
                        child: child,
                        onApproved: { approvedId in
                            playApprovedVideo(videoId: approvedId, title: title)
                        },
                        onDenied: {
                            screen = .denied
                        },
                        onCancel: { screen = .home }
                    )
                }

            case .denied:
                DeniedView(
                    videoTitle: pendingVideoTitle ?? "this video",
                    onBack: { screen = .home }
                )

            case .player:
                if let child = selectedChild,
                   let videoId = pendingVideoId {
                    PlayerView(
                        videoId: videoId,
                        videoTitle: pendingVideoTitle ?? "",
                        child: child,
                        onTimesUp: { screen = .timesUp },
                        onOutsideSchedule: {
                            screen = .outsideSchedule
                        },
                        onDismiss: { screen = .home }
                    )
                }

            case .timesUp:
                TimesUpView(
                    childName: selectedChild?.name ?? "",
                    onBack: { screen = .home }
                )

            case .outsideSchedule:
                OutsideScheduleView(
                    unlockTime: scheduleUnlockTime,
                    onBack: { screen = .home }
                )
            }
        }
        .animation(.easeInOut(duration: 0.25), value: screen)
    }

    // MARK: - Navigation Helpers

    private func playApprovedVideo(videoId: String, title: String) {
        pendingVideoId = videoId
        pendingVideoTitle = title
        screen = .player
    }

    private func requestVideo(_ result: SearchResult) {
        pendingVideoId = result.videoId
        pendingVideoTitle = result.title
        // Fire the request then navigate to pending
        Task {
            let apiClient = APIClient()
            guard let child = selectedChild else { return }
            do {
                let response = try await apiClient.requestVideo(
                    videoId: result.videoId,
                    childId: child.id
                )
                await MainActor.run {
                    if response.status == "approved" {
                        screen = .player
                    } else if response.status == "denied" {
                        screen = .denied
                    } else {
                        screen = .pending
                    }
                }
            } catch {
                // If request fails, still go to pending — it might already exist
                await MainActor.run { screen = .pending }
            }
        }
    }
}

// MARK: - App Screen State

enum AppScreen: Equatable {
    case profilePicker
    case home
    case search(query: String)
    case pending
    case denied
    case player
    case timesUp
    case outsideSchedule
}
