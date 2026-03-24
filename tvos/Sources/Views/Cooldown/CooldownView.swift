import SwiftUI

/// Screen shown between viewing sessions when a cooldown period is active.
/// Displays a countdown to the next session and locks the app until it expires.
struct CooldownView: View {
    let sessionStatus: SessionStatus
    let onUnlock: () -> Void

    @State private var secondsRemaining: Int

    init(sessionStatus: SessionStatus, onUnlock: @escaping () -> Void) {
        self.sessionStatus = sessionStatus
        self.onUnlock = onUnlock
        self._secondsRemaining = State(initialValue: sessionStatus.cooldownRemainingSeconds ?? 0)
    }

    private var isExhausted: Bool { sessionStatus.sessionsExhausted == true }

    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()

            VStack(spacing: 40) {
                Spacer()

                Image(systemName: isExhausted ? "checkmark.seal.fill" : "pause.circle.fill")
                    .font(.system(size: 80))
                    .foregroundColor(isExhausted ? .green : .orange)

                Text(isExhausted ? "All done for today!" : "Time for a break!")
                    .font(.largeTitle)
                    .fontWeight(.bold)

                sessionProgressView

                if isExhausted {
                    Text("You've had a great watching session today!\nCome back tomorrow.")
                        .font(.title3)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                } else {
                    cooldownCountdownView
                }

                Spacer()
            }
            .padding(60)
        }
        .onReceive(Timer.publish(every: 1, on: .main, in: .common).autoconnect()) { _ in
            guard !isExhausted, secondsRemaining > 0 else { return }
            secondsRemaining -= 1
            if secondsRemaining == 0 {
                onUnlock()
            }
        }
    }

    @ViewBuilder
    private var sessionProgressView: some View {
        if let current = sessionStatus.currentSession,
           let max = sessionStatus.maxSessions {
            Text("Session \(current) of \(max) complete")
                .font(.title2)
                .foregroundColor(.secondary)
        }
    }

    @ViewBuilder
    private var cooldownCountdownView: some View {
        VStack(spacing: 16) {
            Text("Your next session starts in")
                .font(.title3)
                .foregroundColor(.secondary)

            if secondsRemaining > 0 {
                Text(formatCountdown(secondsRemaining))
                    .font(.system(size: 80, weight: .bold, design: .monospaced))
            } else {
                Text("Starting now...")
                    .font(.title2)
                    .foregroundColor(.green)
            }
        }
    }

    private func formatCountdown(_ seconds: Int) -> String {
        let m = seconds / 60
        let s = seconds % 60
        return String(format: "%02d:%02d", m, s)
    }
}
