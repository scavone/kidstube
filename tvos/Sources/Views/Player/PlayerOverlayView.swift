import SwiftUI

/// Semi-transparent time-remaining overlay shown on the player.
/// Auto-hides after a few seconds, reappears when remaining time is low.
struct PlayerOverlayView: View {
    @ObservedObject var heartbeat: HeartbeatService
    @State private var isVisible = true
    @State private var hideTask: Task<Void, Never>?

    var body: some View {
        Group {
            if shouldShow {
                badge
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .animation(.easeInOut(duration: 0.3), value: shouldShow)
        .onAppear {
            scheduleHide()
        }
        .onChange(of: heartbeat.remainingSeconds) { _, newValue in
            // Always show when time is running low (under 5 minutes)
            if newValue >= 0 && newValue <= 300 {
                isVisible = true
            }
        }
    }

    private var shouldShow: Bool {
        // Always show if time is low or exceeded
        if heartbeat.remainingSeconds >= 0 && heartbeat.remainingSeconds <= 300 {
            return true
        }
        // Show briefly on initial appearance, then hide
        return isVisible && heartbeat.remainingSeconds >= 0
    }

    private var badge: some View {
        HStack(spacing: 8) {
            Image(systemName: iconName)
                .font(.body)

            Text(displayText)
                .font(.body)
                .fontWeight(.semibold)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(backgroundColor)
        .cornerRadius(12)
    }

    private var iconName: String {
        if heartbeat.isTimeExceeded { return "exclamationmark.circle.fill" }
        if heartbeat.remainingSeconds <= 300 { return "clock.badge.exclamationmark" }
        return "clock"
    }

    private var displayText: String {
        let seconds = heartbeat.remainingSeconds
        if seconds < 0 { return "" }
        if seconds == 0 { return "Time's up!" }
        let hours = seconds / 3600
        let minutes = (seconds % 3600) / 60
        if hours > 0 { return "\(hours)h \(minutes)m left" }
        return "\(minutes)m left"
    }

    private var backgroundColor: Color {
        if heartbeat.isTimeExceeded { return .red.opacity(0.85) }
        if heartbeat.remainingSeconds <= 300 { return .orange.opacity(0.85) }
        return .black.opacity(0.6)
    }

    private func scheduleHide() {
        hideTask?.cancel()
        hideTask = Task {
            try? await Task.sleep(nanoseconds: UInt64(Config.overlayDisplayDuration * 1_000_000_000))
            guard !Task.isCancelled else { return }
            await MainActor.run { isVisible = false }
        }
    }
}
