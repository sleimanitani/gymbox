import Foundation

// ExerciseCatalog is the client side of the /exercises OTA spec channel
// (architecture.md §11). It fetches ExerciseSpecs from the server, caches them
// by id with their ETag, and revalidates with If-None-Match so unchanged specs
// return 304 and aren't re-downloaded. The cached spec is what the on-device
// DSLInterpreter runs.
//
// CONCRETE: fetch + ETag revalidation + in-memory cache. Disk persistence of
// the cache is a host-app concern (inject a CatalogStore) and left as a hook.

public struct CachedSpec: Sendable {
    public let spec: ExerciseSpec
    public let etag: String?
}

/// Optional persistence hook so specs survive app launches. The host app may
/// back this with the file system or a database.
public protocol CatalogStore: AnyObject {
    func load(id: String) -> CachedSpec?
    func save(id: String, cached: CachedSpec)
}

public enum CatalogError: Error {
    case http(Int)
    case notModifiedButNoCache
    case decoding(Error)
}

public final class ExerciseCatalog {
    private let baseURL: URL
    private let token: String
    private let session: URLSession
    private let store: CatalogStore?
    private var memory: [String: CachedSpec] = [:]

    public init(baseURL: URL, token: String,
                session: URLSession = .shared, store: CatalogStore? = nil) {
        self.baseURL = baseURL
        self.token = token
        self.session = session
        self.store = store
    }

    private func cached(_ id: String) -> CachedSpec? {
        memory[id] ?? store?.load(id: id)
    }

    private func put(_ id: String, _ cached: CachedSpec) {
        memory[id] = cached
        store?.save(id: id, cached: cached)
    }

    /// Fetch a spec by id, revalidating against the cache via If-None-Match.
    /// Returns the cached spec on a 304.
    public func fetch(id: String) async throws -> ExerciseSpec {
        var req = URLRequest(url: baseURL.appendingPathComponent("exercises/\(id)"))
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        if let etag = cached(id)?.etag {
            req.setValue(etag, forHTTPHeaderField: "If-None-Match")
        }

        let (data, response) = try await session.data(for: req)
        guard let http = response as? HTTPURLResponse else { throw CatalogError.http(-1) }

        switch http.statusCode {
        case 200:
            do {
                let spec = try ExerciseSpec.decode(from: data)
                let etag = http.value(forHTTPHeaderField: "ETag")
                put(id, CachedSpec(spec: spec, etag: etag))
                return spec
            } catch {
                throw CatalogError.decoding(error)
            }
        case 304:
            guard let c = cached(id) else { throw CatalogError.notModifiedButNoCache }
            return c.spec
        default:
            throw CatalogError.http(http.statusCode)
        }
    }
}
