import SwiftUI

/// "Video not approved" screen shown when a parent denies a video request.
struct DeniedView: View {
    let videoTitle: String
    let onBack: () -> Void

    var body: some View {
        VStack(spacing: 30) {
            Spacer()

            Image(systemName: "xmark.circle")
                .font(.system(size: 80))
                .foregroundColor(.red.opacity(0.8))

            Text("Not Approved")
                .font(.title2)
                .fontWeight(.bold)

            Text("\"\(videoTitle)\"")
                .font(.headline)
                .foregroundColor(.secondary)
                .lineLimit(2)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 80)

            Text("A parent didn't approve this video.\nTry a different one!")
                .font(.callout)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)

            Spacer()

            Button("Go Back", action: onBack)
                .buttonStyle(.borderedProminent)

            Spacer()
        }
        .padding(60)
    }
}
