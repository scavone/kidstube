import SwiftUI
import CoreImage.CIFilterBuiltins

/// First-launch pairing screen. Guides the user through:
/// 1. Entering the server URL
/// 2. Displaying a QR code (token) + PIN for the parent to confirm via Telegram
/// 3. Polling until confirmed, then storing credentials and proceeding
struct PairingView: View {
    let onPaired: () -> Void

    @StateObject private var viewModel = PairingViewModel()
    @FocusState private var isURLFieldFocused: Bool
    @FocusState private var isNameFieldFocused: Bool

    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()

            VStack(spacing: 0) {
                // App title
                VStack(spacing: 8) {
                    Image(systemName: "tv")
                        .font(.system(size: 48))
                        .foregroundColor(.accentColor)
                    Text(Config.appName)
                        .font(.largeTitle)
                        .fontWeight(.bold)
                        .foregroundColor(AppTheme.textPrimary)
                }
                .padding(.top, 60)
                .padding(.bottom, 40)

                switch viewModel.step {
                case .enterURL:
                    serverURLStep
                case .showCode:
                    pairingCodeStep
                case .denied:
                    deniedStep
                case .success:
                    successStep
                }

                Spacer()
            }
        }
        .animation(.easeInOut(duration: 0.3), value: viewModel.step)
    }

    // MARK: - Step 1: Server URL Entry

    private var serverURLStep: some View {
        VStack(spacing: 32) {
            Text("Connect to Server")
                .font(.title2)
                .fontWeight(.semibold)
                .foregroundColor(AppTheme.textPrimary)

            Text("Enter the address of your KidsTube server.\nAsk a parent if you're not sure.")
                .font(.callout)
                .foregroundColor(AppTheme.textSecondary)
                .multilineTextAlignment(.center)

            VStack(spacing: 16) {
                TextField("https://kidstube.example.com", text: $viewModel.serverURL)
                    .textFieldStyle(.plain)
                    .font(.body)
                    .padding(16)
                    .background(
                        RoundedRectangle(cornerRadius: 10)
                            .fill(AppTheme.surface)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 10)
                            .stroke(AppTheme.border, lineWidth: 1)
                    )
                    .focused($isURLFieldFocused)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                    .frame(maxWidth: 600)

                TextField("Apple TV", text: $viewModel.deviceName)
                    .textFieldStyle(.plain)
                    .font(.body)
                    .padding(16)
                    .background(
                        RoundedRectangle(cornerRadius: 10)
                            .fill(AppTheme.surface)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 10)
                            .stroke(AppTheme.border, lineWidth: 1)
                    )
                    .focused($isNameFieldFocused)
                    .frame(maxWidth: 600)
            }

            Button(action: {
                Task { await viewModel.startPairing() }
            }) {
                HStack(spacing: 8) {
                    if viewModel.isConnecting {
                        ProgressView()
                            .scaleEffect(0.8)
                    }
                    Text(viewModel.isConnecting ? "Connecting..." : "Connect")
                        .fontWeight(.semibold)
                }
                .frame(minWidth: 200)
            }
            .disabled(viewModel.serverURL.isEmpty || viewModel.isConnecting)

            if let error = viewModel.errorMessage {
                Text(error)
                    .font(.caption)
                    .foregroundColor(.red)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 40)
            }
        }
        .onAppear { isURLFieldFocused = true }
    }

    // MARK: - Step 2: QR Code + PIN

    private var pairingCodeStep: some View {
        VStack(spacing: 32) {
            Text("Pair This Device")
                .font(.title2)
                .fontWeight(.semibold)
                .foregroundColor(AppTheme.textPrimary)

            Text("A pairing request was sent to Telegram.\nYou can also scan the QR code to approve.")
                .font(.callout)
                .foregroundColor(AppTheme.textSecondary)
                .multilineTextAlignment(.center)

            HStack(spacing: 60) {
                // QR Code
                VStack(spacing: 16) {
                    if let qrImage = viewModel.qrCodeImage {
                        Image(uiImage: qrImage)
                            .interpolation(.none)
                            .resizable()
                            .scaledToFit()
                            .frame(width: 240, height: 240)
                            .background(Color.white)
                            .cornerRadius(12)
                    } else {
                        RoundedRectangle(cornerRadius: 12)
                            .fill(AppTheme.surface)
                            .frame(width: 240, height: 240)
                            .overlay(ProgressView())
                    }

                    Text("Scan with phone")
                        .font(.caption)
                        .foregroundColor(AppTheme.textMuted)
                }

                // Divider
                VStack(spacing: 12) {
                    Rectangle()
                        .fill(AppTheme.border)
                        .frame(width: 1, height: 60)
                    Text("OR")
                        .font(.caption)
                        .fontWeight(.bold)
                        .foregroundColor(AppTheme.textMuted)
                    Rectangle()
                        .fill(AppTheme.border)
                        .frame(width: 1, height: 60)
                }

                // PIN Code
                VStack(spacing: 16) {
                    Text("Verification PIN")
                        .font(.callout)
                        .foregroundColor(AppTheme.textSecondary)

                    if let pin = viewModel.pin {
                        HStack(spacing: 12) {
                            ForEach(Array(pin.enumerated()), id: \.offset) { _, char in
                                Text(String(char))
                                    .font(.system(size: 48, weight: .bold, design: .monospaced))
                                    .foregroundColor(AppTheme.textPrimary)
                                    .frame(width: 56, height: 72)
                                    .background(
                                        RoundedRectangle(cornerRadius: 10)
                                            .fill(AppTheme.surface)
                                    )
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 10)
                                            .stroke(AppTheme.border, lineWidth: 1)
                                    )
                            }
                        }
                    }

                    Text("approve in Telegram")
                        .font(.caption)
                        .foregroundColor(AppTheme.textMuted)
                }
            }

            // Status / timer
            HStack(spacing: 8) {
                ProgressView()
                    .scaleEffect(0.7)
                Text("Waiting for parent approval...")
                    .font(.caption)
                    .foregroundColor(AppTheme.textSecondary)
            }

            if viewModel.isExpiringSoon {
                Text("Code expires soon")
                    .font(.caption)
                    .foregroundColor(.orange)
            }

            Button("Cancel") {
                viewModel.cancelPairing()
            }
            .buttonStyle(.bordered)

            if let error = viewModel.errorMessage {
                Text(error)
                    .font(.caption)
                    .foregroundColor(.red)
                    .multilineTextAlignment(.center)
            }
        }
    }

    // MARK: - Denied

    private var deniedStep: some View {
        VStack(spacing: 24) {
            Image(systemName: "xmark.circle.fill")
                .font(.system(size: 80))
                .foregroundColor(.red)

            Text("Pairing Denied")
                .font(.title2)
                .fontWeight(.bold)
                .foregroundColor(AppTheme.textPrimary)

            Text("A parent denied this pairing request.\nTry again or ask for approval.")
                .font(.callout)
                .foregroundColor(AppTheme.textSecondary)
                .multilineTextAlignment(.center)

            Button("Try Again") {
                Task { await viewModel.startPairing() }
            }
        }
    }

    // MARK: - Success

    private var successStep: some View {
        VStack(spacing: 24) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 80))
                .foregroundColor(.green)

            Text("Paired Successfully!")
                .font(.title2)
                .fontWeight(.bold)
                .foregroundColor(AppTheme.textPrimary)

            Text("This TV is now connected to your server.")
                .font(.callout)
                .foregroundColor(AppTheme.textSecondary)
        }
        .onAppear {
            // Brief delay to show success, then proceed
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
                onPaired()
            }
        }
    }
}

