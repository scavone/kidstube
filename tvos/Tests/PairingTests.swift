/// Test plan for Issue #8: QR code / pin code pairing flow.
///
/// Covers:
/// 1. PairingSession model decoding (token, pin, expires_in)
/// 2. PairingStatus model decoding (pending, confirmed with credentials, expired)
/// 3. APIClient pairing methods (requestPairing, pollPairingStatus)
/// 4. KeychainService — secure credential storage
/// 5. Integration: endpoints referenced vs. backend provided
///
/// New frontend files expected:
///   Views/Pairing/PairingView.swift        — QR code + PIN display screen
///   Services/KeychainService.swift         — Keychain CRUD for server URL + API key
///   Models/PairingModels.swift             — PairingSession, PairingStatus models
///   Services/APIClient.swift (modified)    — requestPairing(), pollPairingStatus()
///   Services/Config.swift (modified)       — Read from Keychain instead of Info.plist
///   App/ContentView.swift (modified)       — Show PairingView on first launch

import Testing
import Foundation
@testable import KidsTubeCore

// MARK: - PairingSession Model Tests
//
// Activate these tests once PairingSession model is added to Models/.
//
// @Suite("PairingSession")
// struct PairingSessionTests {
//
//     @Test("Decode pairing session response")
//     func decodeSession() throws {
//         let json = """
//         {
//             "token": "abc123def456_-xyz",
//             "pin": "482931",
//             "expires_in": 300
//         }
//         """.data(using: .utf8)!
//
//         let session = try JSONDecoder().decode(PairingSession.self, from: json)
//         #expect(session.token == "abc123def456_-xyz")
//         #expect(session.pin == "482931")
//         #expect(session.expiresIn == 300)
//     }
//
//     @Test("Decode pairing session with optional device_name")
//     func decodeWithDeviceName() throws {
//         let json = """
//         {
//             "token": "tok123",
//             "pin": "123456",
//             "expires_in": 300,
//             "device_name": "Living Room TV"
//         }
//         """.data(using: .utf8)!
//
//         let session = try JSONDecoder().decode(PairingSession.self, from: json)
//         #expect(session.token == "tok123")
//     }
// }

// MARK: - PairingStatus Model Tests
//
// Activate these tests once PairingStatus model is added to Models/.
//
// @Suite("PairingStatus")
// struct PairingStatusTests {
//
//     @Test("Decode pending status")
//     func decodePending() throws {
//         let json = """
//         {"status": "pending"}
//         """.data(using: .utf8)!
//
//         let status = try JSONDecoder().decode(PairingStatus.self, from: json)
//         #expect(status.status == "pending")
//         #expect(status.apiKey == nil)
//         #expect(status.serverUrl == nil)
//     }
//
//     @Test("Decode confirmed status with credentials")
//     func decodeConfirmed() throws {
//         let json = """
//         {
//             "status": "confirmed",
//             "api_key": "long-lived-key-abcdef123456",
//             "server_url": "http://192.168.1.100:8080"
//         }
//         """.data(using: .utf8)!
//
//         let status = try JSONDecoder().decode(PairingStatus.self, from: json)
//         #expect(status.status == "confirmed")
//         #expect(status.apiKey == "long-lived-key-abcdef123456")
//         #expect(status.serverUrl == "http://192.168.1.100:8080")
//     }
//
//     @Test("Decode expired status")
//     func decodeExpired() throws {
//         let json = """
//         {"status": "expired"}
//         """.data(using: .utf8)!
//
//         let status = try JSONDecoder().decode(PairingStatus.self, from: json)
//         #expect(status.status == "expired")
//         #expect(status.apiKey == nil)
//     }
// }

