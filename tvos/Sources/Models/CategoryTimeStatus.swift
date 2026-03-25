import Foundation

struct CategoryTimeStatusResponse: Codable {
    let categories: [String: CategoryTimeInfo]
    let uncappedCategories: [String]

    enum CodingKeys: String, CodingKey {
        case categories
        case uncappedCategories = "uncapped_categories"
    }
}

struct CategoryTimeInfo: Codable {
    let limitMinutes: Int
    let usedMinutes: Double
    let remainingMinutes: Double
    let remainingSeconds: Int
    let bonusMinutes: Int
    let exhausted: Bool

    enum CodingKeys: String, CodingKey {
        case limitMinutes = "limit_minutes"
        case usedMinutes = "used_minutes"
        case remainingMinutes = "remaining_minutes"
        case remainingSeconds = "remaining_seconds"
        case bonusMinutes = "bonus_minutes"
        case exhausted
    }

    /// Human-readable remaining time (e.g. "42 min left" or "1h 5m left").
    var formattedRemaining: String {
        if exhausted || remainingSeconds <= 0 { return "0 min left" }
        let hours = remainingSeconds / 3600
        let minutes = max(1, (remainingSeconds % 3600) / 60)
        if hours > 0 {
            return "\(hours)h \(minutes)m left"
        }
        return "\(minutes) min left"
    }
}
