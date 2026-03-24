import SwiftUI

/// PIN entry screen shown after profile selection when PIN lock is enabled.
/// Supports 4–6 digit PINs with a numeric pad and shake animation on incorrect entry.
struct PinEntryView: View {
    let child: ChildProfile
    let onSuccess: () -> Void
    let onCancel: () -> Void

    @StateObject private var viewModel = PinEntryViewModel()

    private let maxDigits = 6

    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()

            VStack(spacing: 0) {
                // Profile info
                VStack(spacing: 12) {
                    profileAvatar
                        .frame(width: 100, height: 100)
                        .clipShape(Circle())
                        .overlay(
                            Circle()
                                .stroke(AppTheme.border, lineWidth: 2)
                        )

                    Text(child.name)
                        .font(.title3)
                        .fontWeight(.bold)
                        .foregroundColor(AppTheme.textPrimary)
                }
                .padding(.top, 60)
                .padding(.bottom, 32)

                Text("Enter PIN")
                    .font(.title2)
                    .fontWeight(.semibold)
                    .foregroundColor(AppTheme.textPrimary)
                    .padding(.bottom, 32)

                // PIN dots
                pinDots
                    .offset(x: viewModel.shakeOffset)
                    .padding(.bottom, 40)

                // Error message
                Text(viewModel.errorMessage ?? " ")
                    .font(.callout)
                    .foregroundColor(.red)
                    .padding(.bottom, 24)

                // Numeric pad
                numericPad
                    .padding(.bottom, 32)

                // Action buttons
                HStack(spacing: 24) {
                    Button("Back") {
                        onCancel()
                    }
                    .buttonStyle(.bordered)

                    Button(action: {
                        Task { await viewModel.submitPin(childId: child.id) }
                    }) {
                        HStack(spacing: 8) {
                            if viewModel.isVerifying {
                                ProgressView()
                                    .scaleEffect(0.7)
                            }
                            Text("OK")
                                .fontWeight(.semibold)
                        }
                        .frame(minWidth: 100)
                    }
                    .disabled(viewModel.enteredDigits.count < 4 || viewModel.isVerifying)
                }

                Spacer()
            }
        }
        .onChange(of: viewModel.isVerified) {
            if viewModel.isVerified {
                SessionManager.authenticate(
                    childId: child.id,
                    token: viewModel.sessionToken ?? ""
                )
                onSuccess()
            }
        }
    }

    // MARK: - PIN Dots

    private var pinDots: some View {
        HStack(spacing: 16) {
            ForEach(0..<maxDigits, id: \.self) { index in
                if index < viewModel.enteredDigits.count {
                    // Filled dot
                    Circle()
                        .fill(Color.accentColor)
                        .frame(width: 24, height: 24)
                        .overlay(
                            Circle()
                                .stroke(Color.accentColor, lineWidth: 2)
                        )
                        .scaleEffect(1.15)
                } else if index < 4 {
                    // Required position (first 4) — always shown
                    Circle()
                        .fill(AppTheme.surface)
                        .frame(width: 24, height: 24)
                        .overlay(
                            Circle()
                                .stroke(AppTheme.border, lineWidth: 2)
                        )
                } else {
                    // Optional position (5–6) — only shown if digits reach here
                    Circle()
                        .fill(AppTheme.surface)
                        .frame(width: 24, height: 24)
                        .overlay(
                            Circle()
                                .stroke(AppTheme.border.opacity(0.4), lineWidth: 1)
                        )
                        .opacity(viewModel.enteredDigits.count >= index ? 1.0 : 0.3)
                }
            }
        }
        .animation(.easeOut(duration: 0.15), value: viewModel.enteredDigits.count)
    }

    // MARK: - Numeric Pad

    private var numericPad: some View {
        VStack(spacing: 16) {
            ForEach(0..<3, id: \.self) { row in
                HStack(spacing: 16) {
                    ForEach(1...3, id: \.self) { col in
                        let digit = row * 3 + col
                        digitButton(digit)
                    }
                }
            }
            // Bottom row: delete, 0, spacer
            HStack(spacing: 16) {
                deleteButton
                digitButton(0)
                // Invisible spacer to balance the layout
                Color.clear
                    .frame(width: 100, height: 72)
            }
        }
    }

    private func digitButton(_ digit: Int) -> some View {
        Button(action: {
            viewModel.enterDigit(digit)
        }) {
            Text("\(digit)")
                .font(.system(size: 36, weight: .medium, design: .rounded))
                .foregroundColor(AppTheme.textPrimary)
                .frame(width: 100, height: 72)
                .background(
                    RoundedRectangle(cornerRadius: 14)
                        .fill(AppTheme.surface)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 14)
                        .stroke(AppTheme.border, lineWidth: 1)
                )
        }
        .buttonStyle(.plain)
        .disabled(viewModel.enteredDigits.count >= maxDigits || viewModel.isVerifying)
    }

    private var deleteButton: some View {
        Button(action: {
            viewModel.deleteDigit()
        }) {
            Image(systemName: "delete.left")
                .font(.system(size: 28))
                .foregroundColor(AppTheme.textSecondary)
                .frame(width: 100, height: 72)
                .background(
                    RoundedRectangle(cornerRadius: 14)
                        .fill(AppTheme.surface)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 14)
                        .stroke(AppTheme.border, lineWidth: 1)
                )
        }
        .buttonStyle(.plain)
        .disabled(viewModel.enteredDigits.isEmpty || viewModel.isVerifying)
    }

    // MARK: - Avatar

    @ViewBuilder
    private var profileAvatar: some View {
        if let url = child.avatarURL {
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let image):
                    image.resizable().scaledToFill()
                case .failure:
                    Text(child.avatar).font(.system(size: 48))
                default:
                    ProgressView()
                }
            }
        } else {
            Text(child.avatar).font(.system(size: 48))
        }
    }
}

