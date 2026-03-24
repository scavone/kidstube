import Foundation

/// Errors originating from the BrainRotGuard server API.
enum APIError: LocalizedError {
    case invalidURL
    case httpError(statusCode: Int, detail: String)
    case decodingError(Error)
    case networkError(Error)
    case noData
    case notApproved
    case streamUnavailable

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid server URL"
        case .httpError(let code, let detail):
            return "Server error (\(code)): \(detail)"
        case .decodingError(let error):
            return "Failed to parse response: \(error.localizedDescription)"
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        case .noData:
            return "No data received"
        case .notApproved:
            return "Video not approved"
        case .streamUnavailable:
            return "Stream unavailable"
        }
    }
}

/// HTTP client for the BrainRotGuard server API.
/// Thread-safe, designed for use with Swift concurrency.
final class APIClient: Sendable {
    let baseURL: String
    private let apiKey: String
    private let session: URLSession

    init(
        baseURL: String = Config.serverBaseURL,
        apiKey: String = Config.apiKey,
        session: URLSession = .shared
    ) {
        self.baseURL = baseURL
        self.apiKey = apiKey
        self.session = session
    }

    // MARK: - Profiles

    /// Fetch all child profiles.
    func getProfiles() async throws -> [ChildProfile] {
        let response: ProfilesResponse = try await get("/api/profiles")
        return response.profiles
    }

    /// Create a new child profile.
    func createProfile(name: String, avatar: String = "👦") async throws -> ChildProfile {
        struct Body: Codable { let name: String; let avatar: String }
        return try await post("/api/profiles", body: Body(name: name, avatar: avatar))
    }

    // MARK: - Search

    /// Search for videos and channels via Invidious.
    func search(query: String, childId: Int) async throws -> SearchResponse {
        return try await get("/api/search", query: [
            "q": query,
            "child_id": String(childId)
        ])
    }

    /// Fetch videos for a channel, annotated with the child's access status.
    func getChannelVideos(channelId: String, childId: Int) async throws -> [SearchResult] {
        let response: ChannelVideosResponse = try await get(
            "/api/channel/\(channelId)/videos",
            query: ["child_id": String(childId)]
        )
        return response.videos
    }

    /// Fetch channel detail with metadata and paginated approved videos.
    func getChannelDetail(
        channelId: String,
        childId: Int,
        offset: Int = 0,
        limit: Int = 24
    ) async throws -> ChannelDetailResponse {
        return try await get(
            "/api/channels/\(channelId)",
            query: [
                "child_id": String(childId),
                "offset": String(offset),
                "limit": String(limit)
            ]
        )
    }

    // MARK: - Video Detail

    /// Fetch full video metadata including description.
    func getVideoDetail(videoId: String, childId: Int) async throws -> Video {
        return try await get("/api/video/\(videoId)", query: ["child_id": String(childId)])
    }

    // MARK: - Channel Requests

    /// Request a channel for a child.
    func requestChannel(channelId: String, childId: Int) async throws -> ChannelRequestResponse {
        let body = ChannelRequestBody(childId: childId, channelId: channelId)
        return try await post("/api/request-channel", body: body)
    }

    /// Poll approval status for a channel request.
    func getChannelRequestStatus(channelId: String, childId: Int) async throws -> String {
        let response: ChannelRequestStatusResponse = try await get(
            "/api/channel-request-status/\(channelId)",
            query: ["child_id": String(childId)]
        )
        return response.status
    }

    // MARK: - Video Requests

    /// Request access to a video for a child.
    func requestVideo(videoId: String, childId: Int) async throws -> VideoRequestResponse {
        let body = VideoRequestBody(videoId: videoId, childId: childId)
        return try await post("/api/request", body: body)
    }

    /// Poll approval status for a video.
    func getVideoStatus(videoId: String, childId: Int) async throws -> String {
        let response: VideoStatusResponse = try await get(
            "/api/status/\(videoId)",
            query: ["child_id": String(childId)]
        )
        return response.status
    }

