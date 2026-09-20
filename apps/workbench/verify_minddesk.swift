import Foundation
// Compiled alongside the actual read-only MindDeskCore source files.
@main struct VerifyMindDesk {
    static func main() throws {
        let bytes=FileHandle.standardInput.readDataToEndOfFile()
        let manifest=try JSONDecoder.minddesk.decode(ExportManifest.self,from:bytes)
        let issues=ManifestImportValidation.issues(in:manifest)
        guard issues.isEmpty else {
            FileHandle.standardError.write(Data(issues.joined(separator:"\n").utf8))
            exit(1)
        }
        FileHandle.standardOutput.write(try JSONEncoder.minddesk.encode(manifest))
    }
}
