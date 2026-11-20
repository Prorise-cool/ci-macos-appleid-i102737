import Foundation
import Vision
import AppKit
import CoreImage

let path = CommandLine.arguments[1]
guard let src = CIImage(contentsOf: URL(fileURLWithPath: path)) else { print("NOIMG"); exit(1) }
let ctx = CIContext()

func render(_ img: CIImage, _ s: CGFloat) -> CGImage? {
    let t = img.transformed(by: CGAffineTransform(scaleX: s, y: s))
    return ctx.createCGImage(t, from: t.extent)
}
func ocr(_ cg: CGImage) -> String {
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = false
    req.minimumTextHeight = 0.0
    let h = VNImageRequestHandler(cgImage: cg, options: [:])
    do { try h.perform([req]) } catch { return "" }
    return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: "")
}
func gray(_ img: CIImage) -> CIImage {
    let f = CIFilter(name: "CIColorControls", parameters: [kCIInputImageKey: img, kCIInputSaturationKey: 0.0, kCIInputContrastKey: 3.0, kCIInputBrightnessKey: 0.02])
    return (f?.outputImage) ?? img
}

var results: [String] = []
for inv in [false, true] {
    var base = gray(src)
    if inv {
        if let f = CIFilter(name: "CIColorInvert", parameters: [kCIInputImageKey: base]) { base = f.outputImage ?? base }
    }
    guard let cg = render(base, 4.0) else { continue }
    let w = cg.width, h = cg.height
    var buf = [UInt8](repeating: 255, count: w * h)
    guard let cs = CGColorSpace(name: CGColorSpace.linearGray),
          let g = CGContext(data: &buf, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w, space: cs, bitmapInfo: CGImageAlphaInfo.none.rawValue) else { continue }
    g.draw(cg, in: CGRect(x: 0, y: 0, width: w, height: h))
    var col = [Int](repeating: 0, count: w)
    for x in 0..<w {
        var c = 0
        for y in 0..<h {
            let px = Int(buf[y * w + x])
            let isInk = inv ? (px > 145) : (px < 110)
            if isInk { c += 1 }
        }
        col[x] = c
    }
    var segs: [(Int, Int)] = []
    var st = -1
    for x in 0..<w {
        let dark = col[x] >= 2
        if dark && st < 0 { st = x }
        if !dark && st >= 0 { if x - st >= 4 { segs.append((st, x - 1)) }; st = -1 }
    }
    if st >= 0 && w - st >= 4 { segs.append((st, w - 1)) }
    print("SLICES:" + segs.map { "\($0.0)-\($0.1)" }.joined(separator: ","))
    var out = ""
    for (a, b) in segs {
        let pad = 3
        let x0 = max(0, a - pad), x1 = min(w, b + pad)
        guard let sub = cg.cropping(to: CGRect(x: x0, y: 0, width: x1 - x0, height: h)) else { continue }
        var ch = ""
        for s in [2.0, 4.0, 6.0] as [CGFloat] {
            guard let up = render(CIImage(cgImage: sub), s) else { continue }
            let t = ocr(up).filter { ($0.isLetter && $0.isASCII) || $0.isNumber }
            if !t.isEmpty { ch = String(t.prefix(1)); break }
        }
        out += ch
    }
    if !out.isEmpty { print("SL:" + out); results.append(out) }
}
print("CANDS:" + results.joined(separator: ","))