    // MARK: - Streaming

    /// Get a fresh playable stream URL for an approved video.
    /// Returns (url, sessionId) — sessionId is non-nil for HLS muxing sessions.
    func getStreamURL(videoId: String, childId: Int) async throws -> (url: String, sessionId: String?) {
        let response: StreamUrlResponse = try await get(
            "/api/stream/\(videoId)",
            query: ["child_id": String(childId)]
        )
        return (response.url, response.sessionId)
    }

    /// Kill an active HLS muxing session on the server.
    /// Best-effort — failures are silently ignored.
    func deleteHLSSession(sessionId: String) async {
        do {
            let _: [String: String] = try await delete("/api/hls/\(sessionId)")
        } catch {
            // Best-effort cleanup — don't propagate errors
        }
    }

    // MARK: - Catalog

    /// Fetch paginated catalog of approved videos for a child.
    func getCatalog(
        childId: Int,
        category: String? = nil,
        channel: String? = nil,
        sortBy: String = "newest",
        watchStatus: String = "all",
        offset: Int = 0,
        limit: Int = Config.catalogPageSize
    ) async throws -> CatalogResponse {
        var params: [String: String] = [
            "child_id": String(childId),
            "sort_by": sortBy,
            "watch_status": watchStatus,
            "offset": String(offset),
            "limit": String(limit)
        ]
        if let category { params["category"] = category }
        if let channel { params["channel"] = channel }
        return try await get("/api/catalog", query: params)
    }

    // MARK: - Channels

    /// Fetch allowed channels for a child.
    func getChannels(childId: Int) async throws -> [Channel] {
        let response: ChannelsResponse = try await get("/api/channels", query: ["child_id": String(childId)])
        return response.channels
    }

    /// Fetch recently added/approved videos for a child.
    /// Ordered by approval date descending.
    func getRecentlyAdded(childId: Int, limit: Int = 20) async throws -> [Video] {
        let response: RecentlyAddedResponse = try await get(
            "/api/recently-added",
            query: ["child_id": String(childId), "limit": String(limit)]
        )
        return response.videos
    }

    /// Fetch channels with their latest video for the home screen.
    /// Channels are ordered by most recently published video (newest first).
    func getHomeChannels(childId: Int) async throws -> [HomeChannel] {
        let response: HomeChannelsResponse = try await get(
            "/api/channels-home",
            query: ["child_id": String(childId)]
        )
        return response.channels
    }

    // MARK: - Watch Position (Resume Playback)

    /// Save the current playback position for a child+video pair.
    func saveWatchPosition(videoId: String, childId: Int, position: Int, duration: Int) async {
        struct Response: Codable { let status: String }
        let body = WatchPositionBody(videoId: videoId, childId: childId, position: position, duration: duration)
        do {
            let _: Response = try await post("/api/watch/position", body: body)
        } catch {
            // Best-effort — don't interrupt playback for position save failures
        }
    }

    /// Get the saved playback position for a child+video pair.
    func getWatchPosition(videoId: String, childId: Int) async throws -> WatchPositionResponse {
        return try await get("/api/watch/position/\(videoId)", query: ["child_id": String(childId)])
    }

    // MARK: - Watch Status (Manual Toggle)

    /// Manually mark a video as watched or unwatched.
    /// Best-effort — UI updates optimistically before this call.
    func setWatchStatus(videoId: String, childId: Int, status: String) async {
        let body = WatchStatusBody(videoId: videoId, childId: childId, status: status)
        do {
            struct Response: Codable { let status: String }
            let _: Response = try await post("/api/watch/status", body: body)
        } catch {
            // Best-effort — UI already updated optimistically
        }
    }

    // MARK: - Watch Tracking

