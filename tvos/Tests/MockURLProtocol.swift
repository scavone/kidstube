import Foundation

/// A custom URLProtocol that intercepts network requests for testing.
/// Thread-safe: uses a lock to protect the handlers dictionary.
final class MockURLProtocol: URLProtocol {
    private static let lock = NSLock()
    private static var _handlers: [String: @Sendable (URLRequest) throws -> (Data, HTTPURLResponse)] = [:]

    static var handlers: [String: @Sendable (URLRequest) throws -> (Data, HTTPURLResponse)] {
        get { lock.withLock { _handlers } }
        set { lock.withLock { _handlers = newValue } }
    }

    /// Set a mock response for a given path prefix.
    static func mock(
        path: String,
        statusCode: Int = 200,
        json: Any
    ) {
        // Pre-serialize the JSON data to avoid capturing `json` (which may not be Sendable)
        let data = try! JSONSerialization.data(withJSONObject: json)
        lock.withLock {
            _handlers[path] = { request in
                let response = HTTPURLResponse(
                    url: request.url!,
                    statusCode: statusCode,
                    httpVersion: nil,
                    headerFields: ["Content-Type": "application/json"]
                )!
                return (data, response)
            }
        }
    }

    /// Set a mock error response.
    static func mockError(path: String, statusCode: Int, detail: String) {
        mock(path: path, statusCode: statusCode, json: ["detail": detail])
    }

    /// Clear all mocks.
    static func reset() {
        lock.withLock { _handlers.removeAll() }
    }

    // MARK: - URLProtocol

    override class func canInit(with request: URLRequest) -> Bool {
        return true
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest {
        return request
    }

    override func startLoading() {
        guard let url = request.url else {
            client?.urlProtocol(self, didFailWithError: URLError(.badURL))
            return
        }

        let path = url.path
        let snapshot = MockURLProtocol.handlers
        let handler = snapshot.first { path.hasPrefix($0.key) || path == $0.key }

        guard let (_, mockHandler) = handler else {
            client?.urlProtocol(self, didFailWithError: URLError(.unsupportedURL))
            return
        }

        do {
            let (data, response) = try mockHandler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

/// Creates a URLSession configured with MockURLProtocol for testing.
func makeMockSession() -> URLSession {
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [MockURLProtocol.self]
    return URLSession(configuration: config)
}