// MARK: - ViewModel

@MainActor
final class PinEntryViewModel: ObservableObject {
    @Published var enteredDigits: [Int] = []
    @Published var errorMessage: String?
    @Published var isVerifying = false
    @Published var isVerified = false
    @Published var shakeOffset: CGFloat = 0
    var sessionToken: String?

    private let apiClient = APIClient()

    func enterDigit(_ digit: Int) {
        guard enteredDigits.count < 6 else { return }
        enteredDigits.append(digit)
        errorMessage = nil
    }

    func deleteDigit() {
        guard !enteredDigits.isEmpty else { return }
        enteredDigits.removeLast()
        errorMessage = nil
    }

    func submitPin(childId: Int) async {
        guard enteredDigits.count >= 4 else { return }
        await verifyPin(childId: childId)
    }

    private func verifyPin(childId: Int) async {
        let pin = enteredDigits.map(String.init).joined()
        isVerifying = true
        errorMessage = nil

        do {
            let response = try await apiClient.verifyPin(childId: childId, pin: pin)
            if response.success {
                sessionToken = response.sessionToken
                isVerified = true
            } else {
                await shakeAndReset()
            }
        } catch {
            await shakeAndReset()
        }

        isVerifying = false
    }

    private func shakeAndReset() async {
        errorMessage = "Wrong PIN — try again"

        // Shake animation
        withAnimation(.default) { shakeOffset = -12 }
        try? await Task.sleep(nanoseconds: 80_000_000)
        withAnimation(.default) { shakeOffset = 12 }
        try? await Task.sleep(nanoseconds: 80_000_000)
        withAnimation(.default) { shakeOffset = -8 }
        try? await Task.sleep(nanoseconds: 80_000_000)
        withAnimation(.default) { shakeOffset = 8 }
        try? await Task.sleep(nanoseconds: 80_000_000)
        withAnimation(.default) { shakeOffset = 0 }

        // Brief pause then clear digits for retry
        try? await Task.sleep(nanoseconds: 300_000_000)
        enteredDigits = []
    }
}
