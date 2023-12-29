# Create a folder (named dmg) to prepare our DMG in (if it doesn't already exist).
mkdir -p dist/dmg
# Empty the dmg folder.
# rm -r dist/dmg/*
# Copy the app bundle to the dmg folder.
cp -r "dist/starknet_degensoft.app" dist/dmg
# If the DMG already exists, delete it.
test -f "dist/starknet_degensoft.dmg" && rm "dist/starknet_degensoft.dmg"
create-dmg \
  --volname "starknetDegensoft" \
  --volicon "degensoft.icns" \
  --window-pos 200 120 \
  --window-size 600 300 \
  --icon-size 100 \
  --icon "starknet_degensoft.app" 175 120 \
  --hide-extension "starknet_degensoft.app" \
  --app-drop-link 425 120 \
  "dist/starknet_degensoft.dmg" \
  "dist/dmg/"
rm -r dist/dmg/