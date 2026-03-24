import Foundation

struct SessionStatus: Codable {
    let sessionsEnabled: Bool
    let currentSession: Int?
    let maxSessions: Int?
    let sessionDurationMinutes: Int?
    let cooldownDurationMinutes: Int?
    let sessionTimeRemainingSeconds: Int?
    let inCooldown: Bool?
    let cooldownRemainingSeconds: Int?
    let nextSessionAt: String?
    let sessionsExhausted: Bool?

    enum CodingKeys: String, CodingKey {
        case sessionsEnabled = "sessions_enabled"
        case currentSession = "current_session"
        case maxSessions = "max_sessions"
        case sessionDurationMinutes = "session_duration_minutes"
        case cooldownDurationMinutes = "cooldown_duration_minutes"
        case sessionTimeRemainingSeconds = "session_time_remaining_seconds"
        case inCooldown = "in_cooldown"
        case cooldownRemainingSeconds = "cooldown_remaining_seconds"
        case nextSessionAt = "next_session_at"
        case sessionsExhausted = "sessions_exhausted"
    }
}
