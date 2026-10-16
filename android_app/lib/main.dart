// App da Sarah para Android: abre a interface da Sarah em tela cheia, sem navegador.
//
// A Sarah continua rodando no PC; o app conversa com ela pela sua tailnet (o Tailscale do celular precisa estar
// conectado). Microfone, câmera e localização são pedidos ao Android na primeira vez em que a página usa cada um.
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';

/// Endereço da Sarah na tailnet (o mesmo que abre no navegador do celular), informado na compilação para não ficar no código:
/// flutter build apk --release --split-per-abi --dart-define=SARAH_URL=https://seu-pc.sua-tailnet.ts.net/
const sarahUrl = String.fromEnvironment('SARAH_URL');
const background = Color(0xFFF3F8FE);
const navy = Color(0xFF0B2A4A);

void main() {
  if (!sarahUrl.startsWith('https://')) {
    throw StateError('Compile com --dart-define=SARAH_URL=https://<seu-pc>.<sua-tailnet>.ts.net/');
  }
  runApp(const SarahApp());
}

class SarahApp extends StatelessWidget {
  const SarahApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'Sarah',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(colorSchemeSeed: const Color(0xFF1689E0), scaffoldBackgroundColor: background),
        home: const SarahPage(),
      );
}

class SarahPage extends StatefulWidget {
  const SarahPage({super.key});

  @override
  State<SarahPage> createState() => _SarahPageState();
}

class _SarahPageState extends State<SarahPage> {
  late final WebViewController _web;
  bool _offline = false;

  @override
  void initState() {
    super.initState();
    _web = WebViewController(onPermissionRequest: _onPermission)
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(background)
      ..setNavigationDelegate(NavigationDelegate(
        onWebResourceError: (error) {
          if (error.isForMainFrame ?? true) setState(() => _offline = true);
        },
        onNavigationRequest: (request) {
          if (request.url.startsWith(sarahUrl)) return NavigationDecision.navigate;
          // links de fora (e-mail no Gmail, mapa, fontes da busca) abrem no app certo do celular
          launchUrl(Uri.parse(request.url), mode: LaunchMode.externalApplication);
          return NavigationDecision.prevent;
        },
      ))
      ..loadRequest(Uri.parse(sarahUrl));
    final android = _web.platform as AndroidWebViewController;
    android.setMediaPlaybackRequiresUserGesture(false); // a resposta falada toca sem precisar de um toque antes
    android.setOnShowFileSelector(_pickFiles); // botão 📎
    android.setGeolocationPermissionsPromptCallbacks(onShowPrompt: (request) async {
      final allowed = await Permission.location.request().isGranted;
      return GeolocationPermissionsResponse(allow: allowed, retain: true);
    });
  }

  /// A página pediu microfone e/ou câmera: o Android pergunta ao usuário (só na primeira vez).
  Future<void> _onPermission(WebViewPermissionRequest request) async {
    final wanted = <Permission>[
      if (request.types.contains(WebViewPermissionResourceType.microphone)) Permission.microphone,
      if (request.types.contains(WebViewPermissionResourceType.camera)) Permission.camera,
    ];
    final results = await wanted.request();
    if (results.values.every((s) => s.isGranted)) {
      await request.grant();
    } else {
      await request.deny();
    }
  }

  Future<List<String>> _pickFiles(FileSelectorParams params) async {
    final files = await FilePicker.pickFiles();
    return files.map((f) => f.uri.toString()).toList();
  }

  void _retry() {
    setState(() => _offline = false);
    _web.loadRequest(Uri.parse(sarahUrl));
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        body: SafeArea(child: _offline ? _OfflineMessage(onRetry: _retry) : WebViewWidget(controller: _web)),
      );
}

class _OfflineMessage extends StatelessWidget {
  const _OfflineMessage({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            ClipOval(child: Image.asset('assets/sarah.png', width: 120, height: 120)),
            const SizedBox(height: 20),
            const Text('Não consegui falar com a Sarah',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.w600, color: navy), textAlign: TextAlign.center),
            const SizedBox(height: 10),
            const Text('Confira se o Tailscale está conectado neste celular e se o PC está ligado com a Sarah rodando.',
                textAlign: TextAlign.center),
            const SizedBox(height: 20),
            FilledButton.icon(onPressed: onRetry, icon: const Icon(Icons.refresh), label: const Text('Tentar de novo')),
          ]),
        ),
      );
}
