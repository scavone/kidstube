import Foundation

struct TimeStatus: Codable, Equatable {
    let limitMin: Int
    let usedMin: Double
    let remainingMin: Double
    let remainingSec: Int
    let exceeded: Bool

    /// Human-readable remaining time (e.g. "1h 15m" or "23m").
    var formattedRemaining: String {
        if remainingSec <= 0 { return "0m" }
        let hours = remainingSec / 3600
        let minutes = (remainingSec % 3600) / 60
        if hours > 0 {
            return "\(hours)h \(minutes)m"
        }
        return "\(minutes)m"
    }

    enum CodingKeys: String, CodingKey {
        case limitMin = "limit_min"
        case usedMin = "used_min"
        case remainingMin = "remaining_min"
        case remainingSec = "remaining_sec"
        case exceeded
    }
}

struct ScheduleStatus: Codable, Equatable {
    let allowed: Bool
    let unlockTime: String
    let start: String
    let end: String
    let minutesRemaining: Int  // -1 = no schedule / no end time

    enum CodingKeys: String, CodingKey {
        case allowed
        case unlockTime = "unlock_time"
        case start, end
        case minutesRemaining = "minutes_remaining"
    }
}
