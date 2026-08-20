[app]
title = KasirQu
package.name = poskasir
package.domain = com.syauqi
source.dir = .
source.include_exts = py,png,jpg,jpeg,atlas,kv,json,ttf,otf,txt
source.exclude_dirs = .git,.github,.buildozer,bin,__pycache__
version = 4.10.2
requirements = python3,kivy==2.2.1
orientation = portrait
fullscreen = 0
icon.filename = %(source.dir)s/icon.png
presplash.filename = %(source.dir)s/presplash.png
android.api = 35
android.minapi = 23
android.archs = arm64-v8a
android.debug_artifact = apk
android.permissions = BLUETOOTH, BLUETOOTH_ADMIN, BLUETOOTH_CONNECT, BLUETOOTH_SCAN, ACCESS_FINE_LOCATION
android.accept_sdk_license = True
p4a.fork = kivy
p4a.branch = master
p4a.commit = 957a3e5
[buildozer]
log_level = 2
warn_on_root = 1
