# 🔥 GrillFlow

**An Offline-First Barbecue Business Management Application**

GrillFlow is a Python-based business management application designed to help small barbecue business owners manage daily operations, track sales, monitor customer credit (_utang_), record expenses, and review business performance.

The application aims to provide a simple, user-friendly interface with understandable financial information, making business management more accessible to owners without extensive accounting knowledge.

## Project Status

**In Development**

GrillFlow uses Firebase email/password authentication for owner access and keeps business records in local SQLite databases.

## Technologies

- **Python 3.11** — Primary programming language
- **Kivy 2.3.2** — Cross-platform UI framework
- **SQLite** — Offline business database
- **Git & GitHub** — Version control
- **VS Code** — Development environment

**Target Platform:** Android

## Planned Features

### Dashboard

- Daily, weekly, and monthly business summaries
- Total sales, cash collected, outstanding credit, and expenses
- Estimated earnings and possible loss indicators
- Tappable financial cards with simple Cebuano explanations displayed in bottom sheets

### Sales and Order Management

- Create orders with multiple products and quantities
- Automatically generated customer names (Unknown1, Unknown2, etc.)
- Track order preparation: Pending, Cooking, Ready, and Received
- Track payments: Unpaid, Partially Paid, and Paid
- Automatically calculate cash change (_sukli_)
- Review active orders and completed transactions

### Products

- Add, edit, and archive products
- Set product names and selling prices
- Track product quantities and availability

### Customer Credit (Utang)

- Record credit transactions under named customers
- View individual orders, items, quantities, dates, and times
- Track outstanding balances and payment status
- Record partial and full payments
- Maintain customer payment history

### Receipts

- Generate itemized receipts for customer orders
- Display product names, quantities, unit prices, and totals
- Show cash received, change, and remaining balance
- Preview, print, or share receipts

### Expenses

- Record business purchases and operating expenses
- Categorize expenses such as meat, marinade, charcoal, and transportation
- Review expenses by date

### Family Consumption

- Record barbecue products consumed by family members
- Deduct consumed quantities from available inventory
- Keep family consumption separate from customer sales
- Display quantities and retail values without treating them as actual sales or exact losses

### Financial Reports

- Daily, weekly, and monthly summaries
- Sales and cash collection reports
- Expense and outstanding credit reports
- Estimated earnings and possible loss indicators
- Clear distinctions between sales, cash flow, and accounting profit

## Application Navigation

The five primary navigation destinations are:

**Home | Sales | Products | Utang | Reports**

Additional features, including Expenses, Family Consumption, Inventory, and Settings, will be accessible through secondary navigation.

## Development Roadmap

- [x] Create GitHub repository
- [x] Configure Python virtual environment
- [x] Install and verify Kivy
- [x] Create and test initial application window
- [ ] Implement application navigation and orange-themed screens
- [ ] Implement SQLite database
- [ ] Develop product and order management
- [ ] Implement payments, credit tracking, and receipts
- [ ] Implement expenses and family consumption
- [ ] Develop financial reports
- [ ] Test and package Android APK

## Running the Current Prototype

Clone the repository:

