import Foundation

// Uploader sends a buffered RecordedSession to the server on Wi-Fi
// (architecture.md §7, §8). It builds the multipart POST /sessions request:
//   - a JSON part describing the session + annotations + corrections
//   - a binary part carrying the compressed skeleton blob
// and sets:
//   - Idempotency-Key: a per-attempt UUID so transport retries dedupe
//   - the durable client_session_id lives INSIDE the JSON (session identity);
//     re-uploading the same client_session_id is an UPDATE (last-write-wins on
//     annotations; the skeleton blob is immutable once stored).
//
// CONCRETE request construction. Network policy (Wi-Fi-only gating, retry/
// backoff, background URLSession) is a host-app concern; hooks are noted.

public struct UploadResponse: Sendable, Decodable {
    public let sessionId: String
    public let clientSessionId: String
    public let created: Bool
    public let annotationCount: Int

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case clientSessionId = "client_session_id"
        case created
        case annotationCount = "annotation_count"
    }
}

public enum UploadError: Error {
    case http(Int, String)
    case encoding(Error)
}

public final class Uploader {
    private let baseURL: URL
    private let token: String
    private let session: URLSession
    private let sdkVersion: String

    public init(baseURL: URL, token: String,
                session: URLSession = .shared, sdkVersion: String = GymboxSDKInfo.version) {
        self.baseURL = baseURL
        self.token = token
        self.session = session
        self.sdkVersion = sdkVersion
    }

    /// Upload a recorded session. `idempotencyKey` should be stable across
    /// retries of the SAME attempt and fresh for a genuinely new attempt; it
    /// defaults to a new UUID.
    public func upload(_ recorded: RecordedSession,
                       userId: String,
                       device: DeviceDescriptor,
                       skeletonBlob: Data,
                       idempotencyKey: String = UUID().uuidString) async throws -> UploadResponse {
        let boundary = "gymbox.\(UUID().uuidString)"
        var req = URLRequest(url: baseURL.appendingPathComponent("sessions"))
        req.httpMethod = "POST"
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        req.setValue(idempotencyKey, forHTTPHeaderField: "Idempotency-Key")

        let jsonPart: Data
        do {
            jsonPart = try Self.encodeBody(recorded, userId: userId, device: device,
                                           sdkVersion: sdkVersion, blobPartName: "skeleton")
        } catch {
            throw UploadError.encoding(error)
        }

        var body = Data()
        func boundaryLine() { body.append("--\(boundary)\r\n".data(using: .utf8)!) }

        // JSON part
        boundaryLine()
        body.append("Content-Disposition: form-data; name=\"payload\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: application/json\r\n\r\n".data(using: .utf8)!)
        body.append(jsonPart)
        body.append("\r\n".data(using: .utf8)!)

        // Skeleton blob part
        boundaryLine()
        body.append("Content-Disposition: form-data; name=\"skeleton\"; filename=\"skeleton.bin\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: application/octet-stream\r\n\r\n".data(using: .utf8)!)
        body.append(skeletonBlob)
        body.append("\r\n".data(using: .utf8)!)

        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        req.httpBody = body

        let (data, response) = try await session.data(for: req)
        guard let http = response as? HTTPURLResponse else { throw UploadError.http(-1, "") }
        guard (200..<300).contains(http.statusCode) else {
            throw UploadError.http(http.statusCode, String(data: data, encoding: .utf8) ?? "")
        }
        return try JSONDecoder().decode(UploadResponse.self, from: data)
    }

    /// Build the JSON payload matching the server's SessionUploadIn schema.
    static func encodeBody(_ r: RecordedSession, userId: String, device: DeviceDescriptor,
                           sdkVersion: String, blobPartName: String) throws -> Data {
        let iso = ISO8601DateFormatter()
        let payload: [String: Any] = [
            "session": [
                "client_session_id": r.clientSessionId,
                "user_id": userId,
                "started_at_utc": iso.string(from: r.startedAtUTC),
                "ended_at_utc": iso.string(from: r.endedAtUTC),
                "device": [
                    "model": device.model,
                    "ios_version": device.iosVersion,
                    "sdk_version": sdkVersion
                ],
                "exercise_id": r.exerciseId,
                "weight_kg": r.weightKg as Any
            ],
            "annotations": r.annotations.map { a -> [String: Any] in
                [
                    "client_annotation_id": a.clientAnnotationId,
                    "layer_id": a.layerId,
                    "start_s": a.startSeconds,
                    "end_s": a.endSeconds,
                    "value": a.value,
                    "source": a.source,
                    "confidence": a.confidence as Any
                ]
            },
            "user_corrections": [],
            "skeleton_blob": ["format": "gymbox-v1-skeleton", "url": blobPartName]
        ]
        return try JSONSerialization.data(withJSONObject: payload, options: [])
    }
}

/// Minimal device descriptor for the upload envelope.
public struct DeviceDescriptor: Sendable {
    public let model: String
    public let iosVersion: String
    public init(model: String, iosVersion: String) {
        self.model = model
        self.iosVersion = iosVersion
    }
}
