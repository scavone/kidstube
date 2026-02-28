import Testing
import Foundation
@testable import KidsTubeCore

// MARK: - ChildProfile Tests

@Suite("ChildProfile")
struct ChildProfileTests {

    @Test("Decode child profile from JSON")
    func decodeChildProfile() throws {
        let json = """
        {
            "id": 1,
            "name": "Alex",
            "avatar": "👦",
            "created_at": "2025-02-21T12:00:00"
        }
        """.data(using: .utf8)!

        let profile = try JSONDecoder().decode(ChildProfile.self, from: json)
        #expect(profile.id == 1)
        #expect(profile.name == "Alex")
        #expect(profile.avatar == "👦")
        #expect(profile.createdAt == "2025-02-21T12:00:00")
    }

    @Test("Decode profiles response with multiple children")
    func decodeProfilesResponse() throws {
        let json = """
        {
            "profiles": [
                {"id": 1, "name": "Alex", "avatar": "👦", "created_at": "2025-02-21T12:00:00"},
                {"id": 2, "name": "Sophie", "avatar": "👧", "created_at": "2025-02-21T12:30:00"}
            ]
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(ProfilesResponse.self, from: json)
        #expect(response.profiles.count == 2)
        #expect(response.profiles[0].name == "Alex")
        #expect(response.profiles[1].name == "Sophie")
    }

    @Test("ChildProfile equality")
    func childProfileEquatable() {
        let a = ChildProfile(id: 1, name: "Alex", avatar: "👦", createdAt: "2025-01-01")
        let b = ChildProfile(id: 1, name: "Alex", avatar: "👦", createdAt: "2025-01-01")
        #expect(a == b)
    }

    @Test("ChildProfile id matches database id")
    func childProfileIdentifiable() {
        let profile = ChildProfile(id: 42, name: "Test", avatar: "🎮", createdAt: "2025-01-01")
        #expect(profile.id == 42)
    }

    @Test("Emoji avatar — hasPhotoAvatar is false")
    func emojiAvatarNotPhoto() {
        let profile = ChildProfile(id: 1, name: "Alex", avatar: "👦", createdAt: "2025-01-01")
        #expect(!profile.hasPhotoAvatar)
        #expect(profile.avatarURL == nil)
    }

    @Test("Photo avatar — hasPhotoAvatar is true")
    func photoAvatarDetected() {
        let profile = ChildProfile(id: 3, name: "Sam", avatar: "photo", createdAt: "2025-01-01")
        #expect(profile.hasPhotoAvatar)
        #expect(profile.avatarURL != nil)
        #expect(profile.avatarURL!.absoluteString.contains("/api/profiles/3/avatar"))
    }
}

// MARK: - Video Model Tests

@Suite("Video")
struct VideoModelTests {

    @Test("Decode full video from JSON")
    func decodeVideo() throws {
        let json = """
        {
            "id": 10,
            "video_id": "dQw4w9WgXcQ",
            "title": "Never Gonna Give You Up",
            "channel_name": "Rick Astley",
            "channel_id": "UCuAXFkgsw1L7xaCfnd5JKQ",
            "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
            "duration": 213,
            "category": "fun",
            "effective_category": "fun",
            "access_decided_at": "2025-02-21T12:00:00"
        }
        """.data(using: .utf8)!

        let video = try JSONDecoder().decode(Video.self, from: json)
        #expect(video.dbId == 10)
        #expect(video.videoId == "dQw4w9WgXcQ")
        #expect(video.title == "Never Gonna Give You Up")
        #expect(video.channelName == "Rick Astley")
        #expect(video.duration == 213)
        #expect(video.category == "fun")
        #expect(video.effectiveCategory == "fun")
    }

    @Test("Duration formatting — nil/empty")
    func durationEmpty() {
        let video = Video(videoId: "test", title: "Test", channelName: "Ch")
        #expect(video.formattedDuration == "")
    }

    @Test("Duration formatting — zero")
    func durationZero() {
        var video = Video(videoId: "test", title: "Test", channelName: "Ch")
        video.duration = 0
        #expect(video.formattedDuration == "")
    }

    @Test("Duration formatting — seconds only")
    func durationSeconds() {
        var video = Video(videoId: "test", title: "Test", channelName: "Ch")
        video.duration = 30
        #expect(video.formattedDuration == "0:30")
    }

    @Test("Duration formatting — minutes and seconds")
    func durationMinutes() {
        var video = Video(videoId: "test", title: "Test", channelName: "Ch")
        video.duration = 65
        #expect(video.formattedDuration == "1:05")
    }

    @Test("Duration formatting — hours, minutes, seconds")
    func durationHours() {
        var video = Video(videoId: "test", title: "Test", channelName: "Ch")
        video.duration = 3661
        #expect(video.formattedDuration == "1:01:01")
    }

    @Test("Video id uses videoId")
    func videoIdentifiable() {
        let video = Video(videoId: "abc123", title: "Test", channelName: "Ch")
        #expect(video.id == "abc123")
    }

    @Test("Decode video with null optional fields")
    func decodeVideoWithNullOptionals() throws {
        let json = """
        {"video_id": "test123", "title": "Minimal", "channel_name": "TestCh"}
        """.data(using: .utf8)!

        let video = try JSONDecoder().decode(Video.self, from: json)
        #expect(video.dbId == nil)
        #expect(video.channelId == nil)
        #expect(video.thumbnailUrl == nil)
        #expect(video.duration == nil)
        #expect(video.category == nil)
    }
}

// MARK: - SearchResult Tests

@Suite("SearchResult")
struct SearchResultTests {

    @Test("Decode search result with access status")
    func decodeSearchResult() throws {
        let json = """
        {
            "video_id": "dQw4w9WgXcQ", "title": "Rick Roll",
            "channel_name": "Rick Astley", "channel_id": "UCuAXFkgsw1L7xaCfnd5JKQ",
            "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
            "duration": 213, "published": 1087849200, "view_count": 1427000000,
            "access_status": "approved"
        }
        """.data(using: .utf8)!

        let result = try JSONDecoder().decode(SearchResult.self, from: json)
        #expect(result.videoId == "dQw4w9WgXcQ")
        #expect(result.channelName == "Rick Astley")
        #expect(result.viewCount == 1427000000)
        #expect(result.accessStatus == "approved")
        #expect(result.isApproved)
        #expect(!result.isPending)
    }

    @Test("Pending status flags")
    func pendingStatusFlags() throws {
        let json = """
        {"video_id":"a","title":"T","channel_name":"C","access_status":"pending"}
        """.data(using: .utf8)!
        let pending = try JSONDecoder().decode(SearchResult.self, from: json)
        #expect(pending.isPending)
        #expect(!pending.isApproved)
    }

    @Test("Null access status — not approved, not pending")
    func nullStatusFlags() throws {
        let json = """
        {"video_id":"b","title":"T","channel_name":"C","access_status":null}
        """.data(using: .utf8)!
        let noStatus = try JSONDecoder().decode(SearchResult.self, from: json)
        #expect(!noStatus.isApproved)
        #expect(!noStatus.isPending)
    }

    @Test("Decode search response with multiple results")
    func decodeSearchResponse() throws {
        let json = """
        {
            "results": [
                {"video_id":"a","title":"V1","channel_name":"C1","duration":60},
                {"video_id":"b","title":"V2","channel_name":"C2","duration":120}
            ],
            "query": "test search"
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(SearchResponse.self, from: json)
        #expect(response.query == "test search")
        #expect(response.results.count == 2)
        #expect(response.results[0].videoId == "a")
    }

    @Test("Search result duration formatting")
    func searchResultFormattedDuration() {
        var result = SearchResult(videoId: "t", title: "T", channelName: "C")
        #expect(result.formattedDuration == "")
        result.duration = 90
        #expect(result.formattedDuration == "1:30")
    }
}

// MARK: - TimeStatus Tests

@Suite("TimeStatus")
struct TimeStatusTests {

