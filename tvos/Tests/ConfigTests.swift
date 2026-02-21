import Testing
@testable import KidsTubeCore

@Suite("Config")
struct ConfigTests {

    @Test("Server base URL is a valid HTTP URL")
    func serverBaseURLIsValid() {
        #expect(!Config.serverBaseURL.isEmpty)
        #expect(Config.serverBaseURL.hasPrefix("http"))
    }

    @Test("API key has a default value")
    func apiKeyHasDefault() {
        #expect(!Config.apiKey.isEmpty)
    }

    @Test("Poll interval is between 1 and 30 seconds")
    func pollIntervalReasonable() {
        #expect(Config.pollInterval >= 1.0)
        #expect(Config.pollInterval <= 30.0)
    }

    @Test("Heartbeat interval is between 10 and 120 seconds")
    func heartbeatIntervalReasonable() {
        #expect(Config.heartbeatInterval >= 10.0)
        #expect(Config.heartbeatInterval <= 120.0)
    }

    @Test("Heartbeat seconds matches interval")
    func heartbeatSecondsMatchesInterval() {
        #expect(Double(Config.heartbeatSeconds) == Config.heartbeatInterval)
    }

    @Test("Catalog page size is within server limits")
    func catalogPageSizeValid() {
        #expect(Config.catalogPageSize > 0)
        #expect(Config.catalogPageSize <= 100)
    }

    @Test("App name is not empty")
    func appNameNotEmpty() {
        #expect(!Config.appName.isEmpty)
    }

    @Test("Overlay display duration is positive")
    func overlayDisplayDurationPositive() {
        #expect(Config.overlayDisplayDuration > 0)
    }
}
