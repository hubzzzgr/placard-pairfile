import Foundation

enum PairingFileStore {
    enum ImportError: LocalizedError {
        case invalidPairingFile

        var errorDescription: String? {
            "This is not a valid pairing file. Choose a .plist, .mobiledevicepairing, or .mobilepair file created for this iPhone."
        }
    }

    /// Preserve XML/binary pairing records exactly; never replace a saved record with invalid data.
    static func save(_ data: Data, in directory: URL) throws -> URL {
        guard let record = (try? PropertyListSerialization.propertyList(from: data, format: nil)) as? [String: Any],
              ["HostID", "SystemBUID"].allSatisfy({ !(record[$0] as? String ?? "").isEmpty }),
              ["DeviceCertificate", "HostCertificate", "HostPrivateKey", "RootCertificate", "RootPrivateKey"]
                .allSatisfy({ !(record[$0] as? Data ?? Data()).isEmpty }) else {
            throw ImportError.invalidPairingFile
        }

        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let destination = directory.appendingPathComponent("aircard_pairing.plist")
        try data.write(to: destination, options: .atomic)
        return destination
    }
}