    @Test("Decode time status")
    func decodeTimeStatus() throws {
        let json = """
        {"limit_min":120,"used_min":45.5,"remaining_min":74.5,"remaining_sec":4470,"exceeded":false}
        """.data(using: .utf8)!

        let status = try JSONDecoder().decode(TimeStatus.self, from: json)
        #expect(status.limitMin == 120)
        #expect(status.usedMin == 45.5)
        #expect(status.remainingMin == 74.5)
        #expect(status.remainingSec == 4470)
        #expect(!status.exceeded)
    }

    @Test("Formatted remaining — hours and minutes")
    func formattedRemainingHours() {
        let s = TimeStatus(limitMin: 120, usedMin: 0, remainingMin: 120, remainingSec: 7200, exceeded: false)
        #expect(s.formattedRemaining == "2h 0m")
    }

    @Test("Formatted remaining — minutes only")
    func formattedRemainingMinutes() {
        let s = TimeStatus(limitMin: 120, usedMin: 97, remainingMin: 23, remainingSec: 1380, exceeded: false)
        #expect(s.formattedRemaining == "23m")
    }

    @Test("Formatted remaining — exceeded")
    func formattedRemainingExceeded() {
        let s = TimeStatus(limitMin: 120, usedMin: 120, remainingMin: 0, remainingSec: 0, exceeded: true)
        #expect(s.formattedRemaining == "0m")
    }

