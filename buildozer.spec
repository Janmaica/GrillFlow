[app]
title = GrillFlow
package.name = app
package.domain = com.grillflow
version = 0.1.0

source.dir = .
source.include_exts = py,png,json
# Buildozer's include patterns override exclude patterns. Allow only runtime files.
source.exclude_patterns = *
source.include_patterns = main.py,firebase_auth.py,session_vault.py,profile_photo.py,product_photos.py,
    product_store.py,order_store.py,order_draft.py,expense_store.py,consumption_store.py,
    receipt_data.py,receipt_export.py,report_chart_data.py,report_output.py,
    screens/,screens/__init__.py,screens/add_product_screen.py,screens/consumption_screen.py,
    screens/dashboard_screen.py,screens/expenses_screen.py,screens/login_screen.py,
    screens/new_order_screen.py,screens/order_history_screen.py,screens/payment_screen.py,
    screens/products_screen.py,screens/profile_screen.py,screens/receipt_screen.py,
    screens/report_chart.py,screens/reports_screen.py,screens/sales_screen.py,
    screens/splash_screen.py,screens/utang_screen.py,assets/images/,
    assets/images/grillflow_logo.png,assets/images/splash_background.png,google-services (3).json
source.exclude_dirs = tests,__pycache__,backups,local_data,user_data,accounts,product_photos,android_recipes,bin

icon.filename = assets/images/grillflow_logo.png
presplash.filename = assets/images/grillflow_logo.png
orientation = portrait
fullscreen = 0

# SDL2/Kivy supplies the bundled Roboto fonts. Python's SQLite and TLS use native recipes.
requirements = python3==3.11.9,hostpython3==3.11.9,kivy==2.3.2,Pillow==11.3.0,pyjnius,android,sqlite3,openssl
p4a.branch = v2026.05.09
p4a.bootstrap = sdl2
p4a.local_recipes = android_recipes
android.api = 34
android.minapi = 23
android.ndk = 28c
android.ndk_api = 23
android.archs = arm64-v8a, armeabi-v7a
android.permissions = INTERNET
android.accept_sdk_license = False
android.allow_backup = False
android.debug_artifact = apk

[buildozer]
log_level = 2
warn_on_root = 1
