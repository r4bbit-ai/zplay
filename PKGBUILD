# Maintainer: you <you@example.com>
pkgname=zplay
pkgver=1.0.0
pkgrel=1
pkgdesc="Retro-japanese CLI music deck: spinning disc art, frequency bars, 20 themes"
arch=('any')
url="https://example.com/zplay"
license=('MIT')
depends=('python' 'mpv')
optdepends=('ffmpeg: frequency-bar analysis'
            'python-pillow: images on the spinning disc'
            'python-numpy: real FFT spectrum')
source=()

package() {
  install -dm755 "$pkgdir/usr/lib/zplay"
  cp -r "$startdir/zplay" "$pkgdir/usr/lib/zplay/zplay"
  install -Dm755 "$startdir/bin/zplay" "$pkgdir/usr/bin/zplay"
  install -Dm644 "$startdir/README.md" "$pkgdir/usr/share/doc/zplay/README.md"
}
