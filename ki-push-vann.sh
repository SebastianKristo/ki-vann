#!/bin/bash
# Bruk: bash ~/ki-push-vann.sh 1.0.0
set -e
V=$1
[ -z "$V" ] && { echo "Bruk: ki-push-vann.sh 1.0.0"; exit 1; }
REPO=~/Documents/HomeAssistant/ki-vann
U=${V//./_}

cd ~/Downloads
ZIP=""
for k in "ki-vann-$V.zip" "ki-vann-$U.zip"; do [ -f "$k" ] && ZIP="$k" && break; done
[ -z "$ZIP" ] && { echo "Fant ingen ki-vann-$V.zip eller ki-vann-$U.zip i ~/Downloads"; exit 1; }

rm -rf "ki-vann-$V" && unzip -oq "$ZIP" -d "ki-vann-$V"
KILDE="ki-vann-$V"
[ -d "$KILDE/ki-vann" ] && KILDE="$KILDE/ki-vann"
[ -d "$KILDE/custom_components" ] || { echo "Fant ingen custom_components i pakka"; exit 1; }

[ -d "$REPO/.git" ] || git clone -q https://github.com/SebastianKristo/ki-vann.git "$REPO"
cp -r "$KILDE/." "$REPO/"
cd "$REPO"
perl -pi -e "s/\"version\": \"[^\"]*\"/\"version\": \"$V\"/" custom_components/ki_vann/manifest.json
git add .
git commit -m "KI Vann v$V" || true
git push origin main
git tag -f "v$V" && git push -f origin "v$V"

NOTAT=""
[ -f RELEASE.md ] && NOTAT="--notes-file RELEASE.md"
if gh release view "v$V" >/dev/null 2>&1; then
  gh release edit "v$V" $NOTAT && echo "Ferdig. Release v$V oppdatert."
else
  gh release create "v$V" --title "v$V" $NOTAT && echo "Ferdig. Release v$V opprettet."
fi
