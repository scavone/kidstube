import SwiftUI

/// "Video not approved" screen shown when a parent denies a video request.
struct DeniedView: View {
    let videoTitle: String
    let onBack: () -> Void

    var body: some View {
        VStack(spacing: 30) {
            Image(systemName: "xmark.circle")
                .font(.system(size: 80))
                .foregroundColor(.red.opacity(0.8))

            Text("Not Approved")
                .font(.title2)
                .fontWeight(.bold)
                .foregroundColor(.white)

            Text("\"\(videoTitle)\"")
                .font(.headline)
                .foregroundColor(AppTheme.textSecondary)
                .lineLimit(2)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 80)

            Text("A parent didn't approve this video.\nTry a different one!")
                .font(.callout)
                .foregroundColor(AppTheme.textSecondary)
                .multilineTextAlignment(.center)

            Button("Go Back", action: onBack)
                .buttonStyle(.borderedProminent)
        }
        .padding(60)
        .background(Color(white: 0.12).opacity(0.95))
        .cornerRadius(24)
        .shadow(color: .black.opacity(0.5), radius: 20)
        .frame(maxWidth: 800)
    }
}
