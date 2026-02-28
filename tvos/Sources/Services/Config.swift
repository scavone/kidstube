import Foundation

/// Central configuration for the KidsTube tvOS app.
/// Update these values before building to match your server deployment.
enum Config {
    /// Base URL of the BrainRotGuard server (no trailing slash).
    /// Example: "http://192.168.1.100:8080"
    static let serverBaseURL = "http://localhost:8080"

    /// Shared API key matching the server's BRG_API_KEY environment variable.
    static let apiKey = "2WuqrTwPuVhQxHEwDt00FyQD1AnujUcUT2ZbosD6aBU"

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
}
