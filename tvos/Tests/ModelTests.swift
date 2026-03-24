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

    @Test("watchProgress nil when unwatched")
    func watchProgressNilWhenUnwatched() {
        let video = Video(videoId: "test", title: "Test", channelName: "Ch")
        #expect(video.watchProgress == nil)
    }

    @Test("watchProgress fraction")
    func watchProgressFraction() {
        var video = Video(videoId: "test", title: "Test", channelName: "Ch")
        video.watchPosition = 120
        video.watchDuration = 600
        #expect(video.watchProgress! == 0.2)
    }

    @Test("watchProgress is 1.0 when watched")
    func watchProgressWatched() {
        var video = Video(videoId: "test", title: "Test", channelName: "Ch")
        video.watchStatus = "watched"
        #expect(video.watchProgress == 1.0)
    }

    @Test("isWatched by status")
    func isWatchedByStatus() {
        var video = Video(videoId: "test", title: "Test", channelName: "Ch")
        video.watchStatus = "watched"
        #expect(video.isWatched)
    }

    @Test("isWatched by position fallback")
    func isWatchedByPositionFallback() {
        var video = Video(videoId: "test", title: "Test", channelName: "Ch")
        video.watchPosition = 597
        video.watchDuration = 600
        #expect(video.isWatched)
    }

    @Test("Decode video with watch_status")
    func decodeVideoWithWatchStatus() throws {
        let json = """
        {
            "video_id": "test123", "title": "Watched",
            "channel_name": "Ch", "watch_status": "watched",
            "watch_position": 0, "watch_duration": 600
        }
        """.data(using: .utf8)!

        let video = try JSONDecoder().decode(Video.self, from: json)
        #expect(video.watchStatus == "watched")
        #expect(video.isWatched)
        #expect(video.watchProgress == 1.0)
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

    @Test("Decode search response with videos and channels")
    func decodeSearchResponse() throws {
        let json = """
        {
            "results": [
                {"type":"video","video_id":"a","title":"V1","channel_name":"C1","duration":60},
                {"type":"channel","channel_id":"UC1234","name":"Cool Channel","subscriber_count":5000,"video_count":100},
                {"type":"video","video_id":"b","title":"V2","channel_name":"C2","duration":120}
            ],
            "query": "test search"
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(SearchResponse.self, from: json)
        #expect(response.query == "test search")
        #expect(response.items.count == 3)
        // First item is a video
        if case .video(let v) = response.items[0] {
            #expect(v.videoId == "a")
        } else {
            Issue.record("Expected video at index 0")
        }
        // Second item is a channel
        if case .channel(let c) = response.items[1] {
            #expect(c.channelId == "UC1234")
            #expect(c.name == "Cool Channel")
            #expect(c.subscriberCount == 5000)
        } else {
            Issue.record("Expected channel at index 1")
        }
        // Third item is a video
        if case .video(let v) = response.items[2] {
            #expect(v.videoId == "b")
        } else {
            Issue.record("Expected video at index 2")
        }
    }

    @Test("Decode search response with videos only (backward compat)")
    func decodeSearchResponseVideosOnly() throws {
        let json = """
        {
            "results": [
                {"video_id":"a","title":"V1","channel_name":"C1","duration":60}
            ],
            "query": "test"
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(SearchResponse.self, from: json)
        #expect(response.items.count == 1)
        if case .video(let v) = response.items[0] {
            #expect(v.videoId == "a")
        } else {
            Issue.record("Expected video")
        }
    }

    @Test("Search result duration formatting")
    func searchResultFormattedDuration() {
        var result = SearchResult(videoId: "t", title: "T", channelName: "C")
        #expect(result.formattedDuration == "")
        result.duration = 90
        #expect(result.formattedDuration == "1:30")
    }

    @Test("Channel search result subscriber formatting")
    func channelSubscriberFormatting() {
        var channel = ChannelSearchResult(channelId: "UC1", name: "Ch")
        #expect(channel.formattedSubscriberCount == "")

        channel.subscriberCount = 500
        #expect(channel.formattedSubscriberCount == "500 subscribers")

        channel.subscriberCount = 5000
        #expect(channel.formattedSubscriberCount == "5K subscribers")

        channel.subscriberCount = 1_500_000
        #expect(channel.formattedSubscriberCount == "1.5M subscribers")
    }

    @Test("Decode channel search result with channel_status")
    func decodeChannelWithStatus() throws {
        let json = """
        {"channel_id":"UC1234","name":"Cool Channel","subscriber_count":5000,"channel_status":"allowed"}
        """.data(using: .utf8)!
        let channel = try JSONDecoder().decode(ChannelSearchResult.self, from: json)
        #expect(channel.channelStatus == "allowed")
        #expect(channel.isAllowed)
        #expect(!channel.isPending)
    }

    @Test("Channel status nil — not allowed, not pending")
    func channelStatusNil() {
        let channel = ChannelSearchResult(channelId: "UC1", name: "Ch")
        #expect(!channel.isAllowed)
        #expect(!channel.isPending)
        #expect(channel.channelStatus == nil)
    }

    @Test("Channel status pending")
    func channelStatusPending() {
        var channel = ChannelSearchResult(channelId: "UC1", name: "Ch")
        channel.channelStatus = "pending"
        #expect(channel.isPending)
        #expect(!channel.isAllowed)
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

    @Test("Free day — isFreeDay true and formatted text")
    func freeDayActive() {
        let s = TimeStatus(limitMin: 120, usedMin: 30, remainingMin: 120, remainingSec: -1, exceeded: false)
        #expect(s.isFreeDay)
        #expect(s.formattedRemaining == "Free day!")
    }

    @Test("Free day — isFreeDay false for normal remaining")
    func freeDayInactive() {
        let s = TimeStatus(limitMin: 120, usedMin: 0, remainingMin: 120, remainingSec: 7200, exceeded: false)
        #expect(!s.isFreeDay)
    }

    @Test("Decode schedule status — within window")
    func decodeScheduleStatusAllowed() throws {
        let json = """
        {"allowed":true,"unlock_time":"","start":"8:00 AM","end":"8:00 PM","minutes_remaining":120}
        """.data(using: .utf8)!

        let schedule = try JSONDecoder().decode(ScheduleStatus.self, from: json)
        #expect(schedule.allowed)
        #expect(schedule.unlockTime == "")
        #expect(schedule.start == "8:00 AM")
        #expect(schedule.end == "8:00 PM")
        #expect(schedule.minutesRemaining == 120)
    }

    @Test("Decode schedule status — outside window")
    func decodeScheduleStatusBlocked() throws {
        let json = """
        {"allowed":false,"unlock_time":"8:00 AM","start":"8:00 AM","end":"8:00 PM","minutes_remaining":-1}
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
        #expect(response.statusCounts == nil)
    }

    @Test("Decode catalog response with status_counts")
    func decodeCatalogWithStatusCounts() throws {
        let json = """
        {
            "videos": [],
            "has_more": false,
            "total": 10,
            "status_counts": {"all": 10, "unwatched": 5, "in_progress": 3, "watched": 2}
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(CatalogResponse.self, from: json)
        #expect(response.total == 10)
        #expect(response.statusCounts?.all == 10)
        #expect(response.statusCounts?.unwatched == 5)
        #expect(response.statusCounts?.inProgress == 3)
        #expect(response.statusCounts?.watched == 2)
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

    @Test("Decode channel request response")
    func decodeChannelRequestResponse() throws {
        let json = """
        {"status":"pending","channel_id":"UCabc","child_id":1,"channel_name":"Cool Channel"}
        """.data(using: .utf8)!
        let response = try JSONDecoder().decode(ChannelRequestResponse.self, from: json)
        #expect(response.status == "pending")
        #expect(response.channelId == "UCabc")
        #expect(response.childId == 1)
        #expect(response.channelName == "Cool Channel")
    }

    @Test("Encode channel request body uses snake_case keys")
    func encodeChannelRequestBody() throws {
        let body = ChannelRequestBody(childId: 1, channelId: "UCabc")
        let data = try JSONEncoder().encode(body)
        let dict = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        #expect(dict["child_id"] as? Int == 1)
        #expect(dict["channel_id"] as? String == "UCabc")
    }

    @Test("Decode channel request status response")
    func decodeChannelRequestStatusResponse() throws {
        let json = "{\"status\":\"approved\"}".data(using: .utf8)!
        let response = try JSONDecoder().decode(ChannelRequestStatusResponse.self, from: json)
        #expect(response.status == "approved")
    }

    @Test("Encode watch status body uses snake_case keys")
    func encodeWatchStatusBody() throws {
        let body = WatchStatusBody(videoId: "abc12345678", childId: 1, status: "watched")
        let data = try JSONEncoder().encode(body)
        let dict = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        #expect(dict["video_id"] as? String == "abc12345678")
        #expect(dict["child_id"] as? Int == 1)
        #expect(dict["status"] as? String == "watched")
    }

    @Test("Decode watch status body round-trip")
    func decodeWatchStatusBody() throws {
        let json = "{\"video_id\":\"abc12345678\",\"child_id\":2,\"status\":\"unwatched\"}".data(using: .utf8)!
        let body = try JSONDecoder().decode(WatchStatusBody.self, from: json)
        #expect(body.videoId == "abc12345678")
        #expect(body.childId == 2)
        #expect(body.status == "unwatched")
    }
}

// MARK: - Time Request Model Tests

@Suite("TimeRequest")
struct TimeRequestModelTests {

    @Test("Decode TimeRequestResponse")
    func decodeTimeRequestResponse() throws {
        let json = """
        {"status": "pending", "bonus_minutes": 0}
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(TimeRequestResponse.self, from: json)
        #expect(response.status == "pending")
        #expect(response.bonusMinutes == 0)
    }

    @Test("Decode TimeRequestResponse — granted with bonus")
    func decodeTimeRequestResponseGranted() throws {
        let json = """
        {"status": "granted", "bonus_minutes": 15}
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(TimeRequestResponse.self, from: json)
        #expect(response.status == "granted")
        #expect(response.bonusMinutes == 15)
    }

    @Test("Decode TimeRequestStatusResponse")
    func decodeTimeRequestStatusResponse() throws {
        let json = """
        {"status": "none", "bonus_minutes": 0}
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(TimeRequestStatusResponse.self, from: json)
        #expect(response.status == "none")
        #expect(response.bonusMinutes == 0)
    }

    @Test("Decode TimeRequestStatusResponse — granted")
    func decodeTimeRequestStatusResponseGranted() throws {
        let json = """
        {"status": "granted", "bonus_minutes": 30}
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(TimeRequestStatusResponse.self, from: json)
        #expect(response.status == "granted")
        #expect(response.bonusMinutes == 30)
    }

    @Test("Encode TimeRequestBody with video_id")
    func encodeTimeRequestBody() throws {
        let body = TimeRequestBody(childId: 1, videoId: "abc12345678")
        let data = try JSONEncoder().encode(body)
        let dict = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        #expect(dict["child_id"] as? Int == 1)
        #expect(dict["video_id"] as? String == "abc12345678")
    }

    @Test("Encode TimeRequestBody without video_id")
    func encodeTimeRequestBodyNoVideo() throws {
        let body = TimeRequestBody(childId: 2, videoId: nil)
        let data = try JSONEncoder().encode(body)
        let dict = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        #expect(dict["child_id"] as? Int == 2)
    }
}

// MARK: - SessionStatus Tests

@Suite("SessionStatus")
struct SessionStatusTests {

    @Test("Decode sessions disabled")
    func decodeSessionsDisabled() throws {
        let json = """
        {"sessions_enabled": false}
        """.data(using: .utf8)!

        let status = try JSONDecoder().decode(SessionStatus.self, from: json)
        #expect(!status.sessionsEnabled)
        #expect(status.currentSession == nil)
        #expect(status.maxSessions == nil)
        #expect(status.inCooldown == nil)
        #expect(status.sessionsExhausted == nil)
    }

    @Test("Decode active session (not in cooldown)")
    func decodeActiveSession() throws {
        let json = """
        {
            "sessions_enabled": true,
            "current_session": 1,
            "max_sessions": 3,
            "session_duration_minutes": 30,
            "cooldown_duration_minutes": 15,
            "session_time_remaining_seconds": 900,
            "in_cooldown": false,
            "cooldown_remaining_seconds": null,
            "next_session_at": null,
            "sessions_exhausted": false
        }
        """.data(using: .utf8)!

        let status = try JSONDecoder().decode(SessionStatus.self, from: json)
        #expect(status.sessionsEnabled)
        #expect(status.currentSession == 1)
        #expect(status.maxSessions == 3)
        #expect(status.sessionDurationMinutes == 30)
        #expect(status.cooldownDurationMinutes == 15)
        #expect(status.sessionTimeRemainingSeconds == 900)
        #expect(status.inCooldown == false)
        #expect(status.cooldownRemainingSeconds == nil)
        #expect(status.sessionsExhausted == false)
    }

    @Test("Decode cooldown state")
    func decodeCooldownState() throws {
        let json = """
        {
            "sessions_enabled": true,
            "current_session": 2,
            "max_sessions": 3,
            "session_duration_minutes": 30,
            "cooldown_duration_minutes": 15,
            "session_time_remaining_seconds": 0,
            "in_cooldown": true,
            "cooldown_remaining_seconds": 720,
            "next_session_at": "2026-03-24T16:00:00Z",
            "sessions_exhausted": false
        }
        """.data(using: .utf8)!

        let status = try JSONDecoder().decode(SessionStatus.self, from: json)
        #expect(status.sessionsEnabled)
        #expect(status.inCooldown == true)
        #expect(status.cooldownRemainingSeconds == 720)
        #expect(status.nextSessionAt == "2026-03-24T16:00:00Z")
        #expect(status.sessionsExhausted == false)
    }

    @Test("Decode sessions exhausted")
    func decodeSessionsExhausted() throws {
        let json = """
        {
            "sessions_enabled": true,
            "current_session": 3,
            "max_sessions": 3,
            "session_duration_minutes": 30,
            "cooldown_duration_minutes": 15,
            "session_time_remaining_seconds": 0,
            "in_cooldown": false,
            "cooldown_remaining_seconds": null,
            "next_session_at": null,
            "sessions_exhausted": true
        }
        """.data(using: .utf8)!

        let status = try JSONDecoder().decode(SessionStatus.self, from: json)
        #expect(status.sessionsEnabled)
        #expect(status.sessionsExhausted == true)
        #expect(status.currentSession == 3)
        #expect(status.maxSessions == 3)
        #expect(status.inCooldown == false)
    }
}
