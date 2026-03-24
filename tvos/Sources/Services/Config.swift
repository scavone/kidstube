import Foundation

/// Central configuration for the KidsTube tvOS app.
/// Credentials are resolved in order: Keychain (paired) → Info.plist (build-time) → fallback.
enum Config {
    /// Base URL of the BrainRotGuard server (no trailing slash).
    /// Checks Keychain first (set during pairing), falls back to Info.plist / build-time config.
    static var serverBaseURL: String {
        if let stored = CredentialStore.serverURL {
            return stored
        }
        return infoPlistString(key: "BRGServerURL", fallback: "http://localhost:8080")
    }

    /// Shared API key matching the server's BRG_API_KEY environment variable.
    /// Checks Keychain first (set during pairing), falls back to Info.plist / build-time config.
    static var apiKey: String {
        if let stored = CredentialStore.apiKey {
            return stored
        }
        return infoPlistString(key: "BRGAPIKey", fallback: "")
    }

    /// How often (in seconds) the pending view polls for approval status.
    static let pollInterval: TimeInterval = 3.0

    /// How often (in seconds) the player sends watch heartbeats.
    static let heartbeatInterval: TimeInterval = 30.0

    /// Seconds to report per heartbeat (matches heartbeat interval).
    static let heartbeatSeconds: Int = 30

    /// How long (in seconds) the time-remaining overlay stays visible.
    static let overlayDisplayDuration: TimeInterval = 5.0

    /// Number of catalog items to fetch per page.
    static let catalogPageSize: Int = 24

    /// App display name (dynamic — could change).
    static let appName = "KidsTube"

    private static func infoPlistString(key: String, fallback: String) -> String {
        if let value = Bundle.main.object(forInfoDictionaryKey: key) as? String,
           !value.isEmpty, !value.contains("$(") {
            return value
        }
        return fallback
    }
}
