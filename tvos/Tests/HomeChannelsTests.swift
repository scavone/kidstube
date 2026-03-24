/// Test plan for Issue #3: Home screen redesign — frontend models and API client.
///
/// Covers:
/// 1. New Codable model for home channel data (decoding, edge cases)
/// 2. APIClient method for fetching home channels
/// 3. Error handling for the new endpoint
///
/// Expected new model (HomeChannel or similar):
///   struct HomeChannel: Codable, Identifiable {
///       let channelId: String        // "UC..."
///       let channelName: String
///       let handle: String?          // "@handle"
///       let avatarUrl: String?       // channel avatar for the row
///       let bannerUrl: String?       // banner image for featured section
///       let category: String?
///       let latestVideo: LatestVideo? // most recent video
///   }
///
///   struct LatestVideo: Codable {
///       let videoId: String
///       let title: String
///       let thumbnailUrl: String?
///       let duration: Int?
///       let published: Int?          // unix timestamp
///   }
///
/// Expected APIClient method:
///   func getHomeChannels(childId: Int) async throws -> [HomeChannel]

import Testing
import Foundation
@testable import KidsTubeCore

// MARK: - HomeChannel Model Decoding Tests

@Suite("HomeChannel Model")
struct HomeChannelModelTests {

    @Test("Decode full home channel from JSON")
    func decodeFullHomeChannel() throws {
        // Test plan: verify all fields decode correctly from a complete JSON object
        // {
        //     "channel_id": "UCX6OQ",
        //     "channel_name": "CrashCourse",
        //     "handle": "@crashcourse",
        //     "avatar_url": "https://yt3.ggpht.com/...",
        //     "banner_url": "https://yt3.ggpht.com/banner/...",
        //     "category": "edu",
        //     "latest_video": {
        //         "video_id": "dQw4w9WgXcQ",
        //         "title": "Latest Episode",
        //         "thumbnail_url": "https://i.ytimg.com/vi/.../hqdefault.jpg",
        //         "duration": 600,
        //         "published": 1700000000
        //     }
        // }
        // TODO: implement once model exists
    }

    @Test("Decode home channel with null optional fields")
    func decodeMinimalHomeChannel() throws {
        // Test plan: channel with no handle, no avatar, no banner, no latest_video
        // Should decode without errors, optional fields are nil
        // TODO: implement once model exists
    }

    @Test("Decode home channel with null latest_video")
    func decodeHomeChannelNoLatestVideo() throws {
        // Test plan: channel exists but has no videos yet
        // latest_video should be nil
        // TODO: implement once model exists
    }

    @Test("HomeChannel Identifiable uses channelId")
    func homeChannelIdentifiable() throws {
        // Test plan: verify id property returns channelId
        // This is critical for SwiftUI ForEach rendering in the channel row
        // TODO: implement once model exists
    }

    @Test("Decode array of home channels preserves order")
    func decodeHomeChannelsArray() throws {
        // Test plan: decode a JSON array of 3 channels
        // Verify order is preserved (backend sends sorted by latest publish date)
        // TODO: implement once model exists
    }
}

// MARK: - LatestVideo Model Tests

@Suite("LatestVideo Model")
struct LatestVideoModelTests {

    @Test("Decode latest video with all fields")
    func decodeFullLatestVideo() throws {
        // Test plan: all fields present
        // video_id, title, thumbnail_url, duration, published
        // TODO: implement once model exists
    }

    @Test("Decode latest video with minimal fields")
    func decodeMinimalLatestVideo() throws {
        // Test plan: only video_id and title required
        // thumbnail_url, duration, published can be nil
        // TODO: implement once model exists
    }

    @Test("Duration formatting for latest video")
    func latestVideoDurationFormatting() throws {
        // Test plan: if LatestVideo has a formattedDuration computed property,
        // verify formatting matches Video model convention (e.g., "1:30", "1:01:01")
        // TODO: implement once model exists
    }
}

// MARK: - HomeChannels Response Model Tests

@Suite("HomeChannelsResponse")
struct HomeChannelsResponseTests {

    @Test("Decode response wrapper with channels array")
    func decodeHomeChannelsResponse() throws {
        // Test plan: top-level response has "channels" key containing array
        // {"channels": [...]}
        // TODO: implement once model exists
    }

    @Test("Decode response with empty channels")
    func decodeEmptyHomeChannelsResponse() throws {
        // Test plan: {"channels": []} should decode to empty array
        // This happens when a child has no approved channels
        // TODO: implement once model exists
    }
}

