import SwiftUI

/// Root view that manages navigation between all screens.
/// Uses a state-machine approach for clear, predictable screen flow.
struct ContentView: View {
    @State private var screen: AppScreen = .profilePicker
    @State private var selectedChild: ChildProfile?
    @State private var pendingVideoId: String?
    @State private var pendingVideoTitle: String?
    @State private var scheduleUnlockTime: String = ""
    @State private var playerItem: PlayerItem?
    @State private var catalogRefreshTrigger = 0

    var body: some View {
        ZStack {
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
                            refreshTrigger: catalogRefreshTrigger,
                            onVideoSelected: { video in
                                playVideo(video)
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
                                playVideoById(videoId: videoId, title: query)
                            },
                            onRequest: { result in
                                requestVideo(result)
                            },
                            onBrowseChannel: { channel in
                                screen = .channelDetail(channel: channel)
                            },
                            onBack: { screen = .home }
                        )
                    }

                case .channelDetail(let channel):
                    if let child = selectedChild {
                        ChannelDetailView(
                            channel: channel,
                            child: child,
                            onWatch: { videoId in
                                playVideoById(videoId: videoId, title: channel.name)
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
                                playVideoById(videoId: approvedId, title: title)
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
        .fullScreenCover(item: $playerItem) { item in
            PlayerView(
                video: item.video,
                child: item.child,
                onTimesUp: {
                    playerItem = nil
                    screen = .timesUp
                },
                onOutsideSchedule: {
                    playerItem = nil
                    screen = .outsideSchedule
                },
                onDismiss: {
                    playerItem = nil
                    catalogRefreshTrigger += 1
                }
            )
        }
    }

    // MARK: - Navigation Helpers

    /// Play a video from the catalog (carries watch position data for resume).
    private func playVideo(_ video: Video) {
        pendingVideoId = video.videoId
        pendingVideoTitle = video.title
        guard let child = selectedChild else { return }
        playerItem = PlayerItem(video: video, child: child)
    }

    /// Play a video by ID only (no watch position data — e.g. from search or pending).
    private func playVideoById(videoId: String, title: String) {
        let video = Video(videoId: videoId, title: title, channelName: "")
        playVideo(video)
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
                        playVideoById(videoId: result.videoId, title: result.title)
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

// MARK: - Player Item

struct PlayerItem: Identifiable {
    let id = UUID()
    let video: Video
    let child: ChildProfile
}

// MARK: - App Screen State

enum AppScreen: Equatable {
    case profilePicker
    case home
    case search(query: String)
    case channelDetail(channel: ChannelSearchResult)
    case pending
    case denied
    case timesUp
    case outsideSchedule
}