    @Test("Decode schedule status — within window")
    func decodeScheduleStatusAllowed() throws {
        let json = """
        {"allowed":true,"unlock_time":"","start":"8:00 AM","end":"8:00 PM"}
        """.data(using: .utf8)!

        let schedule = try JSONDecoder().decode(ScheduleStatus.self, from: json)
        #expect(schedule.allowed)
        #expect(schedule.unlockTime == "")
        #expect(schedule.start == "8:00 AM")
        #expect(schedule.end == "8:00 PM")
    }

    @Test("Decode schedule status — outside window")
    func decodeScheduleStatusBlocked() throws {
        let json = """
        {"allowed":false,"unlock_time":"8:00 AM","start":"8:00 AM","end":"8:00 PM"}
        """.data(using: .utf8)!

        let schedule = try JSONDecoder().decode(ScheduleStatus.self, from: json)
        #expect(!schedule.allowed)
        #expect(schedule.unlockTime == "8:00 AM")
    }
}

// MARK: - API Response Model Tests

@Suite("APIResponses")
struct APIResponseModelTests {

    @Test("Decode video request response")
    func decodeVideoRequestResponse() throws {
        let json = "{\"status\":\"pending\",\"video_id\":\"abc\",\"child_id\":1}".data(using: .utf8)!
        let response = try JSONDecoder().decode(VideoRequestResponse.self, from: json)
        #expect(response.status == "pending")
        #expect(response.videoId == "abc")
        #expect(response.childId == 1)
    }

    @Test("Decode stream URL response without session_id")
    func decodeStreamUrlResponse() throws {
        let json = "{\"url\":\"http://invidious:3000/latest_version?id=abc&itag=18\"}".data(using: .utf8)!
        let response = try JSONDecoder().decode(StreamUrlResponse.self, from: json)
        #expect(response.url.contains("invidious"))
        #expect(response.sessionId == nil)
    }

    @Test("Decode stream URL response with session_id")
    func decodeStreamUrlResponseWithSession() throws {
        let json = "{\"url\":\"http://localhost:8080/api/hls/abc123/index.m3u8\",\"session_id\":\"abc123\"}".data(using: .utf8)!
        let response = try JSONDecoder().decode(StreamUrlResponse.self, from: json)
        #expect(response.url.contains("hls"))
        #expect(response.sessionId == "abc123")
    }

    @Test("Decode catalog response")
    func decodeCatalogResponse() throws {
        let json = """
        {
            "videos": [
                {"video_id":"v1","title":"T1","channel_name":"C1"},
                {"video_id":"v2","title":"T2","channel_name":"C2"}
            ],
            "has_more": true, "total": 50
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(CatalogResponse.self, from: json)
        #expect(response.videos.count == 2)
        #expect(response.hasMore)
        #expect(response.total == 50)
    }

    @Test("Decode channel")
    func decodeChannel() throws {
        let json = """
        {"id":1,"channel_name":"CrashCourse","channel_id":"UCX6OQ","handle":"@crashcourse","status":"allowed","category":"edu","added_at":"2025-02-21T10:00:00"}
        """.data(using: .utf8)!

        let channel = try JSONDecoder().decode(Channel.self, from: json)
        #expect(channel.channelName == "CrashCourse")
        #expect(channel.status == "allowed")
        #expect(channel.category == "edu")
    }

    @Test("Decode heartbeat response — remaining time")
    func decodeHeartbeatResponse() throws {
        let json = "{\"remaining\":1800}".data(using: .utf8)!
        let response = try JSONDecoder().decode(HeartbeatResponse.self, from: json)
        #expect(response.remaining == 1800)
    }

    @Test("Decode heartbeat response — no limit")
    func decodeHeartbeatNoLimit() throws {
        let json = "{\"remaining\":-1}".data(using: .utf8)!
        let response = try JSONDecoder().decode(HeartbeatResponse.self, from: json)
        #expect(response.remaining == -1)
    }

    @Test("Decode API error detail")
    func decodeAPIError() throws {
        let json = "{\"detail\":\"Video not approved for this child\"}".data(using: .utf8)!
        let error = try JSONDecoder().decode(APIErrorResponse.self, from: json)
        #expect(error.detail == "Video not approved for this child")
    }

    @Test("Encode video request body uses snake_case keys")
    func encodeVideoRequestBody() throws {
        let body = VideoRequestBody(videoId: "abc123", childId: 1)
        let data = try JSONEncoder().encode(body)
        let dict = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        #expect(dict["video_id"] as? String == "abc123")
        #expect(dict["child_id"] as? Int == 1)
    }

    @Test("Encode heartbeat body uses snake_case keys")
    func encodeHeartbeatBody() throws {
        let body = HeartbeatBody(videoId: "abc", childId: 2, seconds: 30)
        let data = try JSONEncoder().encode(body)
        let dict = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        #expect(dict["video_id"] as? String == "abc")
        #expect(dict["child_id"] as? Int == 2)
        #expect(dict["seconds"] as? Int == 30)
    }
}
