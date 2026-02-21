import Foundation

struct ChildProfile: Codable, Identifiable, Equatable {
    let id: Int
    let name: String
    let avatar: String
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, name, avatar
        case createdAt = "created_at"
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
}

struct ProfilesResponse: Codable {
    let profiles: [ChildProfile]
}
