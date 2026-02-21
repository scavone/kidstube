import Foundation

struct SearchResult: Codable, Identifiable, Equatable {
    let videoId: String
    let title: String
    let channelName: String
    var channelId: String?
    var thumbnailUrl: String?
    var duration: Int?
    var published: Int?
    var viewCount: Int?
    /// Access status for the current child: nil, "pending", "approved", "denied".
    var accessStatus: String?

    var id: String { videoId }

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

    /// Whether this video is already approved and ready to watch.
    var isApproved: Bool { accessStatus == "approved" }

    /// Whether a request is pending parent approval.
    var isPending: Bool { accessStatus == "pending" }

    enum CodingKeys: String, CodingKey {
        case videoId = "video_id"
        case title
        case channelName = "channel_name"
        case channelId = "channel_id"
        case thumbnailUrl = "thumbnail_url"
        case duration, published
        case viewCount = "view_count"
        case accessStatus = "access_status"
    }
}

struct SearchResponse: Codable {
    let results: [SearchResult]
    let query: String
}
