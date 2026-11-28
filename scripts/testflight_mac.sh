#!/usr/bin/env bash
# Archive Klarbefund for Mac and upload it to TestFlight, signed in with an App Store
# Connect API key instead of the Apple ID in Xcode's Accounts. Runs without Xcode's
# Organizer and without a login prompt, from a terminal, CI or an agent.
#
#   scripts/testflight_mac.sh                 archive, export, validate, upload
#   scripts/testflight_mac.sh --validate-only archive, export and validate; no upload
#   scripts/testflight_mac.sh --archive PATH  reuse an existing .xcarchive
#   scripts/testflight_mac.sh --check         only check the key and issuer (offline)
#
# The key stays outside the repository:
#   ~/.appstoreconnect/private_keys/AuthKey_<KEY_ID>.p8   the key App Store Connect issued
#   ~/.appstoreconnect/config                             ASC_ISSUER_ID=…  (and ASC_KEY_ID=…
#                                                         if there is more than one key)
# Environment variables ASC_ISSUER_ID, ASC_KEY_ID and ASC_KEY_PATH override the file.
# The issuer ID is shown in App Store Connect, Users and Access, Integrations,
# App Store Connect API, above the list of keys.
#
# The build number is CURRENT_PROJECT_VERSION in apps/mac/project.yml; App Store Connect
# refuses a number it has seen before, so raise it first.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MAC="$ROOT/apps/mac"
ASC_DIR="$HOME/.appstoreconnect"
TEAM_ID="38R8Z4P7S8"

mode=upload
archive=""
while [ $# -gt 0 ]; do
  case "$1" in
    --validate-only) mode=validate ;;
    --check) mode=check ;;
    --archive) archive="${2:?--archive needs a path}"; shift ;;
    -h|--help) sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
  shift
done

# ── credentials: values are read, never printed ──
config_value() {  # KEY from ~/.appstoreconnect/config, without running the file
  [ -f "$ASC_DIR/config" ] || return 0
  sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*\"\{0,1\}\([^\"]*\)\"\{0,1\}[[:space:]]*$/\1/p" "$ASC_DIR/config" | tail -1
}
ASC_ISSUER_ID="${ASC_ISSUER_ID:-$(config_value ASC_ISSUER_ID)}"
ASC_KEY_ID="${ASC_KEY_ID:-$(config_value ASC_KEY_ID)}"
if [ -z "${ASC_KEY_PATH:-}" ]; then
  if [ -n "$ASC_KEY_ID" ]; then
    ASC_KEY_PATH="$ASC_DIR/private_keys/AuthKey_$ASC_KEY_ID.p8"
  else
    keys=("$ASC_DIR"/private_keys/AuthKey_*.p8)
    if [ ! -e "${keys[0]}" ]; then
      echo "No App Store Connect key in $ASC_DIR/private_keys/." >&2
      echo "Create one in App Store Connect (Users and Access, Integrations, App Store Connect API, role App Manager) and save the .p8 there." >&2
      exit 1
    fi
    if [ "${#keys[@]}" -gt 1 ]; then
      echo "More than one key in $ASC_DIR/private_keys/: set ASC_KEY_ID in $ASC_DIR/config." >&2
      exit 1
    fi
    ASC_KEY_PATH="${keys[0]}"
  fi
fi
[ -f "$ASC_KEY_PATH" ] || { echo "Key file not found: $ASC_KEY_PATH" >&2; exit 1; }
if [ -z "$ASC_KEY_ID" ]; then
  ASC_KEY_ID="$(basename "$ASC_KEY_PATH" .p8)"
  ASC_KEY_ID="${ASC_KEY_ID#AuthKey_}"
fi
if [ -z "$ASC_ISSUER_ID" ]; then
  echo "No issuer ID. Add a line ASC_ISSUER_ID=<issuer id> to $ASC_DIR/config" >&2
  echo "(App Store Connect, Users and Access, Integrations, App Store Connect API, above the keys)." >&2
  exit 1
fi
if ! [[ "$ASC_ISSUER_ID" =~ ^[0-9a-fA-F-]{36}$ ]]; then
  echo "ASC_ISSUER_ID does not look like an issuer ID (a UUID)." >&2
  exit 1
fi

# The key file must be readable by this user only.
perm="$(stat -f '%Lp' "$ASC_KEY_PATH")"
if [ "$perm" != "600" ] && [ "$perm" != "400" ]; then
  echo "The key file is readable by others ($perm); run: chmod 600 \"$ASC_KEY_PATH\"" >&2
  exit 1
