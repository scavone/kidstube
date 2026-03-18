import SwiftUI

/// "Time limit reached" screen shown when the child's daily watch time is exceeded.
struct TimesUpView: View {
    let childName: String
    let childId: Int
    let onBack: () -> Void
    let onTimeGranted: () -> Void

    @StateObject private var timeRequest = TimeRequestService()

    var body: some View {
        VStack(spacing: 30) {
            Spacer()

            Image(systemName: "hourglass.bottomhalf.filled")
                .font(.system(size: 80))
                .foregroundColor(.orange)

            Text("Time's Up!")
                .font(.largeTitle)
                .fontWeight(.bold)

            Text("Great watching, \(childName)!")
                .font(.title3)
                .foregroundColor(.secondary)

            timeRequestContent

            Spacer()
        }
        .padding(60)
        .onAppear {
            if childId > 0 {
                timeRequest.checkStatus(childId: childId)
            }
        }
    }

    @ViewBuilder
    private var timeRequestContent: some View {
        switch timeRequest.status {
        case .idle:
            VStack(spacing: 20) {
                Text("You've used all your screen time for today.\nCome back tomorrow!")
                    .font(.callout)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)

                Spacer()

                if childId > 0 {
                    Button {
                        timeRequest.requestMoreTime(childId: childId)
                    } label: {
                        HStack {
                            Image(systemName: "clock.badge.questionmark")
                            Text("Ask for More Time")
                        }
                    }
                    .buttonStyle(.bordered)
                }

                Button("OK", action: onBack)
                    .buttonStyle(.borderedProminent)
            }
        case .requesting, .pending:
            VStack(spacing: 20) {
                Spacer()
                ProgressView()
                    .scaleEffect(1.5)
                Text("Waiting for a response...")
                    .font(.title3)
                    .foregroundColor(.secondary)
            }
        case .granted(let bonus):
            VStack(spacing: 20) {
                Spacer()
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 48))
                    .foregroundColor(.green)
                Text("You got \(bonus) more minutes!")
                    .font(.title2)
                Button("Continue Watching", action: onTimeGranted)
                    .buttonStyle(.borderedProminent)
            }
        case .denied:
            VStack(spacing: 20) {
                Text("Maybe tomorrow!")
                    .font(.title2)
                    .foregroundColor(.secondary)

                Spacer()

                Button("OK", action: onBack)
                    .buttonStyle(.borderedProminent)
            }
        }
    }
}

/// "Outside schedule" screen shown when it's not within the allowed viewing window.
struct OutsideScheduleView: View {
    let unlockTime: String
    let onBack: () -> Void

    var body: some View {
        VStack(spacing: 30) {
            Spacer()

            Image(systemName: "moon.stars")
                .font(.system(size: 80))
                .foregroundColor(.indigo)

            Text("Not Viewing Time")
                .font(.largeTitle)
                .fontWeight(.bold)

            if !unlockTime.isEmpty {
                Text("Videos will be available at \(unlockTime)")
                    .font(.title3)
                    .foregroundColor(.secondary)
            }

            Text("It's time for other activities.\nSee you later!")
                .font(.callout)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)

            Spacer()

            Button("OK", action: onBack)
                .buttonStyle(.borderedProminent)

            Spacer()
        }
        .padding(60)
    }
}
