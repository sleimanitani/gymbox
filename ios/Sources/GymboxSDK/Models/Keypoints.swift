import Foundation

/// The 33 MediaPipe Pose landmark names, in index order.
///
/// THIS MUST STAY BYTE-FOR-BYTE IN SYNC WITH the Python registry
/// (gymbox/dsl/keypoints.py). A DSL spec authored against one and run against
/// the other only agrees if the joint indices match. Gate B depends on it.
public enum Keypoints {
    public static let names: [String] = [
        "nose",             // 0
        "left_eye_inner",   // 1
        "left_eye",         // 2
        "left_eye_outer",   // 3
        "right_eye_inner",  // 4
        "right_eye",        // 5
        "right_eye_outer",  // 6
        "left_ear",         // 7
        "right_ear",        // 8
        "mouth_left",       // 9
        "mouth_right",      // 10
        "left_shoulder",    // 11
        "right_shoulder",   // 12
        "left_elbow",       // 13
        "right_elbow",      // 14
        "left_wrist",       // 15
        "right_wrist",      // 16
        "left_pinky",       // 17
        "right_pinky",      // 18
        "left_index",       // 19
        "right_index",      // 20
        "left_thumb",       // 21
        "right_thumb",      // 22
        "left_hip",         // 23
        "right_hip",        // 24
        "left_knee",        // 25
        "right_knee",       // 26
        "left_ankle",       // 27
        "right_ankle",      // 28
        "left_heel",        // 29
        "right_heel",       // 30
        "left_foot_index",  // 31
        "right_foot_index"  // 32
    ]

    public static let count = names.count

    private static let indexByName: [String: Int] =
        Dictionary(uniqueKeysWithValues: names.enumerated().map { ($1, $0) })

    /// Index of a landmark by name. Returns nil if unknown.
    public static func index(of name: String) -> Int? {
        indexByName[name]
    }

    /// Name of a landmark by index. Traps on out-of-range (programmer error).
    public static func name(of index: Int) -> String {
        names[index]
    }
}

// Compile-time-ish sanity: there are exactly 33 landmarks.
#if DEBUG
private let _keypointCountCheck: Void = {
    assert(Keypoints.count == 33, "MediaPipe Pose has 33 landmarks")
}()
#endif
