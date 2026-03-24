import SwiftUI

/// Root view that manages navigation between all screens.
/// Shows pairing screen if no credentials exist, then profile picker, then sidebar + content.
struct ContentView: View {
    @State private var isPaired: Bool = CredentialStore.isPaired
    @State private var selectedChild: ChildProfile?
    @State private var sidebarSection: SidebarSection = .home
    @State private var pendingVideoId: String?
    @State private var pendingVideoTitle: String?
    @State private var pendingChannelName: String?
    @State private var scheduleUnlockTime: String = ""
    @State private var playerItem: PlayerItem?
    @State private var catalogRefreshTrigger = 0
    @State private var overlayScreen: OverlayScreen?
    @State private var timeStatus: TimeStatus?
    @State private var sessionStatus: SessionStatus?
    @State private var browsingChannel: ChannelSearchResult?
    @State private var pinGateState: PinGateState = .authenticated
    @State private var suppressAutoSelect = false

    var body: some View {
        Group {
            if !isPaired {
                PairingView(onPaired: {
                    isPaired = true
                })
            } else if let child = selectedChild {
                switch pinGateState {
                case .checking:
                    pinCheckingView(child: child)
                case .pinRequired:
                    PinEntryView(
                        child: child,
                        onSuccess: {
                            suppressAutoSelect = false
                            pinGateState = .authenticated
                        },
                        onCancel: {
                            suppressAutoSelect = true
                            selectedChild = nil
                        }
                    )
                case .authenticated:
                    mainAppLayout(child: child)
                }
            } else {
                ProfilePickerView(
                    suppressAutoSelect: suppressAutoSelect
                ) { profile in
                    selectedChild = profile
                }
            }
        }
        .onChange(of: selectedChild?.id) {
            // Reset to Home tab when switching profiles
            sidebarSection = .home
            browsingChannel = nil

            if let child = selectedChild {
                // Check PIN status for newly selected profile
                checkPinStatus(child: child)
            } else {
                // Returning to profile picker — clear session
                pinGateState = .authenticated
                SessionManager.clearAll()
            }
        }
        .fullScreenCover(item: $playerItem, onDismiss: {
            catalogRefreshTrigger += 1
        }) { item in
            PlayerView(
                video: item.video,
                child: item.child,
                onTimesUp: {
                    handleTimesUp(child: item.child)
                },
                onOutsideSchedule: {
                    playerItem = nil
                    scheduleUnlockTime = ""
                    overlayScreen = .outsideSchedule
                },
                onDismiss: {
                    playerItem = nil
                }
            )
        }
    }

    // MARK: - Main App Layout (Sidebar + Content)

