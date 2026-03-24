import Foundation

/// A channel with its latest video, used for the home screen channel row and featured banner.
/// Returned by the `GET /api/channels-home` endpoint.
struct HomeChannel: Codable, Identifiable, Equatable {
    let channelName: String
    var channelId: String?
    var handle: String?
    var category: String?
    var thumbnailUrl: String?
    var bannerUrl: String?
    var latestVideo: HomeChannelVideo?

    var id: String { channelId ?? channelName }

    enum CodingKeys: String, CodingKey {
        case channelName = "channel_name"
        case channelId = "channel_id"
        case handle
        case category
        case thumbnailUrl = "thumbnail_url"
        case bannerUrl = "banner_url"
        case latestVideo = "latest_video"
    }
}

/// Minimal video info embedded in a HomeChannel response.
struct HomeChannelVideo: Codable, Equatable {
    let videoId: String
    let title: String
    var thumbnailUrl: String?
    var duration: Int?
    var publishedAt: Int?

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

    enum CodingKeys: String, CodingKey {
        case videoId = "video_id"
        case title
        case thumbnailUrl = "thumbnail_url"
        case duration
        case publishedAt = "published_at"
    }
}

/// Response wrapper for the home channels endpoint.
struct HomeChannelsResponse: Codable {
    let channels: [HomeChannel]
}