// MARK: - ViewModel

enum PairingStep: Equatable {
    case enterURL
    case showCode
    case denied
    case success
}

@MainActor
final class PairingViewModel: ObservableObject {
    @Published var step: PairingStep = .enterURL
    @Published var serverURL: String = ""
    @Published var deviceName: String = ""
    @Published var pin: String?
    @Published var qrCodeImage: UIImage?
    @Published var isConnecting = false
    @Published var errorMessage: String?
    @Published var isExpiringSoon = false

    private var pairingToken: String?
    private var pollTask: Task<Void, Never>?
    private var expirationTask: Task<Void, Never>?

    deinit {
        pollTask?.cancel()
        expirationTask?.cancel()
    }

    /// Step 1 → Step 2: validate URL, request pairing, show codes.
    func startPairing() async {
        let url = normalizeURL(serverURL)
        guard !url.isEmpty else {
            errorMessage = "Please enter a server address."
            return
        }

        isConnecting = true
        errorMessage = nil

        let apiClient = APIClient(baseURL: url, apiKey: "")

        do {
            let response = try await apiClient.requestPairing(deviceName: deviceName)

            serverURL = url
            pairingToken = response.token
            pin = response.pin
            qrCodeImage = generateQRCode(from: "\(url)/api/pair/approve/\(response.token)")
            isExpiringSoon = false
            step = .showCode

            startPolling(serverURL: url, token: response.token)
            startExpirationTimer(expiresIn: response.expiresIn, serverURL: url)
        } catch {
            errorMessage = "Could not connect to server.\nCheck the address and try again."
        }

        isConnecting = false
    }

