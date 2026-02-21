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
}

struct ProfilesResponse: Codable {
    let profiles: [ChildProfile]
}
