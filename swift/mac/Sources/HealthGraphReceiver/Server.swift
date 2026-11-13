import Foundation
import Network
import NIOCore
import NIOHTTP1
import NIOTransportServices

/// HTTPS server for `ReceiverCore` on SwiftNIO over Apple's Network framework:
/// TLS is the operating system's, nothing is bundled. Non-blocking: a client
/// that stalls (no TLS hello, a slow upload) never holds up the others; idle
/// connections are closed after 60 s.
public final class ReceiverServer {
  let core: ReceiverCore
  let tls: TLSIdentity
  let group = NIOTSEventLoopGroup(loopCount: 2)
  var channel: Channel?

  public init(core: ReceiverCore, identity: Identity) throws {
    self.core = core
    tls = try TLSIdentity(identity)
  }

  /// Binds and returns the port (pass 0 for any free port).
  @discardableResult
  public func start(host: String = "0.0.0.0", port: Int) throws -> Int {
    let core = self.core
    let options = NWProtocolTLS.Options()
    let sec = options.securityProtocolOptions
    sec_protocol_options_set_local_identity(sec, tls.secIdentity)
    sec_protocol_options_set_min_tls_protocol_version(sec, .TLSv12)
    let bootstrap = NIOTSListenerBootstrap(group: group)
      .serverChannelOption(ChannelOptions.socketOption(.so_reuseaddr), value: 1)
      .tlsOptions(options)
      .childChannelInitializer { channel in
        channel.eventLoop.makeCompletedFuture { try ReceiverServer.configureHTTP(channel, core: core) }
      }
    let channel = try bootstrap.bind(host: host, port: port).wait()
    self.channel = channel
    return channel.localAddress?.port ?? port
  }

  public func wait() throws { try channel?.closeFuture.wait() }

  public func stop() {
    try? channel?.close().wait()
    try? group.syncShutdownGracefully()
    tls.remove()
  }

  /// Everything after TLS: idle timeout, HTTP/1.1, the receiver. Shared with the
  /// command-line server (`HealthGraphReceiverNIOSSL`).
  package static func configureHTTP(_ channel: Channel, core: ReceiverCore) throws {
    let ops = channel.pipeline.syncOperations
    try ops.addHandler(IdleStateHandler(readTimeout: .seconds(60)))
    try ops.addHandler(CloseOnIdle())
    try ops.configureHTTPServerPipeline(withErrorHandling: true)
    try ops.addHandler(HTTPHandler(core: core))
  }
}

final class CloseOnIdle: ChannelInboundHandler {
  typealias InboundIn = NIOAny
  func userInboundEventTriggered(context: ChannelHandlerContext, event: Any) {
    if event is IdleStateHandler.IdleStateEvent { context.close(promise: nil) }
    context.fireUserInboundEventTriggered(event)
  }
}

final class HTTPHandler: ChannelInboundHandler {
  typealias InboundIn = HTTPServerRequestPart
  typealias OutboundOut = HTTPServerResponsePart

  let core: ReceiverCore
  var head: HTTPRequestHead?
  var body = ByteBuffer()
  var tooLarge = false

  init(core: ReceiverCore) { self.core = core }

  func channelRead(context: ChannelHandlerContext, data: NIOAny) {
    switch unwrapInboundIn(data) {
    case .head(let h):
      head = h
      body.clear()
      tooLarge = (h.headers.first(name: "content-length").flatMap(Int.init) ?? 0) > ReceiverCore.maxBody
    case .body(var chunk):
      if tooLarge { return }
      if body.readableBytes + chunk.readableBytes > ReceiverCore.maxBody {
        tooLarge = true
        body.clear()
      } else {
        body.writeBuffer(&chunk)
      }
    case .end:
      guard let head else { return }
      var headers: [String: String] = [:]
      for (name, value) in head.headers { headers[name.lowercased()] = value }
      let ip = context.channel.remoteAddress?.ipAddress
      if tooLarge {
        return respond(context, head, ReceiverCore.Response(413, ["error": "a FHIR Bundle up to 10 MB is required"]))
      }
      let request = ReceiverCore.Request(
        method: head.method.rawValue, path: head.uri, headers: headers, remoteIP: ip,
        body: Data(body.readableBytesView))
      let loop = context.eventLoop
      let bound = NIOLoopBound((self, context), eventLoop: loop)
      core.handle(request) { response in
        loop.execute {
          let (handler, context) = bound.value
          handler.respond(context, head, response)
        }
      }
    }
  }

  func respond(_ context: ChannelHandlerContext, _ head: HTTPRequestHead, _ response: ReceiverCore.Response) {
    var headers = HTTPHeaders()
    headers.add(name: "Content-Type", value: "application/json")
    headers.add(name: "Content-Length", value: String(response.body.count))
    headers.add(name: "Server", value: "RelateHealthGraph/2 (Swift)")
    let keepAlive = head.isKeepAlive
    if !keepAlive { headers.add(name: "Connection", value: "close") }
    let status = HTTPResponseStatus(statusCode: response.status)
    context.write(wrapOutboundOut(.head(HTTPResponseHead(version: head.version, status: status, headers: headers))), promise: nil)
    context.write(wrapOutboundOut(.body(.byteBuffer(ByteBuffer(bytes: response.body)))), promise: nil)
    let done = context.writeAndFlush(wrapOutboundOut(.end(nil)))
    if !keepAlive { done.whenComplete { _ in context.close(promise: nil) } }
  }
}
