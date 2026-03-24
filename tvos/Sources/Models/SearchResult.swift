import Foundation

// MARK: - Video Search Result

struct SearchResult: Codable, Identifiable, Equatable {
    let videoId: String
    let title: String
    let channelName: String
    var channelId: String?
    var thumbnailUrl: String?
    var thumbnailUrls: [String]?
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
        case thumbnailUrls = "thumbnail_urls"
        case duration, published
        case viewCount = "view_count"
        case accessStatus = "access_status"
    }
}

// MARK: - Channel Search Result

struct ChannelSearchResult: Codable, Identifiable, Equatable {
    let channelId: String
    let name: String
    var thumbnailUrl: String?
    var subscriberCount: Int?
    var videoCount: Int?
    var channelStatus: String?

    var id: String { channelId }

    var isAllowed: Bool { channelStatus == "allowed" }
    var isPending: Bool { channelStatus == "pending" }

    var formattedSubscriberCount: String {
        guard let count = subscriberCount, count > 0 else { return "" }
        if count >= 1_000_000 {
            return String(format: "%.1fM subscribers", Double(count) / 1_000_000)
        } else if count >= 1_000 {
            return String(format: "%.0fK subscribers", Double(count) / 1_000)
        }
        return "\(count) subscribers"
    }

    enum CodingKeys: String, CodingKey {
        case channelId = "channel_id"
        case name
        case thumbnailUrl = "thumbnail_url"
        case subscriberCount = "subscriber_count"
        case videoCount = "video_count"
        case channelStatus = "channel_status"
    }
}

// MARK: - Search Item (discriminated union for mixed results)

enum SearchItem: Identifiable, Equatable {
    case video(SearchResult)
    case channel(ChannelSearchResult)

    var id: String {
        switch self {
        case .video(let v): return "v_\(v.videoId)"
        case .channel(let c): return "c_\(c.channelId)"
        }
    }
}

// MARK: - Search Response

struct SearchResponse: Decodable {
    let items: [SearchItem]
    let query: String

    private enum CodingKeys: String, CodingKey {
        case results
        case query
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        query = try container.decode(String.self, forKey: .query)

        var rawArray = try container.nestedUnkeyedContainer(forKey: .results)
        var decoded: [SearchItem] = []
        while !rawArray.isAtEnd {
            let wrapper = try rawArray.decode(SearchItemWrapper.self)
            decoded.append(wrapper.item)
        }
        items = decoded
    }
}

/// Decodes a single search result item by peeking at the "type" field.
private struct SearchItemWrapper: Decodable {
    let item: SearchItem

    private enum TypeCodingKeys: String, CodingKey {
        case type
    }

    init(from decoder: Decoder) throws {
        let typeContainer = try decoder.container(keyedBy: TypeCodingKeys.self)
        let type = try typeContainer.decodeIfPresent(String.self, forKey: .type) ?? "video"

        if type == "channel" {
            item = .channel(try ChannelSearchResult(from: decoder))
        } else {
            item = .video(try SearchResult(from: decoder))
        }
    }
}