    @ViewBuilder
    private func mainAppLayout(child: ChildProfile) -> some View {
        ZStack {
            HStack(spacing: 0) {
                // Sidebar
                SidebarView(
                    selection: $sidebarSection,
                    child: child,
                    timeStatus: timeStatus
                )
                .frame(width: AppTheme.sidebarWidth)

                // Main content
                ZStack {
                    AppTheme.background.ignoresSafeArea()
                    detailContent(child: child)
                }
                .focusSection()
            }
            .disabled(overlayScreen != nil)
            .blur(radius: overlayScreen != nil ? 5 : 0)

            // Overlay screens (pending, denied, timesUp, outsideSchedule)
            if let overlay = overlayScreen {
                overlayView(overlay, child: child)
                    .transition(.opacity)
            }
        }
        .animation(.easeInOut(duration: 0.25), value: overlayScreen)
        .task {
            await refreshTimeStatus(childId: child.id)
        }
        .task(id: child.id) {
            // Check session status on load, then every 30s
            await checkSessionStatus(childId: child.id)
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 30 * 1_000_000_000)
                guard !Task.isCancelled else { break }
                await checkSessionStatus(childId: child.id)
            }
        }
        .onChange(of: catalogRefreshTrigger) {
            Task { await refreshTimeStatus(childId: child.id) }
        }
        .onChange(of: sidebarSection) {
            // Touch session on navigation to keep it alive
            SessionManager.touch(childId: child.id)
        }
    }

    // MARK: - Detail Content

    @ViewBuilder
    private func detailContent(child: ChildProfile) -> some View {
        // Channel detail takes precedence when browsing
        if let channel = browsingChannel {
            ChannelDetailView(
                channel: channel,
                child: child,
                onWatch: { videoId in
                    playVideoById(videoId: videoId, title: channel.name)
                },
                onRequest: { result in
                    requestVideo(result)
                },
                onBack: { browsingChannel = nil }
            )
        } else {
            switch sidebarSection {
            case .home:
                HomeView(
                    child: child,
                    refreshTrigger: catalogRefreshTrigger,
                    onVideoSelected: { video in
                        playVideo(video)
                    },
                    onSearchSubmitted: { _ in
                        sidebarSection = .search
                    },
                    onSwitchProfile: {
                        selectedChild = nil
                    },
                    onOutsideSchedule: { unlockTime in
                        scheduleUnlockTime = unlockTime
                        overlayScreen = .outsideSchedule
                    }
                )

            case .channels:
                ChannelsListView(
                    child: child,
                    onChannelSelected: { homeChannel in
                        // Convert HomeChannel to ChannelSearchResult for detail view
                        let channel = ChannelSearchResult(
                            channelId: homeChannel.channelId ?? homeChannel.channelName,
                            name: homeChannel.channelName,
                            thumbnailUrl: homeChannel.thumbnailUrl
                        )
                        browsingChannel = channel
                    }
                )

            case .category(let category):
                CategoryContentView(
                    child: child,
                    category: category,
                    onVideoSelected: { video in
                        playVideo(video)
                    }
                )

            case .search:
                SidebarSearchView(
                    child: child,
                    onWatch: { videoId in
                        playVideoById(videoId: videoId, title: "")
                    },
                    onRequest: { result in
                        requestVideo(result)
                    },
                    onBrowseChannel: { channel in
                        browsingChannel = channel
                    },
                    onRequestChannel: { channel in
                        requestChannel(channel)
                    }
                )

            case .profile:
                ProfileView(
                    child: child,
                    timeStatus: timeStatus,
                    onSwitchProfile: {
                        selectedChild = nil
                    },
                    onUnpair: {
                        CredentialStore.clear()
                        selectedChild = nil
                        isPaired = false
                    }
                )
            }
        }
    }

    // MARK: - Overlay Screens

    @ViewBuilder
    private func overlayView(_ screen: OverlayScreen, child: ChildProfile) -> some View {
        switch screen {
        case .pending:
            if let videoId = pendingVideoId,
               let title = pendingVideoTitle {
                PendingView(
                    videoId: videoId,
                    videoTitle: title,
                    child: child,
                    onApproved: { approvedId in
                        overlayScreen = nil
                        playVideoById(videoId: approvedId, title: title)
                    },
                    onDenied: {
                        overlayScreen = .denied
                    },
                    onCancel: { overlayScreen = nil }
                )
            }

        case .channelPending(let channel):
            ChannelPendingView(
                channelId: channel.channelId,
                channelName: channel.name,
                child: child,
                onApproved: {
                    catalogRefreshTrigger += 1
                    overlayScreen = nil
                },
                onDenied: {
                    pendingChannelName = channel.name
                    overlayScreen = .denied
                },
                onCancel: { overlayScreen = nil }
            )

        case .denied:
            DeniedView(
                videoTitle: pendingChannelName ?? pendingVideoTitle ?? "this video",
                onBack: {
                    pendingChannelName = nil
                    overlayScreen = nil
                }
            )

        case .timesUp:
            TimesUpView(
                childName: child.name,
                childId: child.id,
                onBack: { overlayScreen = nil },
                onTimeGranted: { overlayScreen = nil }
            )

        case .outsideSchedule:
            OutsideScheduleView(
                unlockTime: scheduleUnlockTime,
                onBack: {
                    overlayScreen = nil
                    selectedChild = nil
                }
            )

        case .cooldown:
            if let status = sessionStatus {
                CooldownView(
                    sessionStatus: status,
                    onUnlock: {
                        overlayScreen = nil
                        Task { await checkSessionStatus(childId: child.id) }
                    }
                )
            }
        }
    }

    // MARK: - PIN Gate

    @ViewBuilder
    private func pinCheckingView(child: ChildProfile) -> some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()
            VStack(spacing: 16) {
                ProgressView()
                    .scaleEffect(1.2)
                Text(child.name)
                    .font(.callout)
                    .foregroundColor(AppTheme.textSecondary)
            }
        }
    }

    private func checkPinStatus(child: ChildProfile) {
        // If already has a valid session, skip PIN
        if SessionManager.isAuthenticated(childId: child.id) {
            pinGateState = .authenticated
            return
        }

        // Use inline pin_enabled from profiles endpoint if available
        if let pinEnabled = child.pinEnabled {
            pinGateState = pinEnabled ? .pinRequired : .authenticated
            return
        }

        // Fallback: fetch from dedicated endpoint
        pinGateState = .checking
        Task {
            let apiClient = APIClient()
            do {
                let status = try await apiClient.getPinStatus(childId: child.id)
                await MainActor.run {
                    if status.pinEnabled {
                        pinGateState = .pinRequired
                    } else {
                        pinGateState = .authenticated
                    }
                }
            } catch {
                // If we can't check, let them through (fail open)
                await MainActor.run {
                    pinGateState = .authenticated
                }
            }
        }
    }

    // MARK: - Navigation Helpers

    private func refreshTimeStatus(childId: Int) async {
        do {
            timeStatus = try await APIClient().getTimeStatus(childId: childId)
        } catch {
            // Non-critical
        }
    }

    private func checkSessionStatus(childId: Int) async {
        do {
            let status = try await APIClient().getSessionStatus(childId: childId)
            sessionStatus = status
            guard status.sessionsEnabled else { return }
            if status.inCooldown == true || status.sessionsExhausted == true {
                overlayScreen = .cooldown
            } else if overlayScreen == .cooldown {
                // Cooldown expired — return to normal browsing
                overlayScreen = nil
            }
        } catch {
            // Non-critical
        }
    }

    /// Handle time-up event from the player.
    /// Shows cooldown screen if sessions are active and a cooldown is pending,
    /// otherwise shows the standard time's-up screen.
    private func handleTimesUp(child: ChildProfile) {
        playerItem = nil
        Task {
            do {
                let status = try await APIClient().getSessionStatus(childId: child.id)
                sessionStatus = status
                if status.sessionsEnabled && (status.inCooldown == true || status.sessionsExhausted == true) {
                    overlayScreen = .cooldown
                } else {
                    overlayScreen = .timesUp
                }
            } catch {
                overlayScreen = .timesUp
            }
        }
    }

    /// Play a video from the catalog (carries watch position data for resume).
    private func playVideo(_ video: Video) {
        pendingVideoId = video.videoId
        pendingVideoTitle = video.title
        guard let child = selectedChild else { return }

        // Block playback immediately if a cooldown or exhausted session is already cached
        if let session = sessionStatus, session.sessionsEnabled {
            if session.inCooldown == true || session.sessionsExhausted == true {
                overlayScreen = .cooldown
                return
            }
        }

        Task {
            let apiClient = APIClient()
            do {
                let status = try await apiClient.getTimeStatus(childId: child.id)
                await MainActor.run {
                    if status.exceeded {
                        overlayScreen = .timesUp
                    } else {
                        playerItem = PlayerItem(video: video, child: child)
                    }
                }
            } catch {
                await MainActor.run {
                    playerItem = PlayerItem(video: video, child: child)
                }
            }
        }
    }

    /// Play a video by ID only (no watch position data).
    private func playVideoById(videoId: String, title: String) {
        let video = Video(videoId: videoId, title: title, channelName: "")
        playVideo(video)
    }

    private func requestVideo(_ result: SearchResult) {
        pendingVideoId = result.videoId
        pendingVideoTitle = result.title
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
                        overlayScreen = .denied
                    } else {
                        overlayScreen = .pending
                    }
                }
            } catch {
                await MainActor.run { overlayScreen = .pending }
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
                    } else if response.status == "denied" {
                        pendingChannelName = channel.name
                        overlayScreen = .denied
                    } else {
                        overlayScreen = .channelPending(channel: channel)
                    }
                }
            } catch {
                await MainActor.run { overlayScreen = .channelPending(channel: channel) }
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

// MARK: - Overlay Screen State

/// PIN gate state — tracks whether a profile needs PIN verification.
enum PinGateState {
    case checking       // Fetching pin-status from server
    case pinRequired    // PIN entry screen shown
    case authenticated  // Passed (or PIN disabled) — show main app
}

/// Screens that appear as overlays on top of the sidebar layout.
enum OverlayScreen: Equatable {
    case pending
    case channelPending(channel: ChannelSearchResult)
    case denied
    case timesUp
    case outsideSchedule
    case cooldown
}