// MARK: - APIClient Home Channels Tests

@Suite("APIClient Home Channels", .serialized)
struct APIClientHomeChannelsTests {

    private func makeClient() -> APIClient {
        MockURLProtocol.reset()
        let session = makeMockSession()
        return APIClient(baseURL: "http://test.local:8080", apiKey: "test-key", session: session)
    }

    @Test("Get home channels returns list")
    func getHomeChannels() async throws {
        // Test plan: mock the endpoint, verify APIClient returns decoded channels
        // let client = makeClient()
        // MockURLProtocol.mock(path: "/api/home/channels", json: [
        //     "channels": [
        //         [
        //             "channel_id": "UCX6OQ",
        //             "channel_name": "CrashCourse",
        //             "handle": "@crashcourse",
        //             "avatar_url": "https://yt3.ggpht.com/...",
        //             "category": "edu",
        //             "latest_video": [
        //                 "video_id": "abc12345678",
        //                 "title": "Latest",
        //                 "thumbnail_url": "https://i.ytimg.com/vi/.../hq.jpg",
        //                 "duration": 300,
        //                 "published": 1700000000
        //             ]
        //         ]
        //     ]
        // ])
        // let channels = try await client.getHomeChannels(childId: 1)
        // #expect(channels.count == 1)
        // #expect(channels[0].channelName == "CrashCourse")
        // #expect(channels[0].latestVideo?.videoId == "abc12345678")
    }

    @Test("Get home channels — empty list")
    func getHomeChannelsEmpty() async throws {
        // Test plan: child with no channels returns empty array
        // let client = makeClient()
        // MockURLProtocol.mock(path: "/api/home/channels", json: ["channels": []])
        // let channels = try await client.getHomeChannels(childId: 1)
        // #expect(channels.isEmpty)
    }

    @Test("Get home channels — sends child_id as query param")
    func getHomeChannelsSendsChildId() async throws {
        // Test plan: verify the request URL includes ?child_id=N
        // Use MockURLProtocol.handlers to inspect the request
        // let client = makeClient()
        // MockURLProtocol.handlers["/api/home/channels"] = { request in
        //     let url = request.url!
        //     let components = URLComponents(url: url, resolvingAgainstBaseURL: false)!
        //     let childId = components.queryItems?.first(where: { $0.name == "child_id" })?.value
        //     #expect(childId == "1")
        //     let data = try JSONSerialization.data(withJSONObject: ["channels": []])
        //     let response = HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: nil)!
        //     return (data, response)
        // }
        // _ = try await client.getHomeChannels(childId: 1)
    }

    @Test("Get home channels — sends Authorization header")
    func getHomeChannelsAuthHeader() async throws {
        // Test plan: verify Bearer token is included in request
        // Same pattern as existing authHeaderSent test
    }

    @Test("Get home channels — HTTP 404 error for invalid child")
    func getHomeChannels404() async throws {
        // Test plan: server returns 404 for unknown child_id
        // Verify APIError.httpError(404, ...) is thrown
        // let client = makeClient()
        // MockURLProtocol.mockError(path: "/api/home/channels", statusCode: 404, detail: "Child not found")
        // do {
        //     _ = try await client.getHomeChannels(childId: 999)
        //     Issue.record("Should have thrown")
        // } catch let error as APIError {
        //     if case .httpError(let code, _) = error {
        //         #expect(code == 404)
        //     }
        // }
    }

    @Test("Get home channels — HTTP 401 unauthenticated")
    func getHomeChannels401() async throws {
        // Test plan: verify proper error for missing/wrong API key
    }
}

// MARK: - Focus-Driven Banner Update (View State)

// NOTE: View-level focus behavior cannot be unit tested via swift test,
// but we document what should be manually verified:
//
// [ ] Focusing a channel in the row updates the featured banner
// [ ] Banner shows the latest_video thumbnail/title from the focused channel
// [ ] Banner transitions smoothly (animation)
// [ ] Clicking the banner plays the focused channel's latest video
// [ ] Clicking a channel navigates to channel detail / filtered catalog
// [ ] Empty state: no channels shows appropriate placeholder
// [ ] Channel row scrolls horizontally with proper tvOS focus behavior
// [ ] Category rows still appear below the channel row
// [ ] Back navigation from channel detail returns to home screen
