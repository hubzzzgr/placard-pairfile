import Foundation

enum PairingFileStore {
    enum ImportError: LocalizedError {
        case emptyFile
        case invalidPropertyList

        var errorDescription: String? {
            switch self {
            case .emptyFile:
                return "The selected .plist file is empty."
            case .invalidPropertyList:
                return "Placard could not read this .plist file. Choose an XML or binary property-list file containing a dictionary."
            }
        }
    }

    /// Preserve the original record for Airlift's Lockdown/Remote Pairing parsers.
    /// Import checks only the plist container; Airlift validates credentials when connecting.
    static func save(_ data: Data, in directory: URL) throws -> URL {
        guard !data.isEmpty else { throw ImportError.emptyFile }
        guard let record = (try? PropertyListSerialization.propertyList(from: data, format: nil)) as? [String: Any],
              !record.isEmpty else {
            throw ImportError.invalidPropertyList
        }

        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let destination = directory.appendingPathComponent("aircard_pairing.plist")
        try data.write(to: destination, options: .atomic)
        return destination
    }
}
