import Foundation

struct Video: Codable, Identifiable, Equatable {
    /// Database row ID (present in catalog responses).
    var dbId: Int?
    /// YouTube video ID (always present).
    let videoId: String
    let title: String
    let channelName: String
    var channelId: String?
    var thumbnailUrl: String?
    var duration: Int?
    var category: String?
    var description: String?

    /// Only present in catalog responses.
    var effectiveCategory: String?
    var accessDecidedAt: String?
    /// Only present in video detail responses.
    var accessStatus: String?

    var id: String { videoId }

    /// Human-readable duration string (e.g. "3:45" or "1:02:30").
    var formattedDuration: String {
        guard let d = duration, d > 0 else { return "" }
        let hours = d / 3600
        let minutes = (d % 3600) / 60
        let seconds = d % 60
        if hours > 0 {
            return String(format: "%d:%02d:%02d", hours, minutes, seconds)
        }
        return String(format: "%d:%02d", minutes, seconds)
    }

    enum CodingKeys: String, CodingKey {
        case dbId = "id"
        case videoId = "video_id"
        case title
        case channelName = "channel_name"
        case channelId = "channel_id"
        case thumbnailUrl = "thumbnail_url"
        case duration, category, description
        case effectiveCategory = "effective_category"
        case accessDecidedAt = "access_decided_at"
        case accessStatus = "access_status"
    }
}
