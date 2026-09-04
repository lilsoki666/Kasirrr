[app]
title = UT Kasirrr
package.name = utkasir
package.domain = org.test

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,db

# PASTIKAN bagian requirements HANYA ini (jangan masukkan sqlite3 atau sqlite)
requirements = python3,kivy

# Permissions
android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE

# Android API Target
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.debug_artifact = apk
android.permissions = BLUETOOTH, BLUETOOTH_ADMIN, BLUETOOTH_CONNECT, BLUETOOTH_SCAN, INTERNAL_STORAGE, READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, READ_MEDIA_IMAGES
android.accept_sdk_license = True
p4a.fork = kivy
p4a.branch = master
p4a.commit = 957a3e5
[buildozer]
log_level = 2
warn_on_root = 1