    /// Cancel pairing and return to URL entry.
    func cancelPairing() {
        pollTask?.cancel()
        expirationTask?.cancel()
        pairingToken = nil
        pin = nil
        qrCodeImage = nil
        errorMessage = nil
        step = .enterURL
    }

    // MARK: - Polling

    private func startPolling(serverURL: String, token: String) {
        pollTask?.cancel()
        pollTask = Task {
            let apiClient = APIClient(baseURL: serverURL, apiKey: "")

            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: UInt64(Config.pollInterval * 1_000_000_000))
                guard !Task.isCancelled else { return }

                do {
                    let status = try await apiClient.getPairStatus(token: token)

                    if status.isConfirmed, let apiKey = status.apiKey {
                        // Use server_url from response if provided, otherwise use entered URL
                        let finalURL = status.serverUrl ?? serverURL
                        CredentialStore.store(serverURL: finalURL, apiKey: apiKey)
                        expirationTask?.cancel()
                        step = .success
                        return
                    } else if status.isDenied {
                        pollTask?.cancel()
                        expirationTask?.cancel()
                        step = .denied
                        return
                    } else if status.isExpired {
                        await handleExpiration(serverURL: serverURL)
                        return
                    }
                    // else: still pending, keep polling
                } catch {
                    // Network hiccup — keep trying
                }
            }
        }
    }

    private func startExpirationTimer(expiresIn: Int, serverURL: String) {
        expirationTask?.cancel()
        expirationTask = Task {
            // Warn when 60 seconds remain
            let warningDelay = max(0, expiresIn - 60)
            if warningDelay > 0 {
                try? await Task.sleep(nanoseconds: UInt64(warningDelay) * 1_000_000_000)
                guard !Task.isCancelled else { return }
                isExpiringSoon = true
            }

            // Wait for actual expiration
            let remainingDelay = min(60, expiresIn)
            try? await Task.sleep(nanoseconds: UInt64(remainingDelay) * 1_000_000_000)
            guard !Task.isCancelled else { return }

            await handleExpiration(serverURL: serverURL)
        }
    }

    private func handleExpiration(serverURL: String) async {
        pollTask?.cancel()
        expirationTask?.cancel()

        // Auto-regenerate
        errorMessage = "Code expired — generating a new one..."
        let apiClient = APIClient(baseURL: serverURL, apiKey: "")

        do {
            let response = try await apiClient.requestPairing(deviceName: deviceName)
            pairingToken = response.token
            pin = response.pin
            qrCodeImage = generateQRCode(from: "\(serverURL)/api/pair/approve/\(response.token)")
            isExpiringSoon = false
            errorMessage = nil

            startPolling(serverURL: serverURL, token: response.token)
            startExpirationTimer(expiresIn: response.expiresIn, serverURL: serverURL)
        } catch {
            errorMessage = "Could not refresh pairing code. Please try again."
            step = .enterURL
        }
    }

    // MARK: - Helpers

    private func normalizeURL(_ input: String) -> String {
        var url = input.trimmingCharacters(in: .whitespacesAndNewlines)
        if !url.isEmpty && !url.contains("://") {
            url = "https://" + url
        }
        if url.hasSuffix("/") {
            url = String(url.dropLast())
        }
        return url
    }

    private func generateQRCode(from string: String) -> UIImage? {
        let context = CIContext()
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(string.utf8)
        filter.correctionLevel = "M"

        guard let outputImage = filter.outputImage else { return nil }

        let transform = CGAffineTransform(scaleX: 10, y: 10)
        let scaledImage = outputImage.transformed(by: transform)

        guard let cgImage = context.createCGImage(scaledImage, from: scaledImage.extent) else {
            return nil
        }

        return UIImage(cgImage: cgImage)
    }
}
