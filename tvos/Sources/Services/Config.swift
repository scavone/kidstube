import Foundation

/// Central configuration for the KidsTube tvOS app.
/// Server URL and API key are read from Info.plist (set via Secrets.xcconfig).
enum Config {
    /// Base URL of the BrainRotGuard server (no trailing slash).
    static var serverBaseURL: String {
        infoPlistString(key: "BRGServerURL", fallback: "http://localhost:8080")
    }

    /// Shared API key matching the server's BRG_API_KEY environment variable.
    static var apiKey: String {
        infoPlistString(key: "BRGAPIKey", fallback: "")
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
