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

    /// Watch position tracking (resume playback).
    var watchPosition: Int?
    var watchDuration: Int?
    var lastWatchedAt: String?

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
        case watchPosition = "watch_position"
        case watchDuration = "watch_duration"
        case lastWatchedAt = "last_watched_at"
    }

    /// Whether this video has a saved position worth resuming from (at least 5 seconds in).
    var hasResumePosition: Bool {
        guard let pos = watchPosition, let dur = watchDuration, pos >= 5, dur > 0 else { return false }
        // Don't offer resume if within last 5 seconds (effectively finished)
        return pos < dur - 5
    }

    /// Formatted resume position string (e.g. "3:45").
    var formattedResumePosition: String {
        guard let pos = watchPosition, pos > 0 else { return "" }
        let hours = pos / 3600
        let minutes = (pos % 3600) / 60
        let seconds = pos % 60
        if hours > 0 {
            return String(format: "%d:%02d:%02d", hours, minutes, seconds)
        }
        return String(format: "%d:%02d", minutes, seconds)
    }
}
