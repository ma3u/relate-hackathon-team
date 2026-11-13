import Foundation
import Relate

/// The knowledge layer, as `health_graph/knowledge.py` seeds it: health risks,
/// risk scores, the measures guidelines name for each risk, and official and
/// optimal reference ranges, and how the risks raise each other with the studies
/// that show it, each with its source. The facts and the Cypher are
/// generated from the Python (KnowledgeData.swift, Cypher.swift).
extension HealthStore {
  /// Writes the knowledge layer; a no-op when it is already current.
  @discardableResult
  public func seedKnowledge(force: Bool = false) throws -> [String: Int] {
    let current = try connection.query("MATCH (k:Knowledge {id: 'health-graph'}) RETURN k.fingerprint AS f")
      .records.first?["f"]?.plain
    if current == KnowledgeData.fingerprint && !force { return [:] }
    let data = try JSON.object(Data(KnowledgeData.json.utf8))
    var counts: [String: Int] = [:]
    let steps: [(String, String)] = [
      (Cypher.seedRisks, "risks"), (Cypher.seedScores, "scores"),
      (Cypher.seedMarkers, "markers"), (Cypher.seedRanges, "ranges"),
      (Cypher.seedStudies, "studies"), (Cypher.seedStudyMarkers, "examines"),
      (Cypher.seedStudyScores, "informs"), (Cypher.seedRiskLinks, "links"),
    ]
    for (cypher, key) in steps {
      let rows = try connection.query(cypher, [key: JSON.cypher(data[key])]).records
      for (k, v) in rows.first ?? [:] { counts[k] = Int(v.intValue ?? 0) }
    }
    _ = try connection.query(
      Cypher.seedVersion,
      ["fingerprint": .string(KnowledgeData.fingerprint), "rangesSource": .string(KnowledgeData.rangesSource)])
    return counts
  }
}
