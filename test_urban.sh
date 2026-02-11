#!/bin/bash
set -euo pipefail

SERVICE="haier"
BASE_DIR="/opt/haier"
CONFIG="/opt/config.ini"
TMP="$(mktemp)"

echo "📦 Wklejam pliki z paczki test 1.4.5.7"

systemctl stop "$SERVICE"

rm -rf "$BASE_DIR/static" "$BASE_DIR/templates" "$BASE_DIR/main.py"
cd "$BASE_DIR"

curl -sL https://github.com/ur6an/Haier/raw/refs/heads/main/fixV1.4.5.7.tar.gz | tar -xz

cp "$CONFIG" "${CONFIG}.backup"

echo "✅ Podmiana zakończona"
echo

# -------------------------------------------------
# FUNKCJE
# -------------------------------------------------

config_has() {
    grep -Eq "^[[:space:]]*$1[[:space:]]*=" "$CONFIG"
}

insert_after_section() {
    local section="$1"
    local content="$2"
    local tmp
    tmp="$(mktemp)"

    awk -v sec="[$section]" -v txt="$content" '
    $0 == sec {
        print
        print txt
        next
    }
    { print }
    ' "$CONFIG" > "$tmp" && mv "$tmp" "$CONFIG"
}


# -------------------------------------------------
# Usuwanie wpisu blablabla = abccasd
# -------------------------------------------------

sed -i '/^[[:space:]]*blablabla[[:space:]]*=/d' "$CONFIG"

# -------------------------------------------------
# CWU
# -------------------------------------------------

if ! config_has "dhwuse"; then
    read -p "Czy korzystasz z CWU? [t/n]: " -n 1 answer < /dev/tty
    echo

    [[ "$answer" =~ [Tt] ]] && DHW=1 || DHW=0

    insert_after_section "SETTINGS" "dhwuse = $DHW"
else
    echo "ℹ️  Wpis dhwuse istnieje"
fi

# -------------------------------------------------
# ZONE
# -------------------------------------------------

if ! config_has "zone_frost_enable"; then
    insert_after_section "SETTINGS" \
"zone_frost_enable = 0
zone_frost_temp = -5
zone_frost_mode = quiet
zone_warm_enable = 0
zone_warm_temp = 10
zone_warm_mode = quiet_flimit"
else
    echo "ℹ️  Wpis zone istnieje"
fi

# -------------------------------------------------
# EMERGENCY
# -------------------------------------------------

if ! config_has "emergency_intemp"; then
    insert_after_section "SETTINGS" "emergency_intemp = 20.0"
else
    echo "ℹ️  Wpis emergency_intemp istnieje"
fi

# -------------------------------------------------
# DHW TEMP
# -------------------------------------------------

if ! config_has "dhwtemp"; then
    insert_after_section "SETTINGS" "dhwtemp = builtin"
    insert_after_section "HOMEASSISTANT" "dhwsensor ="
else
    echo "ℹ️  Wpis dhwtemp istnieje"
fi

# -------------------------------------------------
# NO LIMIT MODE
# -------------------------------------------------

if ! config_has "dhwnolimit_mode"; then
    insert_after_section "SETTINGS" "dhwnolimit_mode = turbo"
else
    echo "ℹ️  Wpis dhwnolimit_mode istnieje"
fi

# -------------------------------------------------
# DIRECT THERMOSTAT
# -------------------------------------------------

if ! config_has "direct_thermostat"; then
    insert_after_section "SETTINGS" \
"direct_thermostat = 0
direct_inside_settemp = 22.0"
else
    echo "ℹ️  Wpis direct_thermostat istnieje"
fi

# -------------------------------------------------
# START
# -------------------------------------------------

# -------------------------------------------------
# FIX
# -------------------------------------------------

read -p "Czy masz problem z logowaniem na strone www? [t/n]: " -n 1 answer < /dev/tty
echo
    
if [[ "$answer" =~ [Tt] ]]; then
    sed -i '/^[[:space:]]*bindport[[:space:]]*=/d' "$CONFIG"
    sed -i '/^[[:space:]]*bindaddress[[:space:]]*=/d' "$CONFIG"
    sed -i '/^[[:space:]]*firstrun[[:space:]]*=/d' "$CONFIG"
    insert_after_section "MAIN" "bindport = 80"
    insert_after_section "MAIN" "bindaddress = 0.0.0.0"
    insert_after_section "MAIN" "firstrun = 0"
    echo "ℹ️  wpisy w config naprawiono"
fi

echo
echo "🚀 Startuję usługę Haier..."
systemctl start "$SERVICE" \
    && echo "✅ OK: USŁUGA WYSTARTOWAŁA" \
    || echo "⚠️  Błąd uruchamiania usługi"
