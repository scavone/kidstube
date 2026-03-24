import SwiftUI

/// Profile screen shown from the sidebar — displays child info, time status, and switch profile option.
struct ProfileView: View {
    let child: ChildProfile
    let timeStatus: TimeStatus?
    let onSwitchProfile: () -> Void

    var body: some View {
        ScrollView {
            VStack(spacing: 40) {
                // Avatar + name
                VStack(spacing: 16) {
                    profileAvatar
                        .frame(width: 160, height: 160)
                        .clipShape(Circle())
                        .overlay(
                            Circle()
                                .stroke(AppTheme.border, lineWidth: 2)
                        )

                    Text(child.name)
                        .font(.title2)
                        .fontWeight(.bold)
                        .foregroundColor(AppTheme.textPrimary)
                }
                .padding(.top, 40)

                // Time status card
                if let time = timeStatus {
                    timeCard(time)
                }

                // Switch profile button
                Button(action: onSwitchProfile) {
                    Label("Switch Profile", systemImage: "person.2")
                        .font(.callout)
                        .fontWeight(.medium)
                }
                .buttonStyle(.bordered)
                .padding(.top, 20)

                Spacer()
            }
            .frame(maxWidth: .infinity)
            .padding(.horizontal, 60)
        }
    }

    @ViewBuilder
    private var profileAvatar: some View {
        if let url = child.avatarURL {
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let image):
                    image.resizable().scaledToFill()
                case .failure:
                    Text(child.avatar).font(.system(size: 80))
                default:
                    ProgressView()
                }
            }
        } else {
            Text(child.avatar).font(.system(size: 80))
        }
    }

    private func timeCard(_ status: TimeStatus) -> some View {
        VStack(spacing: 16) {
            HStack(spacing: 12) {
                Image(systemName: status.exceeded ? "exclamationmark.circle.fill" : "clock.fill")
                    .font(.title3)
                    .foregroundColor(status.exceeded ? .red : .accentColor)

                Text("Watch Time")
                    .font(.headline)
                    .foregroundColor(AppTheme.textPrimary)

                Spacer()

                Text(status.formattedRemaining)
                    .font(.title3)
                    .fontWeight(.bold)
                    .foregroundColor(status.exceeded ? .red : AppTheme.textPrimary)
            }

            if !status.isFreeDay && !status.exceeded {
                // Progress bar
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 4)
                            .fill(AppTheme.border)
                            .frame(height: 6)

                        RoundedRectangle(cornerRadius: 4)
                            .fill(progressColor(status))
                            .frame(width: max(0, geo.size.width * usedFraction(status)), height: 6)
                    }
                }
                .frame(height: 6)

                HStack {
                    Text("\(Int(status.usedMin))m watched")
                        .font(.caption)
                        .foregroundColor(AppTheme.textSecondary)
                    Spacer()
                    Text("\(status.limitMin)m limit")
                        .font(.caption)
                        .foregroundColor(AppTheme.textSecondary)
                }
            }
        }
        .padding(24)
        .background(
            RoundedRectangle(cornerRadius: AppTheme.cardCornerRadius)
                .fill(AppTheme.surface)
        )
        .frame(maxWidth: 500)
    }

    private func usedFraction(_ status: TimeStatus) -> Double {
        guard status.limitMin > 0 else { return 0 }
        return min(status.usedMin / Double(status.limitMin), 1.0)
    }

    private func progressColor(_ status: TimeStatus) -> Color {
        let fraction = usedFraction(status)
        if fraction > 0.9 { return .red }
        if fraction > 0.7 { return .orange }
        return .green
    }
}