fi

# Offline check: altool signs a token with the key; the token is discarded.
if ! xcrun altool --generate-jwt --apiKey "$ASC_KEY_ID" --apiIssuer "$ASC_ISSUER_ID" \
     --p8-file-path "$ASC_KEY_PATH" >/dev/null 2>&1; then
  echo "The key could not sign a token: check that the .p8 file is the one App Store Connect issued." >&2
  exit 1
fi
echo "App Store Connect key: ok (key file found, issuer set, token signed)"
[ "$mode" = check ] && exit 0

AUTH=(-authenticationKeyPath "$ASC_KEY_PATH" -authenticationKeyID "$ASC_KEY_ID"
      -authenticationKeyIssuerID "$ASC_ISSUER_ID")
ALTOOL_AUTH=(--apiKey "$ASC_KEY_ID" --apiIssuer "$ASC_ISSUER_ID" --p8-file-path "$ASC_KEY_PATH")

build="$(sed -n 's/^[[:space:]]*CURRENT_PROJECT_VERSION:[[:space:]]*"\{0,1\}\([0-9][0-9]*\)"\{0,1\}.*/\1/p' "$MAC/project.yml" | head -1)"
[ -n "$build" ] || { echo "No CURRENT_PROJECT_VERSION in $MAC/project.yml" >&2; exit 1; }

# Archives live in a .noindex folder so Spotlight never launches an archived build (docs/MAC.md).
ARCHIVES="$MAC/build/archives.noindex"
mkdir -p "$ARCHIVES"
if [ -z "$archive" ]; then
  archive="$ARCHIVES/Klarbefund-$build.xcarchive"
  [ -e "$archive" ] && { echo "$archive exists: raise CURRENT_PROJECT_VERSION or pass --archive." >&2; exit 1; }
  echo "Archiving build $build …"
  (cd "$MAC" && xcodegen generate -q)
  xcodebuild -project "$MAC/Klarbefund.xcodeproj" -scheme Klarbefund -configuration Release \
    -destination 'generic/platform=macOS' -derivedDataPath "$MAC/build/dd-release" \
    -archivePath "$archive" -allowProvisioningUpdates "${AUTH[@]}" archive \
    > "$MAC/build/archive-$build.log" 2>&1 \
    || { grep -E 'error:' "$MAC/build/archive-$build.log" | head -20 >&2; echo "Archive failed; log: $MAC/build/archive-$build.log" >&2; exit 1; }
fi
[ -d "$archive" ] || { echo "No archive at $archive" >&2; exit 1; }

# Export the signed installer package locally, then validate and upload it with altool:
# the same package is checked and sent, and a failed validation sends nothing.
out="$MAC/build/export-$build"
rm -rf "$out"
tmp="$(mktemp -d -t klarbefund-export)"
trap 'rm -rf "$tmp"' EXIT
opts="$tmp/ExportOptions.plist"
cat > "$opts" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>method</key><string>app-store-connect</string>
  <key>destination</key><string>export</string>
  <key>teamID</key><string>$TEAM_ID</string>
  <key>signingStyle</key><string>automatic</string>
</dict></plist>
PLIST
echo "Exporting …"
xcodebuild -exportArchive -archivePath "$archive" -exportOptionsPlist "$opts" -exportPath "$out" \
  -allowProvisioningUpdates "${AUTH[@]}" > "$MAC/build/export-$build.log" 2>&1 \
  || { grep -E 'error:' "$MAC/build/export-$build.log" | head -20 >&2; echo "Export failed; log: $MAC/build/export-$build.log" >&2; exit 1; }
pkg="$(find "$out" -maxdepth 1 -name '*.pkg' | head -1)"
[ -n "$pkg" ] || { echo "The export made no .pkg; see $out" >&2; exit 1; }

echo "Validating $(basename "$pkg") …"
xcrun altool --validate-app -f "$pkg" -t macos "${ALTOOL_AUTH[@]}"
[ "$mode" = validate ] && { echo "Validated build $build; not uploaded (--validate-only)."; exit 0; }

echo "Uploading build $build …"
xcrun altool --upload-app -f "$pkg" -t macos "${ALTOOL_AUTH[@]}"
echo "Uploaded build $build. App Store Connect processes it before TestFlight offers it (usually 5 to 30 minutes)."
