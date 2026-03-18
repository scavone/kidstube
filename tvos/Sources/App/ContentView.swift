import SwiftUI

/// Root view that manages navigation between all screens.
/// Uses a state-machine approach for clear, predictable screen flow.
struct ContentView: View {
    @State private var screen: AppScreen = .profilePicker
    @State private var selectedChild: ChildProfile?
    @State private var pendingVideoId: String?
    @State private var pendingVideoTitle: String?
    @State private var pendingChannelName: String?
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
                            },
                            onOutsideSchedule: { unlockTime in
                                scheduleUnlockTime = unlockTime
                                screen = .outsideSchedule
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
                            onRequestChannel: { channel in
                                requestChannel(channel)
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

                case .channelPending(let channel):
                    if let child = selectedChild {
                        ChannelPendingView(
                            channelId: channel.channelId,
                            channelName: channel.name,
                            child: child,
                            onApproved: {
                                catalogRefreshTrigger += 1
                                screen = .home
                            },
                            onDenied: {
                                pendingChannelName = channel.name
                                screen = .denied
                            },
                            onCancel: { screen = .home }
                        )
                    }

                case .denied:
                    DeniedView(
                        videoTitle: pendingChannelName ?? pendingVideoTitle ?? "this video",
                        onBack: {
                            pendingChannelName = nil
                            screen = .home
                        }
                    )

                case .timesUp:
                    TimesUpView(
                        childName: selectedChild?.name ?? "",
                        onBack: { screen = .home }
                    )

                case .outsideSchedule:
                    OutsideScheduleView(
                        unlockTime: scheduleUnlockTime,
                        onBack: {
                            // Return to profile picker so another child can watch
                            selectedChild = nil
                            screen = .profilePicker
                        }
                    )
                }
            }
            .animation(.easeInOut(duration: 0.25), value: screen)
        }
        .fullScreenCover(item: $playerItem, onDismiss: {
            catalogRefreshTrigger += 1
        }) { item in
            PlayerView(
                video: item.video,
                child: item.child,
                onTimesUp: {
                    playerItem = nil
                    screen = .timesUp
                },
                onOutsideSchedule: {
                    playerItem = nil
                    scheduleUnlockTime = ""
                    screen = .outsideSchedule
                },
                onDismiss: {
                    playerItem = nil
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

    private func requestChannel(_ channel: ChannelSearchResult) {
        Task {
            let apiClient = APIClient()
            guard let child = selectedChild else { return }
            do {
                let response = try await apiClient.requestChannel(
                    channelId: channel.channelId,
                    childId: child.id
                )
                await MainActor.run {
                    if response.status == "approved" {
                        catalogRefreshTrigger += 1
                        screen = .home
                    } else if response.status == "denied" {
                        pendingChannelName = channel.name
                        screen = .denied
                    } else {
                        screen = .channelPending(channel: channel)
                    }
                }
            } catch {
                await MainActor.run { screen = .channelPending(channel: channel) }
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
    case channelPending(channel: ChannelSearchResult)
    case denied
    case timesUp
    case outsideSchedule
}