    /// Send a heartbeat reporting seconds watched. Returns remaining seconds.
    /// - Returns: remaining seconds (-1 = no limit, -2 = outside schedule)
    @discardableResult
    func sendHeartbeat(videoId: String, childId: Int, seconds: Int) async throws -> Int {
        let body = HeartbeatBody(videoId: videoId, childId: childId, seconds: seconds)
        let response: HeartbeatResponse = try await post("/api/watch-heartbeat", body: body)
        return response.remaining
    }

    // MARK: - Time & Schedule

    /// Get the child's time usage and remaining limit.
    func getTimeStatus(childId: Int) async throws -> TimeStatus {
        return try await get("/api/time-status", query: ["child_id": String(childId)])
    }

    /// Check if current time is within the child's allowed schedule.
    func getScheduleStatus(childId: Int) async throws -> ScheduleStatus {
        return try await get("/api/schedule-status", query: ["child_id": String(childId)])
    }

    // MARK: - Time Requests (More Time)

    /// Request more time for a child.
    func requestMoreTime(childId: Int, videoId: String? = nil) async throws -> TimeRequestResponse {
        let body = TimeRequestBody(childId: childId, videoId: videoId)
        return try await post("/api/time-request", body: body)
    }

    /// Poll the status of a pending time request.
    func getTimeRequestStatus(childId: Int) async throws -> TimeRequestStatusResponse {
        return try await get("/api/time-request/status", query: ["child_id": String(childId)])
    }

    // MARK: - Pairing (No Auth Required)

    /// Request a new pairing session. Called against a server URL before credentials exist.
    /// Uses an unauthenticated request since the device has no API key yet.
    func requestPairing() async throws -> PairRequestResponse {
        let url = try buildURL(path: "/api/pair/request")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        // No auth — pairing endpoint is public
        request.httpBody = try JSONEncoder().encode(["device_name": "Apple TV"])
        return try await execute(request)
    }

    /// Poll the status of a pairing session. Returns confirmed + API key when parent approves.
    func getPairStatus(token: String) async throws -> PairStatusResponse {
        let url = try buildURL(path: "/api/pair/status/\(token)")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        // No auth — pairing endpoint is public
        return try await execute(request)
    }

    // MARK: - Private HTTP Helpers

    private func get<T: Decodable>(
        _ path: String,
        query: [String: String] = [:]
    ) async throws -> T {
        let url = try buildURL(path: path, query: query)
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        applyAuth(&request)
        return try await execute(request)
    }

    private func delete<T: Decodable>(
        _ path: String,
        query: [String: String] = [:]
    ) async throws -> T {
        let url = try buildURL(path: path, query: query)
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        applyAuth(&request)
        return try await execute(request)
    }

    private func post<T: Decodable, B: Encodable>(
        _ path: String,
        body: B,
        query: [String: String] = [:]
    ) async throws -> T {
        let url = try buildURL(path: path, query: query)
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        applyAuth(&request)
        request.httpBody = try JSONEncoder().encode(body)
        return try await execute(request)
    }

    private func buildURL(path: String, query: [String: String] = [:]) throws -> URL {
        guard var components = URLComponents(string: baseURL + path) else {
            throw APIError.invalidURL
        }
        if !query.isEmpty {
            components.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        guard let url = components.url else {
            throw APIError.invalidURL
        }
        return url
    }

    private func applyAuth(_ request: inout URLRequest) {
        if !apiKey.isEmpty {
            request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        }
    }

    private func execute<T: Decodable>(_ request: URLRequest) async throws -> T {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.networkError(error)
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.noData
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            let detail: String
            if let errorResponse = try? JSONDecoder().decode(APIErrorResponse.self, from: data) {
                detail = errorResponse.detail
            } else {
                detail = String(data: data, encoding: .utf8) ?? "Unknown error"
            }
            throw APIError.httpError(statusCode: httpResponse.statusCode, detail: detail)
        }

        do {
            let decoder = JSONDecoder()
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decodingError(error)
        }
    }
}
