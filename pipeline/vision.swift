// Faces and text (Thai + English) for each image path on stdin -> one JSON line each.
// Boxes are normalised, origin top-left.
import Foundation
import Vision
import AppKit

func box(_ r: CGRect) -> [Double] { [Double(r.minX), Double(1 - r.maxY), Double(r.width), Double(r.height)] }

while let path = readLine() {
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        print("{\"path\":\"\(path)\",\"error\":\"unreadable\"}"); continue
    }
    let h = VNImageRequestHandler(cgImage: cg, options: [:])
    let faces = VNDetectFaceRectanglesRequest()
    let people = VNDetectHumanRectanglesRequest(); people.upperBodyOnly = false
    let text = VNRecognizeTextRequest()
    text.recognitionLevel = .accurate
    text.recognitionLanguages = ["th-TH", "en-US"]
    text.usesLanguageCorrection = true
    text.revision = VNRecognizeTextRequestRevision3
    text.minimumTextHeight = 0.008
    try? h.perform([faces, people, text])
    var out: [String: Any] = ["path": path]
    out["faces"] = (faces.results ?? []).map { ["box": box($0.boundingBox), "conf": Double($0.confidence)] }
    out["people"] = (people.results ?? []).map { ["box": box($0.boundingBox), "conf": Double($0.confidence)] }
    out["text"] = (text.results ?? []).compactMap { o -> [String: Any]? in
        guard let c = o.topCandidates(1).first else { return nil }
        return ["s": c.string, "conf": Double(c.confidence), "box": box(o.boundingBox)]
    }
    let data = try! JSONSerialization.data(withJSONObject: out)
    print(String(data: data, encoding: .utf8)!)
    fflush(stdout)
}