// MARK: - APIClient Pairing Tests
//
// Activate these tests once requestPairing() and pollPairingStatus() are added to APIClient.
//
// @Suite("APIClient Pairing", .serialized)
// struct APIClientPairingTests {
//
//     private func makeClient(baseURL: String = "http://test.local:8080") -> APIClient {
//         MockURLProtocol.reset()
//         let session = makeMockSession()
//         return APIClient(baseURL: baseURL, apiKey: "", session: session)
//     }
//
//     @Test("Request pairing — returns session")
//     func requestPairing() async throws {
//         let client = makeClient()
//         MockURLProtocol.mock(path: "/api/pair/request", json: [
//             "token": "test-token-123",
//             "pin": "482931",
//             "expires_in": 300
//         ])
//
//         let session = try await client.requestPairing(deviceName: "Test TV")
//         #expect(session.token == "test-token-123")
//         #expect(session.pin == "482931")
//         #expect(session.expiresIn == 300)
//     }
//
//     @Test("Poll pairing status — pending")
//     func pollStatusPending() async throws {
//         let client = makeClient()
//         MockURLProtocol.mock(path: "/api/pair/status/", json: [
//             "status": "pending"
//         ])
//
//         let status = try await client.pollPairingStatus(token: "test-token")
//         #expect(status.status == "pending")
//         #expect(status.apiKey == nil)
//     }
//
//     @Test("Poll pairing status — confirmed with credentials")
//     func pollStatusConfirmed() async throws {
//         let client = makeClient()
//         MockURLProtocol.mock(path: "/api/pair/status/", json: [
//             "status": "confirmed",
//             "api_key": "new-device-key-xyz",
//             "server_url": "http://192.168.1.100:8080"
//         ])
//
//         let status = try await client.pollPairingStatus(token: "test-token")
//         #expect(status.status == "confirmed")
//         #expect(status.apiKey == "new-device-key-xyz")
//         #expect(status.serverUrl == "http://192.168.1.100:8080")
//     }
//
//     @Test("Poll pairing status — expired")
//     func pollStatusExpired() async throws {
//         let client = makeClient()
//         MockURLProtocol.mock(path: "/api/pair/status/", json: [
//             "status": "expired"
//         ])
//
//         let status = try await client.pollPairingStatus(token: "test-token")
//         #expect(status.status == "expired")
//     }
//
//     @Test("Poll pairing status — token not found returns error")
//     func pollStatusNotFound() async throws {
//         let client = makeClient()
//         MockURLProtocol.mockError(path: "/api/pair/status/", statusCode: 404, detail: "Token not found")
//
//         do {
//             _ = try await client.pollPairingStatus(token: "bad-token")
//             Issue.record("Should have thrown")
//         } catch {
//             #expect(error is APIError)
//         }
//     }
//
//     @Test("Request pairing — no auth header sent")
//     func requestPairingNoAuth() async throws {
//         let client = makeClient()
//         MockURLProtocol.mock(path: "/api/pair/request", json: [
//             "token": "t", "pin": "123456", "expires_in": 300
//         ])
//
//         _ = try await client.requestPairing()
//     }
// }

// MARK: - KeychainService Tests
//
// NOTE: KeychainService uses the iOS/tvOS Keychain which requires the Security
// framework and a signed app context. These tests cannot run via `swift test`
// (Package.swift excludes Services/ that depend on platform APIs).
// They are verified via xcodebuild only.
//
// Documented here for the manual QA checklist:
//
// KeychainService.saveCredentials(serverURL:apiKey:):
// - Saves both values to Keychain
// - Overwrites existing values on re-pair
// - Returns success/failure
//
// KeychainService.loadCredentials() -> (serverURL: String, apiKey: String)?:
// - Returns nil when no credentials stored (first launch)
// - Returns saved values after pairing
// - Survives app restart (Keychain persistence)
//
// KeychainService.deleteCredentials():
// - Removes both values from Keychain
// - loadCredentials() returns nil after delete
// - Used for "re-pair" / "forget server" flow

// MARK: - Integration Check: Endpoints Used by Pairing Flow

// This section documents which API endpoints the pairing flow uses,
// to be verified against the backend during Phase 2 review.
//
// PairingView:
//   POST /api/pair/request           — initiate pairing session (NO auth)
//   GET  /api/pair/status/{token}    — poll for confirmation (NO auth)
//
// Admin confirm (not in tvOS app):
//   POST /api/pair/confirm/{token}   — admin confirms pairing (requires auth)
//   POST /api/pair/confirm-by-pin    — admin confirms via PIN (requires auth)
//
// Device management (admin only):
//   GET    /api/devices              — list paired devices (requires auth)
//   DELETE /api/devices/{device_id}  — revoke a device (requires auth)
//
// ContentView (modified):
//   On launch: KeychainService.loadCredentials()
//   If nil → show PairingView
//   If present → initialize APIClient with Keychain values, show normal app
//
// Config.swift (modified):
//   serverBaseURL and apiKey should read from Keychain first,
//   fall back to Info.plist/Secrets.xcconfig for backward compatibility
//
// NOTE: Pairing endpoints (request, status) must NOT require auth.
// The TV app doesn't have credentials until pairing completes.

// MARK: - Manual QA Checklist (View-Level, Cannot Unit Test)
//
// First Launch (No Credentials):
// [ ] App shows PairingView instead of profile picker
// [ ] QR code is displayed prominently
// [ ] PIN is displayed in large, readable text below QR code
// [ ] Expiration countdown timer is visible
// [ ] "Waiting for confirmation..." spinner/animation shown
//
// Pairing Flow:
// [ ] QR code contains the pairing token (or a URL with token)
// [ ] After parent confirms, screen transitions to profile picker
// [ ] Credentials are saved to Keychain on successful pairing
// [ ] If pairing expires, "Try Again" button regenerates token + PIN
// [ ] Error states (network failure) show appropriate message
//
// Subsequent Launches:
// [ ] App skips PairingView and goes straight to profile picker
// [ ] API calls use Keychain-stored credentials
// [ ] If Keychain credentials are invalid (revoked), app shows error
//
// Re-Pair Flow:
// [ ] "Re-pair" / "Forget Server" option accessible from settings/profile
// [ ] Clears Keychain credentials
// [ ] Returns to PairingView
// [ ] New pairing generates fresh token + PIN
//
// Security:
// [ ] Keychain items use kSecAttrAccessible = kSecAttrAccessibleAfterFirstUnlock
// [ ] Credentials are NOT logged to console
// [ ] Credentials are NOT stored in UserDefaults
// [ ] QR code data does not include the API key (only the token)
// [ ] PIN is not sent in plain text in any GET request URL
