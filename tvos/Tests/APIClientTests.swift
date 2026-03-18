import Testing
import Foundation
@testable import KidsTubeCore

@Suite("APIClient", .serialized)
struct APIClientTests {

    private func makeClient() -> APIClient {
        MockURLProtocol.reset()
        let session = makeMockSession()
        return APIClient(baseURL: "http://test.local:8080", apiKey: "test-key", session: session)
    }

    // MARK: - Profiles

    @Test("Get profiles returns list")
    func getProfiles() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/profiles", json: [
            "profiles": [
                ["id": 1, "name": "Alex", "avatar": "👦", "created_at": "2025-01-01T00:00:00"],
                ["id": 2, "name": "Sophie", "avatar": "👧", "created_at": "2025-01-02T00:00:00"]
            ]
        ])

        let profiles = try await client.getProfiles()
        #expect(profiles.count == 2)
        #expect(profiles[0].name == "Alex")
        #expect(profiles[1].avatar == "👧")
    }

    @Test("Get profiles — empty")
    func getProfilesEmpty() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/profiles", json: ["profiles": []])

        let profiles = try await client.getProfiles()
        #expect(profiles.isEmpty)
    }

    @Test("Create profile")
    func createProfile() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/profiles", json: [
            "id": 3, "name": "Max", "avatar": "🎮", "created_at": "2025-02-21T12:00:00"
        ])

        let profile = try await client.createProfile(name: "Max", avatar: "🎮")
        #expect(profile.name == "Max")
        #expect(profile.id == 3)
    }

    // MARK: - Search

    @Test("Search returns videos and channels")
    func search() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/search", json: [
            "results": [
                [
                    "type": "video",
                    "video_id": "abc123", "title": "Cool Video",
                    "channel_name": "CoolChannel", "duration": 180,
                    "access_status": NSNull()
                ],
                [
                    "type": "channel",
                    "channel_id": "UC_test", "name": "Test Channel",
                    "subscriber_count": 1000, "video_count": 50
                ]
            ],
            "query": "cool"
        ])

        let response = try await client.search(query: "cool", childId: 1)
        #expect(response.query == "cool")
        #expect(response.items.count == 2)
        if case .video(let v) = response.items[0] {
            #expect(v.title == "Cool Video")
            #expect(v.accessStatus == nil)
        } else {
            Issue.record("Expected video at index 0")
        }
        if case .channel(let c) = response.items[1] {
            #expect(c.name == "Test Channel")
        } else {
            Issue.record("Expected channel at index 1")
        }
    }

    // MARK: - Video Request

    @Test("Request video — pending")
    func requestVideoPending() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/request", json: [
            "status": "pending", "video_id": "abc123", "child_id": 1
        ])

        let response = try await client.requestVideo(videoId: "abc123", childId: 1)
        #expect(response.status == "pending")
        #expect(response.videoId == "abc123")
    }

    @Test("Request video — auto-approved")
    func requestVideoAutoApproved() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/request", json: [
            "status": "approved", "video_id": "abc123", "child_id": 1
        ])

        let response = try await client.requestVideo(videoId: "abc123", childId: 1)
        #expect(response.status == "approved")
    }

    // MARK: - Status

    @Test("Get video status — approved")
    func getVideoStatusApproved() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/status/abc123", json: ["status": "approved"])

        let status = try await client.getVideoStatus(videoId: "abc123", childId: 1)
        #expect(status == "approved")
    }

    @Test("Get video status — pending")
    func getVideoStatusPending() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/status/xyz", json: ["status": "pending"])

        let status = try await client.getVideoStatus(videoId: "xyz", childId: 2)
        #expect(status == "pending")
    }

    @Test("Get video status — not found")
    func getVideoStatusNotFound() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/status/none", json: ["status": "not_found"])

        let status = try await client.getVideoStatus(videoId: "none", childId: 1)
        #expect(status == "not_found")
    }

    // MARK: - Stream

    @Test("Get stream URL")
    func getStreamURL() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/stream/abc123", json: [
            "url": "http://invidious:3000/latest_version?id=abc123&itag=18"
        ])

        let (url, _) = try await client.getStreamURL(videoId: "abc123", childId: 1)
        #expect(url.contains("invidious"))
        #expect(url.contains("abc123"))
    }

    // MARK: - Catalog

    @Test("Get catalog with pagination")
    func getCatalog() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/catalog", json: [
            "videos": [
                ["video_id": "v1", "title": "Video 1", "channel_name": "Ch1"],
                ["video_id": "v2", "title": "Video 2", "channel_name": "Ch2"]
            ],
            "has_more": true, "total": 50
        ])

        let response = try await client.getCatalog(childId: 1)
        #expect(response.videos.count == 2)
        #expect(response.hasMore)
        #expect(response.total == 50)
    }

    @Test("Get catalog with category filter")
    func getCatalogWithCategory() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/catalog", json: [
            "videos": [["video_id": "e1", "title": "Edu Video", "channel_name": "EduCh"]],
            "has_more": false, "total": 1
        ])

        let response = try await client.getCatalog(childId: 1, category: "edu")
        #expect(response.videos.count == 1)
        #expect(!response.hasMore)
    }

    @Test("Get catalog — empty")
    func getCatalogEmpty() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/catalog", json: [
            "videos": [], "has_more": false, "total": 0
        ])

        let response = try await client.getCatalog(childId: 1)
        #expect(response.videos.isEmpty)
        #expect(response.total == 0)
    }

    @Test("Get catalog with watch_status filter")
    func getCatalogWithWatchStatus() async throws {
        let client = makeClient()
        MockURLProtocol.handlers["/api/catalog"] = { request in
            let url = request.url!
            let components = URLComponents(url: url, resolvingAgainstBaseURL: false)!
            let watchStatus = components.queryItems?.first(where: { $0.name == "watch_status" })?.value
            #expect(watchStatus == "unwatched")
            let data = try JSONSerialization.data(withJSONObject: [
                "videos": [], "has_more": false, "total": 0,
                "status_counts": ["all": 5, "unwatched": 3, "in_progress": 1, "watched": 1]
            ])
            let response = HTTPURLResponse(
                url: url, statusCode: 200, httpVersion: nil, headerFields: nil
            )!
            return (data, response)
        }

        let response = try await client.getCatalog(childId: 1, watchStatus: "unwatched")
        #expect(response.statusCounts?.unwatched == 3)
    }

    @Test("Get catalog with sort parameter")
    func getCatalogWithSort() async throws {
        let client = makeClient()
        MockURLProtocol.handlers["/api/catalog"] = { request in
            let url = request.url!
            let components = URLComponents(url: url, resolvingAgainstBaseURL: false)!
            let sortBy = components.queryItems?.first(where: { $0.name == "sort_by" })?.value
            #expect(sortBy == "title")
            let data = try JSONSerialization.data(withJSONObject: [
                "videos": [["video_id": "v1", "title": "Alpha", "channel_name": "Ch"]],
                "has_more": false, "total": 1
            ])
            let response = HTTPURLResponse(
                url: url, statusCode: 200, httpVersion: nil, headerFields: nil
            )!
            return (data, response)
        }

        let response = try await client.getCatalog(childId: 1, sortBy: "title")
        #expect(response.videos.count == 1)
    }

    // MARK: - Channels

    @Test("Get channels")
    func getChannels() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/channels", json: [
            "channels": [
                ["id": 1, "channel_name": "CrashCourse", "channel_id": "UCX6OQ", "status": "allowed", "category": "edu"]
            ]
        ])

        let channels = try await client.getChannels(childId: 1)
        #expect(channels.count == 1)
        #expect(channels[0].channelName == "CrashCourse")
    }

    // MARK: - Heartbeat

    @Test("Send heartbeat — remaining time")
    func sendHeartbeat() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/watch-heartbeat", json: ["remaining": 3600])

        let remaining = try await client.sendHeartbeat(videoId: "abc", childId: 1, seconds: 30)
        #expect(remaining == 3600)
    }

    @Test("Send heartbeat — no limit")
    func sendHeartbeatNoLimit() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/watch-heartbeat", json: ["remaining": -1])

        let remaining = try await client.sendHeartbeat(videoId: "abc", childId: 1, seconds: 30)
        #expect(remaining == -1)
    }

    @Test("Send heartbeat — outside schedule")
    func sendHeartbeatOutsideSchedule() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/watch-heartbeat", json: ["remaining": -2])

        let remaining = try await client.sendHeartbeat(videoId: "abc", childId: 1, seconds: 30)
        #expect(remaining == -2)
    }

    // MARK: - Time Status

    @Test("Get time status")
    func getTimeStatus() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/time-status", json: [
            "limit_min": 120, "used_min": 45.5, "remaining_min": 74.5,
            "remaining_sec": 4470, "exceeded": false
        ])

        let status = try await client.getTimeStatus(childId: 1)
        #expect(status.limitMin == 120)
        #expect(status.usedMin == 45.5)
        #expect(!status.exceeded)
    }

    @Test("Get time status — exceeded")
    func getTimeStatusExceeded() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/time-status", json: [
            "limit_min": 60, "used_min": 65, "remaining_min": 0,
            "remaining_sec": 0, "exceeded": true
        ])

        let status = try await client.getTimeStatus(childId: 1)
        #expect(status.exceeded)
        #expect(status.remainingSec == 0)
    }

    // MARK: - Schedule Status

    @Test("Get schedule status — allowed")
    func getScheduleStatus() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/schedule-status", json: [
            "allowed": true, "unlock_time": "", "start": "8:00 AM", "end": "8:00 PM",
            "minutes_remaining": 120
        ])

        let schedule = try await client.getScheduleStatus(childId: 1)
        #expect(schedule.allowed)
        #expect(schedule.start == "8:00 AM")
        #expect(schedule.end == "8:00 PM")
    }

    @Test("Get schedule status — blocked")
    func getScheduleStatusBlocked() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/schedule-status", json: [
            "allowed": false, "unlock_time": "8:00 AM", "start": "8:00 AM", "end": "8:00 PM",
            "minutes_remaining": -1
        ])

        let schedule = try await client.getScheduleStatus(childId: 1)
        #expect(!schedule.allowed)
        #expect(schedule.unlockTime == "8:00 AM")
    }

    // MARK: - Error Handling

    @Test("HTTP 401 error — invalid API key")
    func httpError401() async throws {
        let client = makeClient()
        MockURLProtocol.mockError(path: "/api/profiles", statusCode: 401, detail: "Invalid API key")

        do {
            _ = try await client.getProfiles()
            Issue.record("Should have thrown")
        } catch let error as APIError {
            if case .httpError(let code, let detail) = error {
                #expect(code == 401)
                #expect(detail == "Invalid API key")
            } else {
                Issue.record("Wrong error type: \(error)")
            }
        }
    }

    @Test("HTTP 404 error — child not found")
    func httpError404() async throws {
        let client = makeClient()
        MockURLProtocol.mockError(path: "/api/time-status", statusCode: 404, detail: "Child not found")

        do {
            _ = try await client.getTimeStatus(childId: 999)
            Issue.record("Should have thrown")
        } catch let error as APIError {
            if case .httpError(let code, let detail) = error {
                #expect(code == 404)
                #expect(detail.contains("not found"))
            } else {
                Issue.record("Wrong error type: \(error)")
            }
        }
    }

    @Test("HTTP 403 error — stream not approved")
    func httpError403Stream() async throws {
        let client = makeClient()
        MockURLProtocol.mockError(path: "/api/stream/abc", statusCode: 403, detail: "Video not approved")

        do {
            _ = try await client.getStreamURL(videoId: "abc", childId: 1)
            Issue.record("Should have thrown")
        } catch let error as APIError {
            if case .httpError(let code, _) = error {
                #expect(code == 403)
            } else {
                Issue.record("Wrong error type")
            }
        }
    }

    // MARK: - Auth Header

    @Test("Authorization header is sent with API key")
    func authHeaderSent() async throws {
        let client = makeClient()
        MockURLProtocol.handlers["/api/profiles"] = { request in
            let auth = request.value(forHTTPHeaderField: "Authorization")
            #expect(auth == "Bearer test-key")
            let data = try JSONSerialization.data(withJSONObject: ["profiles": []])
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil
            )!
            return (data, response)
        }

        _ = try await client.getProfiles()
    }

    // MARK: - Channel Request

    @Test("Request channel — pending")
    func requestChannelPending() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/request-channel", json: [
            "status": "pending", "channel_id": "UCabc123", "child_id": 1, "channel_name": "Cool Channel"
        ])

        let response = try await client.requestChannel(channelId: "UCabc123", childId: 1)
        #expect(response.status == "pending")
        #expect(response.channelName == "Cool Channel")
    }

    @Test("Request channel — approved")
    func requestChannelApproved() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/request-channel", json: [
            "status": "approved", "channel_id": "UCabc123", "child_id": 1, "channel_name": "Cool Channel"
        ])

        let response = try await client.requestChannel(channelId: "UCabc123", childId: 1)
        #expect(response.status == "approved")
    }

    @Test("Get channel request status")
    func getChannelRequestStatus() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/channel-request-status/UCabc123", json: ["status": "pending"])

        let status = try await client.getChannelRequestStatus(channelId: "UCabc123", childId: 1)
        #expect(status == "pending")
    }

    // MARK: - Watch Status

    @Test("Set watch status — watched")
    func setWatchStatusWatched() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/watch/status", json: [
            "status": "updated", "video_id": "abc12345678", "child_id": 1, "watch_status": "watched"
        ])

        // Best-effort — just verify no crash
        await client.setWatchStatus(videoId: "abc12345678", childId: 1, status: "watched")
    }

    @Test("Set watch status — unwatched")
    func setWatchStatusUnwatched() async throws {
        let client = makeClient()
        MockURLProtocol.mock(path: "/api/watch/status", json: [
            "status": "updated", "video_id": "abc12345678", "child_id": 1, "watch_status": NSNull()
        ])

        await client.setWatchStatus(videoId: "abc12345678", childId: 1, status: "unwatched")
    }

    @Test("Set watch status — error is swallowed")
    func setWatchStatusError() async throws {
        let client = makeClient()
        MockURLProtocol.mockError(path: "/api/watch/status", statusCode: 404, detail: "No access record")

        // Should not throw — best-effort
        await client.setWatchStatus(videoId: "abc12345678", childId: 1, status: "watched")
    }

    // MARK: - Auth Header

    @Test("No Authorization header when key is empty")
    func noAuthWhenKeyEmpty() async throws {
        MockURLProtocol.reset()
        let noAuthClient = APIClient(baseURL: "http://test.local:8080", apiKey: "", session: makeMockSession())
        MockURLProtocol.handlers["/api/profiles"] = { request in
            let auth = request.value(forHTTPHeaderField: "Authorization")
            #expect(auth == nil)
            let data = try JSONSerialization.data(withJSONObject: ["profiles": []])
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil
            )!
            return (data, response)
        }

        _ = try await noAuthClient.getProfiles()
    }
}