```bash
git clone https://github.com/Janmaica/GrillFlow.git
cd GrillFlow
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Windows:

```cmd
.venv\Scripts\activate
```

Install Kivy:

```bash
python -m pip install -r requirements.txt
```

In the GrillFlow Firebase project, enable **Authentication → Sign-in method → Email/Password**. Place the Firebase Android configuration in the project root as `google-services (3).json`. GrillFlow reads the project ID and API key from that file. Check the Email Verification and Password Reset templates in **Authentication → Templates**.

The offline-access setting is optional.

```powershell
$env:GRILLFLOW_OFFLINE_HOURS = "72"
python main.py
```

**Get Started** opens Login or resumes a valid owner session. Sign Up creates
the Firebase account and sends an email verification link. **Forgot Password?**
requests a Firebase reset link. **Log Out** in **My Profile** removes the
saved sign-in credential and preserves the account's business data.

An initial sign-in requires internet access and a verified email. Subsequent
launches refresh the token and verify the account with Firebase. During a network
outage, GrillFlow can reopen a previously verified session for up to 72 hours
from the last successful online check. Configure 0–168 hours with
`GRILLFLOW_OFFLINE_HOURS`. Zero disables offline access. Offline access depends
on the device clock, and Firebase revocation cannot be checked without a connection.
Windows uses current-user DPAPI. Android builds require API 23 or later, PyJNIus,
the INTERNET permission, and the Firebase JSON file included in the application package.
Android uses an AES-GCM key held by Android Keystore.

**My Profile** in the Dashboard menu shows your Firebase name, email, and
verification status. You can update your name online and request a password-reset
link for your account. During offline access, the profile shows the last
securely cached account information. Profile photos are resized on import,
stored in each account's local folder, and stay on the device. The Windows
file picker supports JPG, JPEG, and PNG. Android gallery selection is pending.

### Local account data

GrillFlow derives each account folder from the Firebase project ID and UID. The
SQLite database, product photos, exports, and reset backups stay in that account's
folder. Local SQLite data does not synchronize between devices. The old shared
`grillflow.sqlite3` stays in the original app-data folder.

For a manual legacy transfer, first sign in to the intended owner account so its
folder exists, and confirm its exact UID in Firebase Authentication. With
GrillFlow closed, make a verified SQLite backup of the legacy database and copy
its `product_photos` folder to the backup location. Confirm the target directory
by calling `firebase_auth.account_directory` with the app-data folder, Firebase
project ID, and confirmed UID. After the owner explicitly approves the transfer,
proceed only with a fresh account with no business records. Back up the target
folder, then place a copy of the verified legacy backup at
`grillflow.sqlite3` in that target and copy the matching product photos. Keep the
legacy database and both backups intact. Open GrillFlow and check the records
under that account. This procedure is for the device operator.

## Building GrillFlow APK Using GitHub Actions

The build runs on GitHub-hosted Ubuntu. Your Windows development machine only
needs a browser to download the APK. The workflow builds GrillFlow as
`com.grillflow.app` for ARM64 phones running Android 6.0 or later, using
Android API 34, minimum API 23, NDK r28c, and python-for-android
`v2026.05.09`. The [Buildozer spec](buildozer.spec) includes the runtime
source, the logo and splash artwork, and the Firebase client JSON. It
excludes local databases, photos, sessions, backups, and generated files.

1. In the GitHub repository, open **Settings ? Secrets and variables ?
   Actions ? New repository secret**. Name it `FIREBASE_CONFIG_JSON` and
   paste the contents of the local `google-services (3).json` file. The
   workflow expects Firebase project `grillflow` and Android app
   `com.grillflow.app`. Keep the JSON in the secret and your ignored
   local copy.
2. Open **Actions ? Build GrillFlow Android APK ? Run workflow**, select
   `main`, and start the run. Open the run to watch its installation,
   Buildozer, and APK validation steps.
3. After the run succeeds, download **GrillFlow-Android-APK** under
   **Artifacts** and extract the ZIP. The run summary lists the APK size,
   SHA-256 checksum, and debug signing SHA-1. Artifacts are retained for
   14 days.
4. Transfer the extracted APK to your phone, open it from the phone's
   file manager, then allow that app to install unknown apps if prompted.
   Open GrillFlow after installation.

If the Firebase validation step fails, check the secret name and confirm that
the JSON is the Android client file for the registered GrillFlow app. If
Buildozer fails, expand **Build signed debug APK** and review the first
toolchain error and the disk and SDK diagnostics. Builds run on new hosted
machines and can have different debug signing keys. If Android reports an
update signing mismatch, keep the installed app and its data while you
resolve the signing key. Uninstalling the installed app removes its local data.

The Android app continues to use the [Firebase Authentication REST APIs](https://firebase.google.com/docs/reference/rest/auth).
The bundled JSON supplies the API key and project ID for the matching Android
client. The APK requests INTERNET permission and sends its installed package
and signing certificate fingerprint on Firebase requests. If the API key has
Android application restrictions, allow this package and the **actual debug
APK's SHA-1** in Google Cloud. The Google Services Gradle plugin and native
Firebase SDK are unused. [Google Cloud API key restrictions](https://docs.cloud.google.com/docs/authentication/api-keys#android-apps)

On Android, SQLite, photos, and exports are written to the account-specific
folder under the app's private files directory. Refresh credentials remain
protected by Android Keystore, and the manifest disables app auto backup.
The Android photo picker and native receipt printing and sharing are pending.
Reports can save CSV files in private app storage. Opening or sharing those
files with another Android app and native report printing are pending.

## Financial history

Deleting a fully paid order removes it from Order History and Recent Orders.
SQLite retains the original sale, item snapshots, payments, and credit-transfer
history for reporting. Clear History archives visible orders in the selected
period in one transaction and is blocked if any selected order has an
outstanding balance. Neither action restores stock.

Products with sales are made inactive when removed. Their item snapshots still
contribute to product rankings, and their names can be used for new products.
Deleting an expense hides it from the expense list while retaining its original
contribution to Dashboard and Reports. Editing an expense updates the recognized
record and logs the previous amount, category, and date when those fields change.

The expense migration creates a verified local backup before updating an
existing expense schema. Reset All Data clears both operational and preserved
financial records, including expense corrections, after its existing explicit
confirmation and backup.

## Project Goals

GrillFlow aims to simplify everyday barbecue business management by providing offline access to sales records, order preparation, customer credit, receipts, expenses, family consumption, and understandable financial summaries.

---

**GrillFlow — Manage Every Sale. Track Every Peso.**
