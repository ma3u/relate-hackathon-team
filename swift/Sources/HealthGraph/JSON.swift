import Foundation
import Relate

/// A FHIR resource as Foundation decodes it (`JSONSerialization`).
public typealias JSONObject = [String: Any]

/// One graph row: the properties of a node, ready to bind as a parameter.
public typealias Row = [String: CypherValue]

extension Dictionary where Key == String, Value == Any {
  func object(_ key: String) -> JSONObject? { self[key] as? JSONObject }
  func objects(_ key: String) -> [JSONObject] {
    (self[key] as? [Any])?.compactMap { $0 as? JSONObject } ?? []
  }
  func string(_ key: String) -> String? { self[key] as? String }
  /// Python's `x.get(key) or None` for strings: an empty string counts as missing.
  func text(_ key: String) -> String? { nonEmpty(self[key] as? String) }
}

func nonEmpty(_ s: String?) -> String? { s.flatMap { $0.isEmpty ? nil : $0 } }

public enum JSON {
  /// Parse a JSON object (a FHIR resource or Bundle).
  public static func object(_ data: Data) throws -> JSONObject {
    guard let obj = try JSONSerialization.jsonObject(with: data) as? JSONObject else {
      throw HealthGraphError.invalid("not a JSON object")
    }
    return obj
  }

  /// A JSON number as a Cypher number: integers stay integers (so
  /// `toString(10)` is "10" as in the Python version), booleans are not numbers.
  static func number(_ any: Any?) -> CypherValue? {
    guard let n = any as? NSNumber, CFGetTypeID(n) != CFBooleanGetTypeID() else { return nil }
    return CFNumberIsFloatType(n) ? .float(n.doubleValue) : .int(n.int64Value)
  }

  /// Any decoded JSON value as a Cypher value.
  public static func cypher(_ any: Any?) -> CypherValue {
    switch any {
    case nil, is NSNull: return .null
    case let n as NSNumber:
      if CFGetTypeID(n) == CFBooleanGetTypeID() { return .bool(n.boolValue) }
      return number(n) ?? .null
    case let s as String: return .string(s)
    case let a as [Any]: return .list(a.map(cypher))
    case let o as JSONObject: return .map(o.mapValues(cypher))
    default: return .null
    }
  }

  /// `json.dumps(value, sort_keys=True)` byte for byte, for the ids that must
  /// match the Python receiver's (default separators, ensure_ascii).
  static func pythonDumps(_ any: Any?) -> String {
    switch any {
    case nil, is NSNull: return "null"
    case let n as NSNumber:
      if CFGetTypeID(n) == CFBooleanGetTypeID() { return n.boolValue ? "true" : "false" }
      return CFNumberIsFloatType(n) ? "\(n.doubleValue)" : "\(n.int64Value)"
    case let s as String: return quote(s)
    case let a as [Any]: return "[" + a.map(pythonDumps).joined(separator: ", ") + "]"
    case let o as JSONObject:
      let keys = o.keys.sorted { $0.unicodeScalars.lexicographicallyPrecedes($1.unicodeScalars) }
      return "{" + keys.map { quote($0) + ": " + pythonDumps(o[$0]) }.joined(separator: ", ") + "}"
    default: return "null"
    }
  }

  private static func quote(_ s: String) -> String {
    var out = "\""
    for unit in s.utf16 {
      switch unit {
      case 0x22: out += "\\\""
      case 0x5C: out += "\\\\"
      case 0x0A: out += "\\n"
      case 0x0D: out += "\\r"
      case 0x09: out += "\\t"
      case 0x08: out += "\\b"
      case 0x0C: out += "\\f"
      case 0x20..<0x7F: out.unicodeScalars.append(Unicode.Scalar(unit)!)
      default: out += String(format: "\\u%04x", unit)
      }
    }
    return out + "\""
  }
}

public enum HealthGraphError: Error, CustomStringConvertible, Equatable {
  case invalid(String)
  public var description: String {
    switch self { case .invalid(let message): message }
  }
}
