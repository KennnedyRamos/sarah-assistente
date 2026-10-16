# Sarah para Android

App em Flutter que abre a interface da Sarah (rodando no PC) em tela cheia, sem navegador, pela tailnet do Tailscale.

```
flutter build apk --release --split-per-abi --dart-define=SARAH_URL=https://<seu-pc>.<sua-tailnet>.ts.net/
```

O APK de 64 bits sai em `build/app/outputs/flutter-apk/app-arm64-v8a-release.apk`. Instalação e uso: README da raiz do projeto.
