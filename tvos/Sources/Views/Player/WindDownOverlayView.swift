import SwiftUI

/// Full-screen overlay shown when time expires mid-video.
/// Offers three choices: finish this video, ask for more time, or stop now.
struct WindDownOverlayView: View {
    let childId: Int
    let videoId: String
    let onStopNow: () -> Void
    let onFinishVideo: () -> Void
    let onTimeGranted: () -> Void

    @StateObject private var timeRequest = TimeRequestService()

    var body: some View {
        ZStack {
            Color.black.opacity(0.85)
                .ignoresSafeArea()

            VStack(spacing: 36) {
                Image(systemName: "hourglass.bottomhalf.filled")
                    .font(.system(size: 64))
                    .foregroundColor(.orange)

                Text("Time's Up!")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                    .foregroundColor(.white)

                mainContent
            }
        }
    }

    @ViewBuilder
    private var mainContent: some View {
        switch timeRequest.status {
        case .idle:
            choiceButtons
        case .requesting, .pending:
            VStack(spacing: 20) {
                ProgressView()
                    .scaleEffect(1.5)
                    .tint(.white)
                Text("Waiting for a response...")
                    .font(.title3)
                    .foregroundColor(.gray)
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
                    .foregroundColor(.secondary)

                HStack(spacing: 30) {
                    Button("Finish This Video", action: onFinishVideo)
                        .buttonStyle(.bordered)
                    Button("Stop Now", action: onStopNow)
                        .buttonStyle(.borderedProminent)
                        .tint(.red)
                }
            }
        }
    }

    private var choiceButtons: some View {
        VStack(spacing: 20) {
            Button(action: onFinishVideo) {
                HStack {
                    Image(systemName: "play.circle")
                    Text("Finish This Video")
                }
                .frame(width: 340, height: 60)
            }
            .buttonStyle(.borderedProminent)

            Button {
                timeRequest.requestMoreTime(childId: childId, videoId: videoId)
            } label: {
                HStack {
                    Image(systemName: "clock.badge.questionmark")
                    Text("Ask for More Time")
                }
                .frame(width: 340, height: 60)
            }
            .buttonStyle(.bordered)

            Button(action: onStopNow) {
                HStack {
                    Image(systemName: "stop.circle")
                    Text("Stop Now")
                }
                .frame(width: 340, height: 60)
            }
            .buttonStyle(.bordered)
            .tint(.red)
        }
    }
}
