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
            Image(systemName: "hourglass.bottomhalf.filled")
                .font(.system(size: 80))
                .foregroundColor(.orange)

            Text("Time's Up!")
                .font(.largeTitle)
                .fontWeight(.bold)
                .foregroundColor(.white)

            Text("Great watching, \(childName)!")
                .font(.title3)
                .foregroundColor(AppTheme.textSecondary)

            timeRequestContent
        }
        .padding(60)
        .background(Color(white: 0.12).opacity(0.95))
        .cornerRadius(24)
        .shadow(color: .black.opacity(0.5), radius: 20)
        .frame(maxWidth: 800)
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
                    .foregroundColor(AppTheme.textSecondary)
                    .multilineTextAlignment(.center)

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
                ProgressView()
                    .scaleEffect(1.5)
                Text("Waiting for a response...")
                    .font(.title3)
                    .foregroundColor(AppTheme.textSecondary)
            }
        case .granted(let bonus):
            VStack(spacing: 20) {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 48))
                    .foregroundColor(.green)
                Text("You got \(bonus) more minutes!")
                    .font(.title2)
                    .foregroundColor(.white)
                Button("Continue Watching", action: onTimeGranted)
                    .buttonStyle(.borderedProminent)
            }
        case .denied:
            VStack(spacing: 20) {
                Text("Maybe tomorrow!")
                    .font(.title2)
                    .foregroundColor(AppTheme.textSecondary)

                Button("OK", action: onBack)
                    .buttonStyle(.borderedProminent)
            }
        }
    }
}

/// "Category time exhausted" screen shown when a per-category limit is reached.
struct CategoryTimesUpView: View {
    let categoryLabel: String
    let onBack: () -> Void

    var body: some View {
        VStack(spacing: 30) {
            Image(systemName: "clock.badge.xmark")
                .font(.system(size: 80))
                .foregroundColor(.orange)

            Text("No more \(categoryLabel) time today!")
                .font(.largeTitle)
                .fontWeight(.bold)
                .foregroundColor(.white)
                .multilineTextAlignment(.center)

            Text("You've used all your \(categoryLabel.lowercased()) time.\nTry another category or come back tomorrow!")
                .font(.callout)
                .foregroundColor(AppTheme.textSecondary)
                .multilineTextAlignment(.center)

            Button("OK", action: onBack)
                .buttonStyle(.borderedProminent)
        }
        .padding(60)
        .background(Color(white: 0.12).opacity(0.95))
        .cornerRadius(24)
        .shadow(color: .black.opacity(0.5), radius: 20)
        .frame(maxWidth: 800)
    }
}

/// "Outside schedule" screen shown when it's not within the allowed viewing window.
struct OutsideScheduleView: View {
    let unlockTime: String
    let onBack: () -> Void

    var body: some View {
        VStack(spacing: 30) {
            Image(systemName: "moon.stars")
                .font(.system(size: 80))
                .foregroundColor(.indigo)

            Text("Not Viewing Time")
                .font(.largeTitle)
                .fontWeight(.bold)
                .foregroundColor(.white)

            if !unlockTime.isEmpty {
                Text("Videos will be available at \(unlockTime)")
                    .font(.title3)
                    .foregroundColor(AppTheme.textSecondary)
            }

            Text("It's time for other activities.\nSee you later!")
                .font(.callout)
                .foregroundColor(AppTheme.textSecondary)
                .multilineTextAlignment(.center)

            Button("OK", action: onBack)
                .buttonStyle(.borderedProminent)
        }
        .padding(60)
        .background(Color(white: 0.12).opacity(0.95))
        .cornerRadius(24)
        .shadow(color: .black.opacity(0.5), radius: 20)
        .frame(maxWidth: 800)
    }
}
