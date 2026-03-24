import Foundation

/// Tracks per-child PIN sessions so we don't re-prompt within the timeout window.
/// Sessions expire after `Config.pinSessionTimeout` seconds of inactivity.
/// Returning to the profile selector clears the session.
enum SessionManager {
    private struct Session {
        let token: String
        var lastActivity: Date
    }

    /// Child ID → session data.
    private static var sessions: [Int: Session] = [:]

    /// Record a successful PIN verification for a child.
    static func authenticate(childId: Int, token: String) {
        sessions[childId] = Session(token: token, lastActivity: Date())
    }

    /// Update the last-activity timestamp (call on user interactions).
    static func touch(childId: Int) {
        guard sessions[childId] != nil else { return }
        sessions[childId]?.lastActivity = Date()
    }

    /// Whether the child has a valid (non-expired) session.
    static func isAuthenticated(childId: Int) -> Bool {
        guard let session = sessions[childId] else { return false }
        return Date().timeIntervalSince(session.lastActivity) < Config.pinSessionTimeout
    }

    /// The session token for a child, if authenticated.
    static func token(childId: Int) -> String? {
        guard isAuthenticated(childId: childId) else { return nil }
        return sessions[childId]?.token
    }

    /// Clear session for a child (e.g. when returning to profile picker).
    static func clear(childId: Int) {
        sessions.removeValue(forKey: childId)
    }

    /// Clear all sessions.
    static func clearAll() {
        sessions.removeAll()
    }
}
