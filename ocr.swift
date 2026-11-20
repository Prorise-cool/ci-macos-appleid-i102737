import Foundation
import Vision
import AppKit
let p = CommandLine.arguments[1]
guard let img = NSImage(contentsOfFile: p) else { print("NOIMG"); exit(1) }
var rect = CGRect(origin: .zero, size: img.size)
guard let cg = img.cgImage(forProposedRect: &rect, context: nil, hints: nil) else { print("NOCG"); exit(1) }
let req = VNRecognizeTextRequest()
req.recognitionLevel = .accurate
req.usesLanguageCorrection = false
req.automaticallyDetectsLanguage = false
let h = VNImageRequestHandler(cgImage: cg, options: [:])
do { try h.perform([req]) } catch { print("ERR"); exit(1) }
let lines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
print(lines.joined(separator: " "))
