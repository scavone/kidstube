import Foundation

struct ChildProfile: Codable, Identifiable, Equatable {
    let id: Int
    let name: String
    let avatar: String
    let createdAt: String
    var videoCount: Int?
    var timeRemainingSec: Int?
    var freeDay: Bool?
    var pinEnabled: Bool?

    enum CodingKeys: String, CodingKey {
        case id, name, avatar
        case createdAt = "created_at"
        case videoCount = "video_count"
        case timeRemainingSec = "time_remaining_sec"
        case freeDay = "free_day"
        case pinEnabled = "pin_enabled"
    }

    /// Whether the avatar is a server-hosted photo (vs. an emoji).
    var hasPhotoAvatar: Bool {
        avatar == "photo"
    }

    /// URL to fetch the photo avatar from the server.
    var avatarURL: URL? {
        guard hasPhotoAvatar else { return nil }
        return URL(string: "\(Config.serverBaseURL)/api/profiles/\(id)/avatar")
    }

    /// Status subtitle for the profile picker (e.g. "12 videos · 45 min left").
    var subtitle: String? {
        var parts: [String] = []

        if let count = videoCount {
            parts.append("\(count) video\(count == 1 ? "" : "s")")
        }

        if freeDay == true {
            parts.append("Free day!")
        } else if let remaining = timeRemainingSec {
            if remaining == -1 {
                // No limit set
            } else if remaining <= 0 {
                parts.append("Time's up")
            } else {
                let hours = remaining / 3600
                let minutes = (remaining % 3600) / 60
                if hours > 0 {
                    parts.append("\(hours)h \(minutes)m left")
                } else {
                    parts.append("\(minutes)m left")
                }
            }
        }

        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }
}

struct ProfilesResponse: Codable {
    let profiles: [ChildProfile]
}
