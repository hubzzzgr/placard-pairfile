#!/usr/bin/env python3
"""Exercise the production pairing record store with synthetic credentials only."""
import pathlib
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]

with tempfile.TemporaryDirectory(prefix="placard-pairing-test-") as temporary:
    temporary = pathlib.Path(temporary)
    main = temporary / "main.swift"
    main.write_text(r'''
import Foundation

let directory = URL(fileURLWithPath: CommandLine.arguments[1]).appendingPathComponent("Documents")
let destination = directory.appendingPathComponent("aircard_pairing.plist")
let record: [String: Any] = [
    "HostID": "test-host", "SystemBUID": "test-system", "WiFiMACAddress": "00:00:00:00:00:00",
    "DeviceCertificate": Data("test-device".utf8), "HostCertificate": Data("test-host".utf8),
    "HostPrivateKey": Data("test-key".utf8), "RootCertificate": Data("test-root".utf8),
    "RootPrivateKey": Data("test-root-key".utf8)
]
func assertContents(_ url: URL, equalTo expected: Data) throws {
    let actual = try Data(contentsOf: url)
    precondition(actual == expected)
}
let formats: [PropertyListSerialization.PropertyListFormat] = [.xml, .binary]
let remoteRecord: [String: Any] = [
    "identifier": "test-remote-host", "public_key": Data(repeating: 1, count: 32),
    "private_key": Data(repeating: 2, count: 32), "alt_irk": Data(repeating: 3, count: 16)
]
// Protocol credentials and future/exporter-specific fields belong to Airlift's parser.
let records: [[String: Any]] = [record, remoteRecord, ["exporter-specific-key": "preserved"]]
for pairingRecord in records {
    for format in formats {
        let data = try PropertyListSerialization.data(fromPropertyList: pairingRecord, format: format, options: 0)
        let saved = try PairingFileStore.save(data, in: directory)
        precondition(saved == destination)
        try assertContents(saved, equalTo: data)
    }
}
let savedData = try Data(contentsOf: destination)
func rejects(_ data: Data) throws {
    do {
        _ = try PairingFileStore.save(data, in: directory)
        fatalError("Accepted an unreadable or empty plist")
    } catch is PairingFileStore.ImportError {
        try assertContents(destination, equalTo: savedData)
    }
}
try rejects(Data())
try rejects(Data("not a plist".utf8))
let unrelatedObjects: [Any] = [[String: String](), ["array"]]
for object in unrelatedObjects {
    try rejects(PropertyListSerialization.data(fromPropertyList: object, format: .xml, options: 0))
}
let blockedDirectory = directory.appendingPathComponent("not-a-directory")
try Data("block".utf8).write(to: blockedDirectory)
do {
    _ = try PairingFileStore.save(savedData, in: blockedDirectory)
    fatalError("Ignored a storage error")
} catch {
    try assertContents(destination, equalTo: savedData)
}
print("PASS: XML/binary Lockdown and Remote Pairing import, exact persistence, no credential schema gate, unreadable/empty plists preserve saved data, storage errors propagate")
''', encoding="utf-8")
    executable = temporary / "pairing-import-tests"
    subprocess.run([
        "swiftc", str(ROOT / "placard/Airlift/PairingFileStore.swift"), str(main),
        "-o", str(executable),
    ], check=True)
    subprocess.run([str(executable), str(temporary)], check=True)
