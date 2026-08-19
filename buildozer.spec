[app]

# ==========================================
# IDENTITAS APLIKASI
# ==========================================
title = POS Kasir
package.name = poskasir
package.domain = com.syauqi

# ==========================================
# SOURCE
# ==========================================
source.dir = .
source.include_exts = py,png,jpg,jpeg,atlas,kv,json,ttf,otf,txt
source.exclude_dirs = .git,.github,.buildozer,bin,__pycache__

# ==========================================
# VERSION
# ==========================================
version = 4.9.8

# ==========================================
# PYTHON / KIVY
# ==========================================
requirements = python3,kivy==2.2.1

# ==========================================
# DISPLAY
# ==========================================
orientation = portrait
fullscreen = 0

# ==========================================
# ANDROID
# ==========================================
android.api = 35
android.minapi = 23
android.archs = arm64-v8a

android.debug_artifact = apk

android.permissions = BLUETOOTH, BLUETOOTH_ADMIN, BLUETOOTH_CONNECT, BLUETOOTH_SCAN, ACCESS_FINE_LOCATION

android.accept_sdk_license = True

# ==========================================
# PYTHON-FOR-ANDROID
# ==========================================
p4a.fork = kivy
p4a.branch = master
p4a.commit = 957a3e5

# ==========================================
# BUILDOZER
# ==========================================
[buildozer]

log_level = 2
warn_on_root = 1
