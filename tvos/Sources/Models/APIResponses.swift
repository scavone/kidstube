import Foundation

// MARK: - Video Request / Status

struct VideoRequestBody: Codable {
    let videoId: String
    let childId: Int

    enum CodingKeys: String, CodingKey {
        case videoId = "video_id"
        case childId = "child_id"
    }
}

struct VideoRequestResponse: Codable {
    let status: String
    let videoId: String
    let childId: Int

    enum CodingKeys: String, CodingKey {
        case status
        case videoId = "video_id"
        case childId = "child_id"
    }
}

struct VideoStatusResponse: Codable {
    let status: String
}

// MARK: - Stream

struct StreamUrlResponse: Codable {
    let url: String
    let sessionId: String?

    enum CodingKeys: String, CodingKey {
        case url
        case sessionId = "session_id"
    }
}

// MARK: - Catalog

struct CatalogResponse: Codable {
    let videos: [Video]
    let hasMore: Bool
    let total: Int
    let statusCounts: StatusCounts?

    enum CodingKeys: String, CodingKey {
        case videos
        case hasMore = "has_more"
        case total
        case statusCounts = "status_counts"
    }
}

struct StatusCounts: Codable, Equatable {
    let all: Int
    let unwatched: Int
    let inProgress: Int
    let watched: Int

    enum CodingKeys: String, CodingKey {
        case all, unwatched
        case inProgress = "in_progress"
        case watched
    }
}

// MARK: - Channels

struct Channel: Codable, Identifiable, Equatable {
    let dbId: Int?
    let channelName: String
    var channelId: String?
    var handle: String?
    let status: String
    var category: String?
    var addedAt: String?

    var id: String { channelId ?? channelName }

    enum CodingKeys: String, CodingKey {
        case dbId = "id"
        case channelName = "channel_name"
        case channelId = "channel_id"
        case handle, status, category
        case addedAt = "added_at"
    }
}

struct ChannelsResponse: Codable {
    let channels: [Channel]
}

// MARK: - Recently Added

struct RecentlyAddedResponse: Codable {
    let videos: [Video]
}

// MARK: - Channel Detail

struct ChannelDetailResponse: Codable {
    let channelName: String
    let channelId: String?
    var handle: String?
    var category: String?
    var thumbnailUrl: String?
    var bannerUrl: String?
    let videoCount: Int
    let videos: [Video]
    let hasMore: Bool
    let total: Int

    enum CodingKeys: String, CodingKey {
        case channelName = "channel_name"
        case channelId = "channel_id"
        case handle, category
        case thumbnailUrl = "thumbnail_url"
        case bannerUrl = "banner_url"
        case videoCount = "video_count"
        case videos
        case hasMore = "has_more"
        case total
    }
}

// MARK: - Channel Videos

struct ChannelVideosResponse: Codable {
    let videos: [SearchResult]
    let channelId: String

    enum CodingKeys: String, CodingKey {
        case videos
        case channelId = "channel_id"
    }
}

// MARK: - Channel Request

struct ChannelRequestBody: Codable {
    let childId: Int
    let channelId: String

    enum CodingKeys: String, CodingKey {
        case childId = "child_id"
        case channelId = "channel_id"
    }
}

struct ChannelRequestResponse: Codable {
    let status: String
    let channelId: String
    let childId: Int
    let channelName: String

    enum CodingKeys: String, CodingKey {
        case status
        case channelId = "channel_id"
        case childId = "child_id"
        case channelName = "channel_name"
    }
}

struct ChannelRequestStatusResponse: Codable {
    let status: String
}

// MARK: - Watch Position

struct WatchPositionBody: Codable {
    let videoId: String
    let childId: Int
    let position: Int
    let duration: Int

    enum CodingKeys: String, CodingKey {
        case videoId = "video_id"
        case childId = "child_id"
        case position, duration
    }
}

struct WatchPositionResponse: Codable {
    let watchPosition: Int
    let watchDuration: Int
    let lastWatchedAt: String?

    enum CodingKeys: String, CodingKey {
        case watchPosition = "watch_position"
        case watchDuration = "watch_duration"
        case lastWatchedAt = "last_watched_at"
    }
}

// MARK: - Watch Status

struct WatchStatusBody: Codable {
    let videoId: String
    let childId: Int
    let status: String

    enum CodingKeys: String, CodingKey {
        case videoId = "video_id"
        case childId = "child_id"
        case status
    }
}

// MARK: - Heartbeat

struct HeartbeatBody: Codable {
    let videoId: String
    let childId: Int
    let seconds: Int

    enum CodingKeys: String, CodingKey {
        case videoId = "video_id"
        case childId = "child_id"
        case seconds
    }
}

struct HeartbeatResponse: Codable {
    let remaining: Int
}

// MARK: - Time Request

struct TimeRequestBody: Codable {
    let childId: Int
    let videoId: String?

    enum CodingKeys: String, CodingKey {
        case childId = "child_id"
        case videoId = "video_id"
    }
}

struct TimeRequestResponse: Codable {
    let status: String
    let bonusMinutes: Int

    enum CodingKeys: String, CodingKey {
        case status
        case bonusMinutes = "bonus_minutes"
    }
}

struct TimeRequestStatusResponse: Codable {
    let status: String
    let bonusMinutes: Int

    enum CodingKeys: String, CodingKey {
        case status
        case bonusMinutes = "bonus_minutes"
    }
}

// MARK: - Error

struct APIErrorResponse: Codable {
    let detail: String
}
