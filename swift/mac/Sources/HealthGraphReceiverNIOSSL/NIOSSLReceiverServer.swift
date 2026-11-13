import Foundation
import HealthGraphReceiver
import NIOCore
import NIOPosix
import NIOSSL

/// The command-line receiver: the same HTTP pipeline as `ReceiverServer`, with
/// TLS from BoringSSL (swift-nio-ssl) and the identity read straight from the
/// PEM files, so no keychain is involved. Not used by the Mac app.
public final class NIOSSLReceiverServer {
  let core: ReceiverCore
  let tls: NIOSSLContext
  let group = MultiThreadedEventLoopGroup(numberOfThreads: 2)
  var channel: Channel?

  public init(core: ReceiverCore, identity: Identity) throws {
    self.core = core
    var config = TLSConfiguration.makeServerConfiguration(
      certificateChain: try NIOSSLCertificate.fromPEMFile(identity.certificate.path).map { .certificate($0) },
      privateKey: .privateKey(try NIOSSLPrivateKey(file: identity.key.path, format: .pem)))
    config.minimumTLSVersion = .tlsv12
    tls = try NIOSSLContext(configuration: config)
  }

  /// Binds and returns the port (pass 0 for any free port).
  @discardableResult
  public func start(host: String = "0.0.0.0", port: Int) throws -> Int {
    let core = self.core
    let tls = self.tls
    let bootstrap = ServerBootstrap(group: group)
      .serverChannelOption(ChannelOptions.backlog, value: 64)
      .serverChannelOption(ChannelOptions.socketOption(.so_reuseaddr), value: 1)
      .childChannelInitializer { channel in
        channel.eventLoop.makeCompletedFuture {
          try channel.pipeline.syncOperations.addHandler(NIOSSLServerHandler(context: tls))
          try ReceiverServer.configureHTTP(channel, core: core)
        }
      }
    let channel = try bootstrap.bind(host: host, port: port).wait()
    self.channel = channel
    return channel.localAddress?.port ?? port
  }

  public func wait() throws { try channel?.closeFuture.wait() }

  public func stop() {
    try? channel?.close().wait()
    try? group.syncShutdownGracefully()
  }
}
