import SwiftUI

/// "Time limit reached" screen shown when the child's daily watch time is exceeded.
struct TimesUpView: View {
    let childName: String
    let onBack: () -> Void

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

            Text("You've used all your screen time for today.\nCome back tomorrow!")
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
